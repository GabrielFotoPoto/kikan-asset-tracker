# Journal des changements

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/) ; versions numérotées `MAJEUR.MINEUR.CORRECTIF`. La feuille de route
détaillée est dans [SPEC.md](SPEC.md) (§13).

## [0.2.0] - à publier

Identité, intégrations et automatisation.

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
- **Catégories de besoin** gérées par l'informatique, cochées par les RH à l'entrée du salarié (sans marque ni modèle).
- **Intégration continue** (GitHub Actions : tests, audit des dépendances, sauvegarde de bout en bout, images), Dependabot, publication des
  images Docker (E5).

### Corrigé
- `GET /assignments/{id}/document` pouvait renvoyer le PDF de la **restitution** à la place de celui de la **remise** (une affectation porte
  deux signatures après une restitution et aucun ordre n'était imposé). Le choix est désormais déterministe (la remise par défaut) et la
  restitution se lit avec `?type=restitution`. Défaut découvert en rejouant l'enchaînement complet des suites (`tests/run_all.sh`).

### Sécurité
- Cloisonnement par entité vérifié sur chaque route ; un oubli est détecté par un test d'inventaire des routes.
- Le routeur RGPD (qui listait les salariés à purger) est réservé à l'informatique.

## [0.1.x] - 2026-10

Socle et finitions.

### Ajouté
- Suivi des actifs par salarié et par entité, remises et restitutions **signées à l'écran** (signature manuscrite) et **scellées** (PAdES),
  chartes d'usage, cycle de vie des salariés, purge RGPD, journal d'audit, rôles informatique, RH et lecture, rapports et statistiques.
- Import CSV, modification et suppression protégées, paramétrage (types, services, marques, modèle de PDF), gestion des comptes, accès
  applicatifs dans le document de remise, saisie assistée du matériel.
- Stockage des PDF scellés en local, sur lecteur réseau (SMB) ou partage web (WebDAV), avec tampon local et reprise.
- Migrations Alembic, Docker durci, HTTPS.
