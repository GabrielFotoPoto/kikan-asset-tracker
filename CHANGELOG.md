# Journal des changements

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/) ; versions numérotées `MAJEUR.MINEUR.CORRECTIF`. La feuille de route
détaillée est dans [SPEC.md](SPEC.md) (§13).

## [Non publié]

## [0.4.0-rc.1] - 2026-10-31

Préversion à tester : refonte de l'interface (navigation, recherche globale, retours d'action, thème sombre, petits écrans, mode tablette et parcours d'arrivée). Aucune migration de base de données. Pas encore validés : l'affichage sur un vrai téléphone (la capture mobile est simulée) et les vues des rôles RH et lecture dans le navigateur ; la portée par entité est en revanche couverte par les tests.

### Sécurité
- `pypdf` passe de 6.21.3 à 6.21.4 (3 vulnérabilités publiées après la 0.3.4).

### Ajouté
- **Recherche globale (Ctrl+K)** : matériel, salariés, pages et actions selon le rôle. Nouvelle route `GET /search` (tous les rôles) qui **applique la portée par entité**, ignore casse et accents, exige tous les termes et ne renvoie ni notes ni e-mails. Nouvelle suite `tests/search_check.py`, et `/search` rejoint l'inventaire des routes soumises à la portée de `tests/scope_check.py`.
- **Parcours « Nouvel arrivant »** : page `/arrivee/:id` (bouton **Parcours** de la liste des utilisateurs) avec les cinq étapes (fiche, besoins, préparation, remise signée, accès), la prochaine action selon le rôle et un journal. Nouvelle route `GET /arrivee/{id}` : l'avancement est calculé sans rien écrire, visible des **RH** (qui ne peuvent pas lire le suivi des besoins) comme de l'informatique, sans nom de compte ni numéro de série. Nouvelle suite `tests/arrivee_check.py`.
- **Thème clair, sombre ou système** (menu latéral, mémorisé par navigateur), appliqué avant l'affichage par `public/theme-init.js` (la politique de sécurité du contenu interdit les scripts en ligne).
- **Mode tablette de la signature** : toute page `/signer/...` s'affiche sans menu, avec de grandes zones tactiles et un bouton Quitter.
- **Petits écrans** : barre du haut avec recherche et menu, tableaux défilants, matériel en cartes.
- **Filtres de la page Matériel dans l'adresse** (recherche, statut, type, entité) et lien profond `/materiel?asset=<id>`. La page Utilisateurs accepte `?q=`.
- Composants : notifications (`Notifications.jsx`), fenêtre de confirmation (`ConfirmDialog.jsx`), états vide, chargement et erreur (`State.jsx`), palette (`Palette.jsx`), barre latérale par sections (`NavPrincipale.jsx`, structure unique dans `nav.js`) et fil d'Ariane.

### Modifié
- **Navigation** en cinq sections repliables (Administration repliée par défaut) avec compteurs ; chaque tuile du tableau de bord mène à la liste filtrée.
- Les messages de succès et d'erreur de 22 pages deviennent des **notifications** (succès annoncés poliment et retirés au bout de 6 s, erreurs conservées) ; les quatre `window.confirm` deviennent une **fenêtre de confirmation** (la purge RGPD demande de taper `PURGER` et liste les salariés concernés).
- **Accessibilité** : lien d'évitement, anneau de focus visible, zones tactiles de 44 px sur écran tactile, bordures de champs à 3:1 au moins (elles étaient à 1,3:1) et couleur d'avertissement `#8a5100` (6,4:1 au lieu de 4,2).
- Toutes les couleurs de `styles.css` sont des jetons `light-dark()` : une seule définition par couleur pour les thèmes clair et sombre.

### Documentation
- Section « Interface » du README avec neuf captures (`docs/captures/interface-*.png`).

## [0.3.4] - 2026-10-30

Renouvellement du matériel (échange en un seul document signé, page Renouvellements, report d'échéance), bleu du logo partout et licence du logo.

### Mise à jour depuis 0.3.3
- Les migrations 0019 (échange de matériel : type d'affectation, **date de retour par actif**, retours d'échange) et 0020 (historique des reports d'échéance) s'appliquent seules au démarrage de l'API. Les affectations déjà clôturées reçoivent la date de leur clôture comme date de retour.

### Ajouté
- **Renouvellement du matériel d'un salarié en poste (échange)**, réservé à l'informatique : remise du nouveau matériel et restitution de l'ancien **en une seule opération, avec un seul document signé et scellé** (« Accusé d'échange de matériel », un seul numéro). Page `/renouveler` (boutons **Renouveler** sur la page Matériel et sur la page Utilisateurs), signature en une fois sur la tablette (rien ne change avant la signature), **devenir de l'ancien matériel choisi** (rendu, retour en stock, à réformer), **charte annexée au choix** (décochée par défaut), besoins ouverts soldés, motif facultatif, renouvellement **partiel** possible. `POST /assignments/echange`, `GET /assignments/echange/recap`, `GET /assignments/detenteur/{id}`, document `?type=echange`. Nouvelle suite `tests/echange_check.py`.
- La liste des remises affiche le type **échange** et le matériel restitué.
- **Page « Renouvellements »** (informatique) : matériel en stock ou affecté dont l'échéance est dépassée ou proche (horizon : dépassée seulement, 1, 3, 6 ou 12 mois ; filtre d'entité), avec **détenteur**, situation et dernier report ; boutons **Renouveler** et **Reporter**. **Report ou avancement de l'échéance** (ou « aucun renouvellement prévu ») avec **motif facultatif** et historique (`GET /renouvellements`, `POST /renouvellements/{id}/reporter`). Tuile « Échéances de renouvellement dépassées » du tableau de bord. Nouvelle suite `tests/renouvellements_check.py`.

### Modifié
- Un matériel **rendu ou réformé n'est plus à renouveler** : il sort des prévisions, des rappels e-mail et des statistiques d'échéances (un matériel remplacé n'était jusqu'ici plus compté qu'une fois réformé).
- Une restitution est enregistrée **par actif** (date de retour) : les statistiques de mouvements comptent désormais chaque restitution à sa date, y compris pour les restitutions partielles et les échanges ; une affectation ne se clôture que lorsque tout son matériel est parti.
- La resynchronisation du stockage reconnaît le type de document (remise, restitution, échange) d'après ses preuves, et non plus d'après le nom du fichier.

- **Couleur de marque** : retour au **bleu du logo, `#1D428A`**, pour la barre latérale, les boutons, les liens, les chiffres, la couleur du thème du navigateur et le manifeste, **et pour les en-têtes de tableau des PDF et des exports Excel** (rapports, statistiques, prévisions, revue des accès, accusés de remise), qui utilisaient l'ancien `#2b4c7e` : une seule constante (`backend/app/theme.py`) remplace sept valeurs dispersées. Seuls les documents générés après la mise à jour changent ; les PDF déjà scellés ne sont pas modifiés (la 0.3.3 utilisait `#024B8F`, issu de la conversion du quadri C100 M75 J0 N0, qui ne correspondait pas au logo).

### Documentation
- **Licence du logo et du nom** : le code reste en GPL-3.0-or-later ; le logo et le nom « Kikan » ne sont pas couverts par cette licence (tous droits réservés, usage autorisé sans modification pour désigner le projet et utiliser le logiciel tel quel). Section « Logo et nom » du README, politique détaillée dans `docs/logo/LICENCE.md`.

## [0.3.3] - 2026-10-30

Souhaits de matériel avec gamme (les RH sans accès à la page Besoins) et nouveau bleu de marque.

### Mise à jour depuis 0.3.2
- La migration 0018 (gammes) s'applique seule au démarrage de l'API. Les catégories de besoin d'origine reçoivent des gammes par défaut (PC portable : Standard, Haut de gamme ; Smartphone Apple : Normal, Pro, XL), modifiables dans **Paramétrage, Catégories de besoin**.
- **Les RH n'ont plus accès à la page Besoins** (menu, tuile du tableau de bord, liens) ni aux routes de suivi (`GET /besoins`, `/besoins/ouverts`, modification, changement de statut : réponse 403). Elles gardent la création d'un souhait depuis le formulaire d'entrée d'un salarié. Un souhait saisi par erreur se corrige désormais côté informatique.

### Ajouté
- **Gamme souhaitée** sur les besoins : l'informatique définit par catégorie une liste de gammes (10 au plus, par exemple Normal, Pro, XL pour un smartphone Apple ; Standard, Haut de gamme pour un PC portable) ; à l'entrée d'un salarié, les RH choisissent la gamme (facultative) une fois la catégorie cochée. La gamme apparaît sur la page Besoins, à la remise et dans le rappel e-mail. `GET /besoins/choix`, `PUT /parametres/categories-besoin/{id}/gammes`.

### Modifié
- **Couleur de marque** : bleu **#024B8F** (quadri C100 M75 J0 N0) pour la barre latérale, les boutons, les liens et les chiffres (jusqu'ici `#2b4c7e`), et pour la couleur du thème du navigateur et du manifeste.
- Le formulaire d'entrée parle de **matériel souhaité** (et non plus « nécessaire ») ; le compteur « Besoins à traiter » n'est plus renvoyé aux RH (`null`). Le texte de la page Besoins décrit le nouveau rôle des RH.

## [0.3.2] - 2026-10-30

Identité visuelle : logo Kikan par défaut et icône de l'application personnalisable.

### Mise à jour depuis 0.3.1
- Aucune migration de base : l'icône personnalisée est un réglage. Rien à faire ; après la mise à jour, actualisez le navigateur (Cmd + Maj + R) pour voir le nouveau logo d'onglet.
- Sur la page de connexion, l'icône est lisible sans session (seule image publique) : n'y mettez rien de confidentiel.

### Ajouté
- **Icône de l'application** personnalisable (Paramétrage, onglet **Apparence**, informatique) : affichée dans le menu, sur la page de connexion et comme icône d'onglet. PNG ou JPEG (300 Ko, 1000 x 400 px au plus), vérifié par son contenu puis réécrit en PNG sans métadonnées ; jamais de SVG. Lecture publique limitée à cette image (`GET /api/branding`, `/api/branding/icone`) pour la page de connexion ; dépôt et suppression réservés à l'informatique et journalisés (empreinte seulement). Le nom « Kikan » reste celui du produit. Nouvelle suite `tests/branding_check.py`.
- **Logo Kikan** : jeu de favicons par défaut (`frontend/public/` : `favicon.ico`, `favicon.svg`, icônes 192 et 512, `apple-touch-icon`, manifeste web), affiché dans le menu, sur la connexion et la page À propos tant qu'aucune icône n'est déposée ; l'icône personnalisée garde la priorité (onglet compris) et sa suppression rétablit le logo. Logo, README d'accueil soigné et image d'aperçu du dépôt (`docs/logo/kikan-social.png`, à téléverser dans les réglages GitHub) dans `docs/logo/`. Le manifeste web est servi en `application/manifest+json`.

## [0.3.1] - 2026-10-30

Statistiques exportables, prévisions de renouvellement avec budget estimé et page « À propos ».

### Mise à jour depuis 0.3.0
- La migration 0017 (coûts de remplacement) s'applique seule au démarrage de l'API. Sans coût renseigné, la page Prévisions affiche un budget à zéro et le nombre de
  matériels « sans estimation » : renseignez les coûts dans **Paramétrage, Coûts de remplacement**.

### Ajouté
- **Prévisions de renouvellement** (C3) : page Prévisions avec **budget estimé** par mois, année civile, type et entité, sur une période au choix (12 mois par défaut, 60 mois au plus), filtre d'entité, échéances dépassées signalées, matériel sans coût compté à part, export **CSV, Excel et PDF** (`GET /previsions`). Les coûts de remplacement se saisissent par type, avec exception par modèle, dans **Paramétrage, Coûts de remplacement** (`/parametres/couts`, informatique). Aucune donnée de salarié. Nouvelle suite `tests/previsions_check.py`.
- **Statistiques exportables** (C1) : filtres par entité (sous-entités incluses, dans la portée du compte) et par période, bloc « Mouvements de la période » (matériels remis, restitués et achetés, par mois), fenêtre des renouvellements réglable, export **CSV, Excel et PDF** (`GET /stats?format=csv|xlsx|pdf&entite_id=&du=&au=`). Nouvelle suite `tests/stats_check.py`.
- **Page « À propos »** (lien en pied de menu, tous les comptes) : version et date de publication, notes de la version, licence GPL-3.0-or-later et auteur, liens vers le dépôt, composants principaux avec leur version installée et leur licence. Une image construite en local s'annonce « version de développement ». Nouvelle route `GET /apropos` ; la date de publication est transmise aux images par le workflow de publication (`KIKAN_RELEASE_DATE`). Nouvelle suite `tests/apropos_check.py`.

### Modifié
- Le filtre d'entité des statistiques et des prévisions est partagé (`scope.restreindre_entite`) ; `xlsx_io.build_table` accepte des colonnes de montants (nombres, additionnables dans Excel).
- Page Prévisions : tableaux défilants dans leur carte sur petit écran ; champ « Montant » du Paramétrage plus large.
- Le guide d'utilisation gagne des captures (statistiques, prévisions, coûts de remplacement, À propos) et deux sections (6.3 et 6.4).

## [0.3.0] - 2026-10-30

Pilotage, conformité et durcissement : revue des droits d'accès, purge RGPD paramétrable, annulation d'import, session sécurisée, guides.

### Mise à jour depuis 0.2.x
- **Sauvegardez avant** (voir [docs/SAUVEGARDE.md](docs/SAUVEGARDE.md)). Les migrations 0014 à 0016 (suivi de la purge RGPD, lots d'import, revue des accès) s'appliquent seules au
  démarrage de l'API.
- **Tout le monde devra se reconnecter une fois** : la session du navigateur est maintenant un cookie `HttpOnly`. Les scripts qui utilisent un jeton `Authorization: Bearer` et l'API
  d'import par jetons ne changent pas.
- **Durée de conservation RGPD** : la valeur proposée par défaut passe de 36 à **12 mois** (une valeur déjà enregistrée est conservée), avec un **délai de grace de 30 jours** réglable
  avant la suppression définitive des PDF du partage. Vérifiez la page RGPD avant de lancer une purge.
- Un mot de passe initial **généré** (premier démarrage) doit être changé dès la première connexion.
- Si le serveur web répond « 502 » après la mise à jour : `docker compose restart web` (corrigé pour les prochaines recréations de l'API).
- `KIKAN_TSA_URL` (horodatage RFC 3161) se règle désormais dans `.env`.

### Modifié
- **Session du navigateur dans un cookie `HttpOnly`** au lieu de `localStorage` : un script injecté (XSS) ne peut plus lire le jeton. Cookie
  `SameSite=Strict` (et `Secure` en HTTPS), limité à `/api`, plus en-tête `X-Kikan-Request` exigé sur les requêtes qui modifient (CSRF). Nouvelle
  route `POST /auth/logout` qui efface le cookie. Le jeton `Authorization: Bearer` reste accepté pour les scripts, et `/auth/login` le renvoie
  toujours dans sa réponse. Les utilisateurs devront se reconnecter une fois après la mise à jour. Nouvelle suite `tests/session_cookie_check.py`.
- **Les tests ne touchent plus à votre instance** : `tests/run_all.sh` crée sa propre pile (projet Docker `kiktest`, conteneurs, volumes, réseau et
  port 8081 propres, secrets repris de `.env` sans le reste). Avant, le nettoyage des tests effaçait les réglages d'e-mails et de GLPI de la base de
  développement. Noms de conteneurs et port de l'API réglables (`KIKAN_PREFIX`, `KIKAN_API_PORT`).
- La durée de conservation RGPD proposée par défaut passe de 36 à 12 mois (une valeur déjà enregistrée est conservée).
- Le serveur web retrouve l'API après sa recréation (résolution DNS à chaque requête) : plus de « 502 Bad Gateway » jusqu'à son redémarrage.

### Ajouté
- `KIKAN_TSA_URL` (horodatage RFC 3161 des PDF scellés) se règle désormais dans `.env` ; variables `KIKAN_SMB_PORT` et `KIKAN_BACKUP_SMB_ENCRYPT` documentées dans `.env.example`.
- **Guides** : [guide d'installation](docs/INSTALLATION.md) (images publiées ou sources, configuration, HTTPS, sauvegarde, mise à jour, dépannage) et
  [guide d'utilisation](docs/GUIDE-UTILISATEUR.md) (par rôle et par tâche, avec captures). Le jeu de démonstration gagne des cas pour la revue des accès
  (accès de salariés sortis, application arrêtée) et une remise en attente de signature.
- **Jeu de données de démonstration** (`scripts/demo.sh charger | etat | effacer`) : groupe fictif, 52 salariés, 77 matériels, remises signées avec de vrais PDF
  scellés, restitutions, besoins, départs, matériel non restitué ou à renouveler, salariés à purger. Refuse de se charger sur des données réelles ;
  l'effacement ne retire que ce qu'il a créé.
- **Revue périodique des droits d'accès** (C2, ISO 27001 A.5.18) : page Revue des accès (anomalies, rapport « qui a accès à quoi » en Excel et CSV,
  campagnes à la demande décidées par les RH dans leur périmètre et l'informatique), clôture avec rapport PDF scellé, accès retirés passés à non,
  suivi des retraits dans les applications, rappels par e-mail, anomalies sur le tableau de bord. Migration 0016.
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

### Sécurité
- Chaîne d'approvisionnement : actions GitHub figées sur une empreinte de commit (et contrôle automatique), jetons du dépôt non conservés par les
  checkouts, délai de précaution Dependabot, analyse CodeQL, revue des dépendances, analyse de sécurité des workflows (`actionlint`, `zizmor`),
  `CODEOWNERS`.
- Connexion : l'identifiant est normalisé une fois (espaces, majuscules) pour le limiteur de tentatives, le journal et la recherche du compte : `"Admin "` ne contourne plus la limite de 5 essais.
- Le mot de passe initial **généré** (affiché dans les journaux) impose un changement à la première connexion.
- Journal d'audit : les refus 401/403 sont plafonnés à 60 par minute et par adresse IP ; les écritures authentifiées sont toujours journalisées.
- Images de base (python, postgres, node, nginx) figées par empreinte, mises à jour par Dependabot ; `PATCH` autorisé côté CORS ; exemple de configuration `set_real_ip_from` derrière un reverse-proxy.
- Signalement privé des vulnérabilités activé sur le dépôt (annoncé par `SECURITY.md`). Le dépôt exige désormais que toute action de workflow soit figée sur une empreinte de commit,
  et une règle protège les étiquettes de version `v*` (création réservée aux administrateurs, aucune modification ni suppression).
- Contributions externes relues et reprises : limiteur de connexion et images figées (#36), session en cookie HttpOnly (#37).

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
