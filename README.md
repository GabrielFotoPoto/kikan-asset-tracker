# Kikan

**Kikan** (機器管理, *kiki-kanri*, « gestion des équipements ») est une application de
**suivi des actifs** (PC, smartphones...) par utilisateur et par entité, avec **remise et
restitution de matériel signées et scellées** (sans papier), import de l'existant, reporting
et gestion des accès applicatifs.

Elle soutient plusieurs contrôles de l'ISO/IEC 27001:2022 :
A.5.9 (inventaire des actifs), A.5.10 (usage acceptable), A.5.11 (restitution des actifs)
et A.5.18 (droits d'accès).

> Remarque : un logiciel n'est pas « certifié ISO 27001 ». Kikan *facilite* la conformité du
> SMSI d'une organisation, il ne la remplace pas.

## Fonctionnalités (v0.1)

- **Cycle de vie du salarié** : formulaire d'entrée (RH), départ avec génération automatique de
  la liste du matériel à récupérer, passage automatique en « sorti » une fois tout rendu.
- **Remise signée** : génération d'un accusé PDF (matériel + charte informatique annexée),
  signature sur tablette, puis **scellement PAdES** (certificat auto-signé de l'organisation,
  horodatage RFC 3161 optionnel). Document infalsifiable et vérifiable.
- **Restitution signée** (A.5.11), conduite par l'informatique ou les RH.
- **Multi-entités / filiales** : rattachement des salariés, données filtrables par entité.
- **Accès applicatifs** (A.5.18) : catalogue d'applications, attribution par salarié avec note
  de niveau (ex. administrateur, « mêmes droits que... »).
- **Import CSV** de l'existant (entités, applications, utilisateurs, matériel, affectations,
  accès), avec prévisualisation et rapport d'erreurs par ligne.
- **Reporting** « qui détient quoi » à l'instant T, export **CSV** et **PDF**.
- **Statistiques** de parc (modèles les plus distribués, répartition, taux d'équipement,
  renouvellements à venir, âge moyen).
- **Rétention RGPD** paramétrable, avec prévisualisation des suppressions avant validation.
- **Authentification et rôles** : RH, informatique, lecture seule.

## Pile technique

- **Front** : React (Vite), servi par Nginx (reverse-proxy `/api`).
- **Back** : FastAPI (Python), SQLModel.
- **Base** : PostgreSQL.
- **Signature PDF** : pyHanko (PAdES) ; **génération PDF** : ReportLab.
- Déploiement **on-premise**, entièrement conteneurisé (`docker compose`).

## Démarrage rapide

Prérequis : Docker et Docker Compose.

```bash
cp .env.example .env        # puis renseigner POSTGRES_PASSWORD et KIKAN_SECRET_KEY
docker compose up --build
```

- Interface : **https://localhost:3443** (certificat auto-signé : avertissement du navigateur à accepter
  en local). Le port `http://localhost:3000` redirige vers HTTPS.
- API en direct (développement, machine locale uniquement) : http://localhost:8080
  (documentation interactive : http://localhost:8080/docs, masquée en production).

### Premier compte

Au premier démarrage, un compte **informatique** est créé (identifiant `admin` par défaut). Son mot de passe est
**aléatoire** : il est affiché une seule fois dans les journaux.

```bash
docker compose logs api | grep "COMPTE INITIAL"
```

Connectez-vous, puis changez-le depuis **Mon compte** et créez des comptes nominatifs. Vous pouvez aussi fixer
vous-même `KIKAN_ADMIN_USER` et `KIKAN_ADMIN_PASSWORD` dans `.env` avant le premier démarrage.

> **Sécurité** : `KIKAN_SECRET_KEY` (clé de signature des sessions, 32 caractères minimum) et `POSTGRES_PASSWORD`
> sont à définir dans `.env`, qui ne doit jamais être commité. Avec `KIKAN_ENV=production`, l'application refuse
> de démarrer sans clé solide. Voir [SECURITY.md](SECURITY.md) pour la liste de contrôle de mise en production,
> les risques acceptés et les tests de sécurité.

### Tablette de signature sur le réseau local

Par défaut l'interface n'est publiée que sur la machine locale. Pour l'ouvrir au réseau de l'organisation,
définir dans `.env` `KIKAN_BIND` (adresse IP du serveur) et `KIKAN_TLS_SAN` (ex. `DNS:kikan.exemple.local,IP:192.168.1.10`)
avant le premier démarrage, ou monter le certificat de l'organisation dans le volume `kikan_webcerts`.

## Rôles

| Rôle | Droits |
|---|---|
| **informatique** | Tout : matériel, remises, restitutions, signatures, entités, import, paramétrage, RGPD, comptes, journal d'audit. |
| **rh** | Cycle de vie des salariés (entrées, départs), restitutions, accès applicatifs. Lecture du reste. |
| **lecture** | Consultation et export uniquement. |

> Cible v0.2 : authentification **SSO Microsoft 365 (Entra ID)** avec comptes nominatifs,
> réservée aux groupes `Kikan-IT` (informatique) et `Kikan-RH` (rh).

## Import de l'existant

Des modèles CSV sont fournis dans [`import-modeles/`](import-modeles/) (un fichier par type,
reliés par des codes). Format : UTF-8, séparateur `;`, dates `AAAA-MM-JJ`, booléens `oui/non`.
Ordre conseillé : entités, applications, utilisateurs, matériel, affectations, accès.

## Stockage des documents (PDF scellés)

Les remises et restitutions signées sont des PDF scellés, rangés **par année** (`AAAA/...`). Trois emplacements
sont possibles, choisis dans `.env` avec `KIKAN_STORAGE_BACKEND` :

| Valeur | Emplacement | Variables principales |
|---|---|---|
| `local` (défaut) | volume Docker du serveur | aucune |
| `smb` | **lecteur réseau** Windows ou Samba (`\\serveur\partage`), SMB 3 chiffré, sans montage | `KIKAN_SMB_SERVER`, `KIKAN_SMB_SHARE`, `KIKAN_SMB_PATH`, `KIKAN_SMB_USER`, `KIKAN_SMB_PASSWORD`, `KIKAN_SMB_DOMAIN` |
| `webdav` | **partage de fichiers web** (HTTPS, WebDAV) | `KIKAN_WEBDAV_URL`, `KIKAN_WEBDAV_USER` et `KIKAN_WEBDAV_PASSWORD` (ou `KIKAN_WEBDAV_TOKEN`), `KIKAN_WEBDAV_CA_BUNDLE` |

Fonctionnement, pensé pour ne jamais perdre une preuve :

- Le PDF est **toujours écrit d'abord en local**, puis déposé sur le partage, **relu et vérifié** (empreinte SHA-256).
  Le tampon local n'est purgé qu'après ce dépôt vérifié.
- Si le partage est **indisponible**, la signature réussit quand même : le document reste en local et sera déposé
  plus tard, automatiquement au démarrage de l'API ou depuis la page **Stockage** (« Reprendre les dépôts en attente »).
- À chaque lecture, l'empreinte est comparée à celle enregistrée à la signature : un fichier **altéré sur le partage
  est détecté** (lecture refusée et alerte dans le journal d'audit).
- La page **Stockage** (rôle informatique) affiche l'emplacement actif, le nombre de documents par emplacement,
  permet de tester la connexion et de reprendre les dépôts en attente.
- La purge RGPD supprime aussi les fichiers sur le partage, une fois la base validée.

Pour un WebDAV avec un certificat d'autorité interne, déposer le certificat (PEM) dans `./ca/` et définir
`KIKAN_WEBDAV_CA_BUNDLE=/ca/mon-autorite.pem`. L'HTTP simple est refusé par défaut, et la vérification du
certificat du serveur ne peut pas être désactivée.

Changer d'emplacement : les nouveaux documents vont vers l'emplacement actif ; les anciens restent lisibles tant que
les variables de leur emplacement d'origine sont conservées dans `.env`. Le passage de `local` vers `smb` ou `webdav`
est automatique (les documents locaux sont déposés au démarrage).
**Attention : ne supprimez ni ne déplacez jamais un partage tant que des documents y sont référencés** (la page
Stockage indique leur nombre par emplacement) : ils ne seraient plus lisibles.

Si le nom du serveur ou du partage est faux, l'opération est abandonnée au bout de `KIKAN_STORAGE_DEADLINE_SEC`
(30 s par défaut) avec un message explicite, et la signature reste possible (dépôt différé).

SharePoint et DocuWare : un partage WebDAV (par exemple SharePoint sur site) ou un lecteur réseau SMB fonctionnent
directement. L'accès par l'API propre à SharePoint Online ou à DocuWare n'est pas géré (voir la feuille de route).
Alternative sans code : monter le partage sur le serveur Docker (volume `cifs`) et laisser `KIKAN_STORAGE_BACKEND=local`.

## Migrations de la base de données

Le schéma est géré par **Alembic** (`backend/migrations/`). Au démarrage, l'API applique automatiquement les
migrations en attente. Une base créée avant Alembic est reprise sans toucher à ses données.

Après une modification de `backend/app/models.py`, générer la migration correspondante (le conteneur est en lecture
seule : on monte le dossier des migrations), relire le fichier créé, puis redémarrer :

```bash
docker compose run --rm --no-deps -v "$PWD/backend/migrations:/app/migrations" api alembic revision --autogenerate -m "description du changement"
docker compose up --build -d api
```

Vérifier qu'aucune dérive n'existe entre le modèle et la base : `docker compose exec api alembic check`
(« No new upgrade operations detected » attendu).

## Structure du projet

```
backend/            API FastAPI
  app/
    models.py       modele de donnees (SQLModel)
    db.py           connexion et application des migrations au demarrage
    auth.py         authentification JWT, mots de passe, limitation des tentatives
    audit.py        journal d'audit
    signing.py      scellement PAdES
    pdfgen.py       generation des PDF
    routers/        endpoints (entites, users, assets, assignments,
                    lifecycle, import, reports, rgpd, stats, acces, auth, audit)
backend/migrations/ migrations Alembic du schema
frontend/           application React (Vite + Nginx, HTTPS)
import-modeles/     modeles CSV pour la reprise de l'existant
tests/              tests de securite, non-regression, audit des dependances
SPEC.md             cahier des charges detaille
SECURITY.md         modele de securite et liste de controle de production
docker-compose.yml
```

## Feuille de route

- **v0.2** : SSO Microsoft 365 (Entra ID), connecteurs API SharePoint Online et DocuWare (le dépôt sur lecteur
  réseau SMB et sur partage WebDAV existe déjà), synchro GLPI, rappels e-mail.
- Durcissement production : certificat reconnu, coffre pour la clé de scellement.

## Développement

Ce projet a été développé avec l'assistance d'une **intelligence artificielle**
(Claude, d'Anthropic), sous la direction et la relecture de l'auteur.

## Licence

Ce projet est distribué sous licence **GNU General Public License v3.0** (voir [LICENSE](LICENSE)).

Copyright (C) 2026 Gabriel Chollet.

Ce programme est un logiciel libre : vous pouvez le redistribuer et/ou le modifier selon les
termes de la GPLv3. Il est distribué dans l'espoir qu'il sera utile, mais SANS AUCUNE GARANTIE.
