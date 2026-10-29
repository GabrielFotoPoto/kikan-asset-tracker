# Journal des changements

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/) ; versions numérotées `MAJEUR.MINEUR.CORRECTIF`. La feuille de route
détaillée est dans [SPEC.md](SPEC.md) (§13).

## [Non publié]

### Modifié
- **Les tests ne touchent plus à votre instance** : `tests/run_all.sh` crée sa propre pile (projet Docker `kiktest`, conteneurs, volumes, réseau et
  port 8081 propres, secrets repris de `.env` sans le reste). Avant, le nettoyage des tests effaçait les réglages d'e-mails et de GLPI de la base de
  développement. Noms de conteneurs et port de l'API réglables (`KIKAN_PREFIX`, `KIKAN_API_PORT`).
- Le serveur web retrouve l'API après sa recréation (résolution DNS à chaque requête) : plus de « 502 Bad Gateway » jusqu'à son redémarrage.

### Ajouté
- **Jeu de données de démonstration** (`scripts/demo.sh charger | etat | effacer`) : groupe fictif, 52 salariés, 76 matériels, remises signées avec de vrais PDF
  scellés, restitutions, besoins, départs, matériel non restitué ou à renouveler, salariés à purger. Refuse de se charger sur des données réelles ;
  l'effacement ne retire que ce qu'il a créé.
- **Annulation d'un import** (A3b) : chaque import réel de la page Import est un lot ; le bouton *Annuler cet import* supprime ce qu'il a créé,
  tout ou rien, et seulement si rien n'en dépend (salarié avec matériel, accès ou besoins, actif remis, entité utilisée, remise signée ou
  restituée, lien GLPI) ; le refus indique ce qui bloque. Migration 0015.
- **Contrôle de sécurité du code** : `scripts/securite_scan.sh` (Bandit, Semgrep, gitleaks, hadolint, actionlint, zizmor, audits de dépendances)
  et skill Claude Code `/kikan-securite` (scans puis relecture avec la liste de contrôle de Kikan). Faux positifs connus justifiés dans le code
  (`# nosec`, `# nosemgrep`), `.gitleaks.toml` et `.hadolint.yaml`.
- **Purge RGPD en deux temps** : durée de conservation (12 mois par défaut) et délai de grace (30 jours par défaut) **réglables** ; bouton réservé
  à l'informatique ; PDF du partage (SMB, WebDAV, volume local) rangés dans `A_PURGER/` puis supprimés par Kikan après le délai de grace, avec remise en place
  possible ; pour SharePoint et DocuWare, liste des documents à supprimer par l'équipe de la GED puis confirmation ; rappel par e-mail si la purge
  n'est pas faite ; journal sans nom ni matricule (nombres et empreintes SHA-256). Migration 0014.

### Corrigé
- **Double clic et appels simultanés** : la remise (actifs), la signature (affectation) et la restitution (salarié) sont verrouillées ; le second
  appel reçoit 409 ou 400 au lieu de créer un doublon. Idée issue d'une relecture externe (PR #12).

### Modifié
- La durée de conservation proposée par défaut passe de 36 à 12 mois (une valeur déjà enregistrée est conservée).

## [0.2.0] - 2026-10-29

Identité, intégrations et automatisation.

### Mise à jour depuis 0.1.x
- Les migrations (0011 à 0013 : catégories de besoin, acronyme et compteur de documents des salariés, liens de réinitialisation) s'appliquent
  seules au démarrage de l'API. Les PDF déjà archivés ne sont pas renommés.
- `KIKAN_PUBLIC_URL` (adresse publique en HTTPS) est nécessaire pour le lien « Mot de passe oublié ? » et les liens des e-mails ;
  `KIKAN_TIMEZONE` (Europe/Paris par défaut) fixe le fuseau des dates dans les noms de PDF.

### Ajouté
- **Connexion Microsoft 365 (SSO)** facultative (Entra ID), rôles d'application, comptes de secours, durée de session réglable (B1).
- **Comptes cloisonnés par entité** : les comptes RH et lecture sont globaux ou limités à des entités et leurs sous-entités ; les comptes
  informatique restent globaux (B2).
- **Rappels par e-mail** (renouvellements, départs à venir, matériel non restitué, besoins non traités) et **rapport mensuel**, par un
  serveur SMTP externe (B3, B4).
- **API d'import par jetons** (`/api/v1`) et **connecteur GLPI** (import sur sélection, export des salariés et du matériel avec numéros
  de série) testé contre GLPI 10.0.28, 11.0.12 et 12.0.1 (B5).
- **Stockage des PDF scellés dans SharePoint Online et DocuWare**, outil de copie vers le moteur actif (B6).
- **Besoins de matériel** saisis par les RH, soldés par la remise (B7).
- **Import et export Excel** (B8).
- **Sauvegarde et restauration** chiffrées, planifiables, avec rétention 30 jours plus une par mois sur 12 mois, restauration guidée et
  vérification des empreintes (E7).
- **Nom des PDF scellés** : `AAAA_MM_JJ_NOM_PRENOM_ACR_NNN.pdf` (date de signature, nom et prénom, acronyme de 3 lettres de la fiche salarié, compteur propre au salarié, un par document signé), toujours rangé dans le dossier de l'année. Seuls les nouveaux documents suivent cette règle. L'index DocuWare `cle` reste sans nom ni prénom.
- **Mot de passe oublié** : lien à usage unique (30 minutes) envoyé par e-mail, réponse identique que le compte existe ou non, demandes limitées, sessions révoquées ; commande de secours `python -m app.reset_admin` pour le dernier administrateur.
- **Heure de Paris** dans le nom des PDF (changements d'heure compris, réglable par `KIKAN_TIMEZONE`), **heure de signature** dans la liste des remises, raccourci « Importer un fichier » sur la page Matériel.
- **Catégories de besoin** gérées par l'informatique, cochées par les RH à l'entrée du salarié (sans marque ni modèle).
- **Intégration continue** (GitHub Actions : tests, audit des dépendances, sauvegarde de bout en bout, images), Dependabot, publication des
  images Docker (E5).

### Corrigé
- Le téléchargement d'un PDF scellé propose le nom du fichier rangé (plus `remise_<n°>.pdf`), et la page d'accueil est revalidée par Nginx à
  chaque visite : une mise à jour du front est vue tout de suite.
- `GET /assignments/{id}/document` pouvait renvoyer le PDF de la **restitution** à la place de celui de la **remise** (une affectation porte
  deux signatures après une restitution et aucun ordre n'était imposé). Le choix est désormais déterministe (la remise par défaut) et la
  restitution se lit avec `?type=restitution`. Défaut découvert en rejouant l'enchaînement complet des suites (`tests/run_all.sh`).

### Sécurité
- Chaîne d'approvisionnement : actions GitHub figées sur une empreinte de commit (et contrôle automatique), jetons du dépôt non conservés par les
  checkouts, délai de précaution Dependabot, analyse CodeQL, revue des dépendances, analyse de sécurité des workflows (`actionlint`, `zizmor`),
  `CODEOWNERS`.
- Cloisonnement par entité vérifié sur chaque route ; un oubli est détecté par un test d'inventaire des routes.
- Le routeur RGPD (qui listait les salariés à purger) est réservé à l'informatique.
- Mot de passe oublié : lien à usage unique dont seule l'empreinte est stockée, réponse identique que le compte existe ou non, envoi en tâche de fond, demandes limitées par adresse IP et par identifiant.

## [0.1.x] - 2026-10

Socle et finitions.

### Ajouté
- Suivi des actifs par salarié et par entité, remises et restitutions **signées à l'écran** (signature manuscrite) et **scellées** (PAdES),
  chartes d'usage, cycle de vie des salariés, purge RGPD, journal d'audit, rôles informatique, RH et lecture, rapports et statistiques.
- Import CSV, modification et suppression protégées, paramétrage (types, services, marques, modèle de PDF), gestion des comptes, accès
  applicatifs dans le document de remise, saisie assistée du matériel.
- Stockage des PDF scellés en local, sur lecteur réseau (SMB) ou partage web (WebDAV), avec tampon local et reprise.
- Migrations Alembic, Docker durci, HTTPS.
