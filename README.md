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
- **Remise signée** : génération d'un accusé PDF (matériel + charte informatique annexée), **signature manuscrite
  de l'employé sur tablette** (doigt, stylet ou souris), puis **scellement PAdES** (certificat auto-signé de
  l'organisation, horodatage RFC 3161 optionnel). Document infalsifiable et vérifiable.
- **Restitution signée** (A.5.11), avec la même signature manuscrite, conduite par l'informatique ou les RH.
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

## Signature manuscrite

À la remise, l'informatique ouvre l'**écran de signature** (bouton « Signer » de la page Remises ; « Restituer et
signer » pour une sortie), pensé pour une tablette. L'écran affiche le récapitulatif (salarié, matériel, charte), le
nom du salarié **repris de sa fiche et non modifiable**, une case d'acceptation obligatoire et le cadre de signature.
La signature est insérée dans le PDF, avec le nom, la date et l'heure (UTC) et le compte qui conduit la remise
(témoin), puis le tout est scellé.

- L'image est traitée comme une donnée non fiable : PNG uniquement, taille et dimensions bornées, trace réel exigé
  (signature vide ou réduite à un point refusée), protection contre les images piégées, ré-encodage sans métadonnées.
- La signature n'est conservée **que dans le PDF scellé** (donc supprimée avec lui par la purge RGPD) ; la base ne
  garde que des empreintes, le nombre de traits et la durée du tracé comme éléments de preuve.
- Une remise ne se signe qu'une seule fois.
- Par défaut la signature manuscrite est **obligatoire**. `KIKAN_SIGNATURE_MANUSCRITE_OBLIGATOIRE=false` autorise une
  simple confirmation (méthode `confirmation`, moins probante).

## Chartes informatiques

La charte est un **fichier déposé par l'informatique** (page **Chartes**) : document **Word (.docx)**, **PDF** ou
**Markdown**. Elle est **globale** (toutes les entités) ou **propre à une entité** ; une entité sans charte propre
hérite de celle de son entité parente, puis de la charte globale. Pour la mettre à jour, il suffit de déposer le
nouveau fichier : l'ancienne version est **archivée et conservée** (jamais supprimée), les documents déjà signés ne
changent pas.

- À la création d'une remise, la charte applicable au salarié est **jointe d'office** (un autre choix ou « aucune
  charte » est possible). À la signature, le serveur relit la charte, contrôle son empreinte et l'**annexe au PDF
  avant le scellement** ; la version et l'empreinte sont enregistrées comme preuve. L'écran de signature affiche la
  charte page par page.
- Les fichiers sont conservés dans le stockage choisi (volume, SMB ou WebDAV), avec le fichier d'origine.
- Un fichier déposé est une donnée non fiable : il est reconstruit en PDF propre (sans JavaScript, lien, action ni
  annotation) et contrôlé par un second moteur. Le Markdown accepte titres, listes, **gras** et *italique*.
- Les documents Word sont convertis par un **service isolé** (`converter`, LibreOffice) sans accès à Internet. S'il
  est arrêté, le dépôt Word est refusé avec un message clair (PDF et Markdown restent possibles). Pour s'en passer :
  retirer le service `converter` de `docker-compose.yml` et vider `KIKAN_WORD_CONVERTER_URL`.
- Limites : `KIKAN_MAX_CHARTE_MB` (10 Mo), 60 pages. Le texte Markdown est rendu avec les polices standard du PDF
  (lettres accentuées courantes, pas les emojis).

## Modification et suppression

Les pages Entités, Utilisateurs, Matériel et Accès applicatifs (catalogue) offrent **Modifier** (formulaire
pré-rempli) et **Supprimer** (confirmation en deux temps). Principe : **ce qui a une histoire ne se supprime pas, on le
désactive ou on l'archive** (traçabilité ISO 27001).

| Élément | Suppression autorisée si | Sinon |
|---|---|---|
| Entité | aucun salarié, actif, application, charte ni entité fille | la désactiver |
| Salarié (informatique seule) | jamais d'affectation ni d'accès | statut « sorti » via la page Sorties ; effacement définitif par la purge RGPD |
| Actif | jamais remis | statut « réformé » |
| Application | aucun accès attribué | la désactiver |

Le refus indique précisément ce qui bloque (« utilisé par 3 salariés... »). Règles de cohérence : les statuts
« affecté » et « rendu » d'un actif viennent de la remise et de la restitution, jamais d'une saisie ; un salarié passe
« sorti » uniquement par le départ (restitution signée) et n'est pas réactivé ; renommer le code d'une entité met à
jour ses filiales ; les boucles de parenté, les codes, matricules, numéros de série et identifiants internes en double
sont refusés. Le journal d'audit conserve les **noms des champs modifiés**, jamais leurs valeurs.

## Paramétrage

La page **Paramétrage** (informatique) regroupe :

- **Types d'actifs** et **services** : listes qui alimentent les menus du matériel et des fiches salariés (ajout,
  renommage, activation, suppression si inutilisé). Les listes sont **souples** : une valeur nouvelle saisie ou importée
  s'ajoute à la liste sans jamais bloquer, et une valeur qui ne diffère que par la casse reprend la graphie de la liste.
  Renommer met à jour tout le matériel ou toutes les fiches concernés.
- **Marques et modèles** : outil de **fusion** des variantes (Dell, DELL, Dell Technologies) vers un nom unique, avec
  détection des variantes probables, aperçu du nombre de matériels touchés et confirmation. Opération atomique, tracée.
- **Modèle de PDF** : nom de l'organisation, **logo** (PNG ou JPEG, 300 Ko, 1000 x 400 px, ré-encodé par le serveur),
  mentions légales et pied de page, appliqués à l'accusé de remise, à l'accusé de restitution et au rapport PDF, avec un
  aperçu. Le modèle en vigueur est **figé dans chaque document signé** et son empreinte est enregistrée avec la
  signature : le modifier ne change aucun document existant.
- **État du scellement** (lecture seule) : certificat (sujet, validité, empreinte), autorité de temps, signature
  manuscrite obligatoire, stockage et limites. Ces réglages restent dans le déploiement (`.env`), car ils touchent à la
  valeur probante des documents.

Les chartes, les applications, le stockage, la rétention RGPD et les comptes ont leur propre page.

## Import de l'existant

Page **Import** (informatique) : choix du type de fichier, aide colonne par colonne, **modèle CSV téléchargeable**
(aussi dans [`import-modeles/`](import-modeles/)), puis dépôt du fichier.

1. Le fichier est d'abord **simulé** : rien n'est écrit. Le rapport indique les lignes lues, à créer, ignorées et en
   erreur (avec le numéro de ligne et le problème), et le détail ligne par ligne.
2. Le bouton **Importer pour de bon** n'est actif que si la simulation est sans erreur (**tout ou rien**). L'import
   réel traite exactement le fichier simulé (contrôle par empreinte SHA-256).
3. Les erreurs se téléchargent en CSV pour corriger le fichier source.

L'import **ne fait que créer** : un élément déjà présent (même code d'entité, matricule, application ou accès) est
ignoré, ce qui permet de rejouer un fichier sans doublon. Format : UTF-8 ou Windows-1252 (export Excel), séparateur
`;` ou `,` (détectés), dates `AAAA-MM-JJ`, booléens `oui/non`. Ordre conseillé : entités, applications, utilisateurs,
matériel, affectations, accès. Plafonds : `KIKAN_MAX_IMPORT_MB` (5 Mo), `KIKAN_MAX_IMPORT_ROWS` (20 000 lignes).
Chaque simulation et chaque import sont tracés dans le journal d'audit (type, compteurs, empreinte, sans contenu).
Excel (.xlsx) est prévu en v0.2 (B8).

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
    importer.py     lecture CSV (encodage, separateur)
    rules.py        regles de modification et de suppression protegee
    catalogs.py     listes souples (types d'actifs, services)
    pdf_template.py modele de PDF (logo, mentions, pied de page)
    charte.py       chartes deposees : validation, normalisation PDF, portees, annexe
    docx_convert.py appel du service de conversion Word
    routers/        endpoints (entites, users, assets, assignments,
                    lifecycle, import, reports, rgpd, stats, acces, auth, audit)
backend/migrations/ migrations Alembic du schema
converter/          service isole de conversion Word vers PDF (LibreOffice, sans Internet)
frontend/           application React (Vite + Nginx, HTTPS)
import-modeles/     modeles CSV pour la reprise de l'existant
tests/              tests de securite, non-regression, audit des dependances
SPEC.md             cahier des charges detaille
SECURITY.md         modele de securite et liste de controle de production
docker-compose.yml
```

## Feuille de route

Détail et origine de chaque point dans [SPEC.md](SPEC.md) (section 13). La v0.1 est livrée.

- **v0.1.x - combler les écarts avec le SPEC (prioritaire)** : signature manuscrite à l'écran (A1, **fait**), gestion des
  chartes d'usage (A2, **fait**), page d'import CSV (A3, **fait**), modification et suppression dans l'interface (A4, **fait**), interface de
  paramétrage (A5, **fait**), gestion des comptes (A6), accès applicatifs dans le document de remise (A7), autocomplétion des
  modèles (A8).
- **v0.2 - identité, intégrations, automatisation** : SSO Microsoft 365 / Entra ID (B1), comptes cloisonnés par
  entité (B2), rappels par e-mail (B3), rapport mensuel automatique (B4), connecteur GLPI (B5), dépôt via l'API
  SharePoint Online et DocuWare (B6), besoins matériels saisis par les RH (B7), import et export Excel (B8).
- **v0.3 - pilotage** : statistiques exportables (C1), revue périodique des droits d'accès (C2), prévision des
  renouvellements (C3), étiquettes et QR codes (C4), pièces jointes (C5).
- **v0.4 - montée en échelle** : multi-organisations (D1), interface multilingue (D2), API publique (D3), webhooks (D4).
- **Sécurité et exploitation, en continu** : MFA locale (E1), certificat de scellement reconnu et clé dans un coffre
  (E2), journal d'audit infalsifiable (E3), révocation des sessions (E4), intégration continue, Dependabot et images
  publiées (E5), tests unitaires et d'interface (E6), sauvegarde et restauration (E7), accessibilité et thème
  sombre (E8).

## Développement

Ce projet a été développé avec l'assistance d'une **intelligence artificielle**
(Claude, d'Anthropic), sous la direction et la relecture de l'auteur.

## Licence

Ce projet est distribué sous licence **GNU General Public License v3.0** (voir [LICENSE](LICENSE)).

Copyright (C) 2026 Gabriel Chollet.

Ce programme est un logiciel libre : vous pouvez le redistribuer et/ou le modifier selon les
termes de la GPLv3. Il est distribué dans l'espoir qu'il sera utile, mais SANS AUCUNE GARANTIE.
