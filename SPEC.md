# SPEC - Kikan - suivi des actifs & remise de matériel signée

> **Kikan** (機器管理, *kiki-kanri*, « gestion des équipements »).
> Document de travail - version 0.1 du cahier des charges. Rédigé le 2026-10-27.

## 1. Objectif

Suivre, par utilisateur, le matériel qui lui est affecté (PC, smartphone, etc.), tracer
chaque **remise** par un **accusé de réception signé numériquement et scellé en PDF**
(sans papier), suivre les **échéances de renouvellement**, et produire un **reporting
mensuel** exportable.

L'outil soutient plusieurs contrôles de l'ISO/IEC 27001:2022 (Annexe A) :
- **A.5.9** - Inventaire des actifs d'information et associés.
- **A.5.10** - Usage acceptable des actifs (charte signée à la remise).
- **A.5.11** - Restitution des actifs (au départ de l'utilisateur).
- **A.5.18** - Droits d'accès (suivi des accès applicatifs par salarié).

> **Important** : un logiciel n'est pas « certifié ISO 27001 ». Il *facilite* la conformité
> du SMSI de l'organisation. Ne jamais le présenter comme certifié.

## 2. Périmètre

### Dans la v0.1
1. Gestion des utilisateurs et des actifs (saisie manuelle).
2. Catalogue de référence auto-construit + autocomplétion à la saisie.
3. Remise de matériel → génération PDF → signature → scellement PAdES → archivage.
4. Restitution / réforme du matériel.
5. Tableau de bord : qui détient quoi, renouvellements à venir.
6. Reporting (à l'instant T et mensuel), export **CSV** et **PDF**.
7. Interface de **paramétrage** (personnalisation maximale).
8. Rétention **RGPD paramétrable** avec prévisualisation des suppressions.
9. **Import initial du parc** par fichier **Excel/CSV** (colonnes définies).
10. **Cycle de vie employé** : formulaire d'**entrée** (RH) et flux de **départ** avec
    préparation automatique de la reprise du matériel.
11. **Rôles** RH et informatique (§5bis).
12. **Multi-entités / filiales** : rattachement des salariés à une entité, données et rapports
    filtrables par entité (pensé pour un usage open source multi-organisations).
13. **Accès applicatifs** : liste d'applications paramétrable, attribuée aux salariés (accès
    oui/non) avec un **champ libre** par application (niveau/rôle). Soutient A.5.18 (droits d'accès).

### Hors périmètre v0.1 (prévu plus tard)
- Interconnexion avec un outil d'inventaire externe (GLPI en priorité) via API REST.
- Statistiques de parc (modèles les plus distribués, etc.).
- Rappels automatiques par e-mail.
- Versionnage avancé de la charte d'usage.

## 3. Choix de signature (décidé)

**Signature électronique simple + PDF scellé (PAdES).** Niveau eIDAS « simple », suffisant
et défendable pour une remise de matériel interne.

**Modèle retenu** : la remise se fait en présence d'un **administrateur du service
informatique**, qui conduit la session sur une **tablette**. L'employé ne se connecte pas :
il est identifié par sélection dans la base, relit à l'écran, et **signe à la main sur la
tablette**. L'administrateur authentifié est le témoin de l'acte.

Ce qui fait la valeur de preuve :
- **Administrateur IT authentifié** qui conduit la remise (session connectée).
- **Signataire (employé)** identifié par sa fiche + **signature manuscrite à l'écran
  (obligatoire dans ce mode)**, insérée dans le PDF.
- **Faisceau de preuves** horodaté : qui (admin + employé), quand, depuis quel appareil
  (IP/agent), et l'**empreinte SHA-256 du document exact** accepté.
- **Scellement cryptographique du PDF entier** avec un **certificat auto-signé de
  l'organisation** (norme PAdES-B-T), + **horodatage d'une autorité de temps** (RFC 3161,
  service gratuit). Toute modification ultérieure casse le sceau → document infalsifiable
  et vérifiable.

> Certificat **auto-signé** (décidé) : le sceau est techniquement valide mais affiché
> « non approuvé » par les lecteurs PDF tant que le certificat racine de l'organisation n'est
> pas installé comme approuvé sur les postes. Acceptable pour un usage interne.

## 4. Modèle de données

### 4.1 `users` (utilisateurs / employés)
| champ | type | note |
|---|---|---|
| id | PK | |
| nom, prenom | texte | |
| entite_id | FK → `entites` | filiale / entité de rattachement (obligatoire) |
| email | texte | identifiant de connexion éventuel |
| service | texte | département |
| matricule | texte | optionnel |
| statut | enum | `prevu`, `actif`, `en_depart`, `sorti` |
| date_arrivee | date | saisie par les RH à l'entrée |
| date_sortie | date | fixée par les RH ; prépare la reprise + déclenche la rétention RGPD |
| cree_le, maj_le | datetime | |

### 4.2 `assets` (actifs)
| champ | type | note |
|---|---|---|
| id | PK | |
| type | FK → `asset_types` | PC portable, smartphone, écran… |
| marque | FK → catalogue | voir §5 |
| modele | FK → catalogue | voir §5 |
| numero_serie | texte | unique |
| identifiant_interne | texte | n° d'inventaire |
| date_achat | date | |
| fin_garantie | date | |
| echeance_renouvellement | date | pilote le suivi de renouvellement |
| statut | enum | `stock`, `affecte`, `rendu`, `reforme` |
| source | enum | `manuel`, `glpi`, … (pour synchro future) |
| id_externe | texte | id dans l'outil source ; nullable |
| notes | texte | |
| cree_le, maj_le | datetime | |

### 4.3 `assignments` (affectations / remises)
| champ | type | note |
|---|---|---|
| id | PK | |
| user_id | FK | |
| date_remise | datetime | |
| date_restitution | datetime | nullable |
| charte_version | FK → `policies` | charte d'usage signée |
| statut | enum | `en_cours`, `restitue` |
| cree_par | FK → compte admin | |

> Une remise peut porter **plusieurs actifs** → table de liaison `assignment_assets`
> (assignment_id, asset_id). Un même actif a un historique d'affectations.

### 4.4 `signatures` (preuves de signature)
| champ | type | note |
|---|---|---|
| id | PK | |
| assignment_id | FK | |
| signataire | texte | nom + email au moment de la signature |
| methode | enum | `confirmation`, `manuscrite_ecran` |
| horodatage | datetime | heure de l'autorité de temps si dispo |
| empreinte_doc | texte | SHA-256 du PDF signé |
| audit_json | json | IP, agent, étapes, consentement |
| ged_reference | texte | référence du PDF scellé : `<emplacement>:AAAA/fichier.pdf` (`local`, `smb` ou `webdav`) |

### 4.5 `entites` (filiales / entités)
| champ | type | note |
|---|---|---|
| id | PK | |
| nom | texte | ex. filiales de SICA Atlantique |
| code | texte | code court optionnel |
| parent_id | FK → `entites` | hiérarchie optionnelle (groupe → filiales) |
| actif | booléen | |

> **Multi-entités** : un salarié est rattaché à une entité. Les actifs peuvent aussi porter
> une entité (optionnel). Les rapports sont **filtrables par entité**. Conçu pour un usage
> open source par plusieurs organisations/filiales.

### 4.6 `applications` (catalogue d'applications - paramétrable)
| champ | type | note |
|---|---|---|
| id | PK | |
| nom | texte | ex. « ERP Cereo » |
| description | texte | optionnel |
| entite_id | FK → `entites` | nullable : globale si vide, sinon propre à une filiale |
| actif | booléen | |

### 4.7 `user_applications` (accès applicatifs d'un salarié)
| champ | type | note |
|---|---|---|
| id | PK | |
| user_id | FK | |
| application_id | FK | |
| acces | booléen | a accès ou non |
| note | texte | **champ libre** : ex. « administrateur », « mêmes droits que *<salarié remplacé>* » |
| attribue_par | FK → compte | RH ou informatique |
| date_maj | datetime | historisé |

> **Cardinalité** : relation **plusieurs-à-plusieurs** via cette table de liaison. Un salarié
> peut avoir **0, 1 ou N applications** (une ligne par application) ; une application peut être
> attribuée à plusieurs salariés.
>
> Soutient **A.5.18** (gestion des droits d'accès). On ne gère pas (encore) les droits *fins
> dans* l'application : le champ libre documente le niveau attendu.

### 4.8 Tables de paramétrage
- `asset_types` et `services` : listes de paramétrage (actif ou non), enrichies à la saisie et à l'import ; `settings` : modèle de PDF (organisation, mentions, pied de page, logo).
- `policies` : chartes d'usage **déposées en fichier** (PDF normalisé et fichier d'origine dans le stockage, empreintes SHA-256), portée (globale ou entité), version, statut active ou archivée ; une seule version active par portée.
- `settings` : paramètres globaux (voir §8).
- `accounts` : comptes applicatifs avec un **rôle** (voir §5bis). Les employés **ne se
  connectent pas** (ils signent sur la tablette tenue par l'informatique).

## 5. Catalogue de référence & autocomplétion

Objectif : accélérer les saisies suivantes en réutilisant ce qui a déjà été saisi.

- Tables de référence : `catalog_marques`, `catalog_modeles` (lié à une marque et à un type),
  alimentées **automatiquement** à chaque nouvelle saisie inédite.
- À la saisie d'un actif, les champs marque / modèle proposent une **autocomplétion** sur
  le catalogue existant (recherche partielle, insensible à la casse/accents).
- Si la valeur n'existe pas encore, elle est ajoutée au catalogue et devient disponible ensuite.
- Paramétrable : possibilité de nettoyer/fusionner des entrées de catalogue (doublons).

## 5bis. Rôles

- **RH** : gère le cycle de vie des **employés** - saisit les **arrivées** (formulaire d'entrée),
  fixe les **dates de départ** (prépare la reprise du matériel). Ne gère pas les actifs. **Ne
  fait pas signer la remise à l'arrivée**, mais **peut conduire la restitution signée à la sortie**.
- **Informatique** : gère les **actifs**, conduit la **remise signée à l'arrivée** et **peut
  aussi** conduire la **restitution à la sortie**, paramètre l'outil.
- **Accès applicatifs** (§6.5) : attribuables par **les RH ou l'informatique**.
- **Lecture seule** *(optionnel, plus tard)* : consultation et export des rapports (RSSI, direction).

> **Portée par entité** (B2, fait) : les comptes RH et lecture sont **globaux** ou **limités à une ou
> plusieurs entités** (leurs sous-entités sont incluses ; ex. une RH ne voit que sa filiale). Les comptes
> **informatique** sont toujours globaux. Les données sans entité ne sont visibles que des comptes globaux ;
> hors périmètre, un élément est « introuvable » (404). Un nouveau compte RH ou lecture n'a aucun périmètre
> tant qu'un administrateur n'en définit pas un. Les listes de suggestions (types, services, marques) et la
> charte globale restent communes.

Les employés ne sont **pas** des comptes connectés : ils sont des fiches (`users`) et signent
sur la tablette.

## 5ter. Authentification

- **Comptes nominatifs** : un compte par personne (jamais de compte generique partage),
  pour la responsabilite et l'audit (ISO A.5.16, A.8.5).
- **Connexion via Microsoft 365 (Entra ID)** en OpenID Connect / OAuth2 (flux Authorization
  Code + PKCE), avec la MFA du tenant. L'application est declaree comme app registration dans
  Entra ID (tenant id, client id, redirect URI, secret).
- **Acces reserve a deux groupes Entra** : seuls les membres de **Kikan-IT** (equipe admin
  informatique) et **Kikan-RH** (equipe RH) peuvent se connecter via Microsoft 365. Toute
  personne du tenant hors de ces deux groupes est **refusee** (aucun compte cree).
- **Correspondance des roles** : Kikan-IT -> role **informatique** ; Kikan-RH -> role **rh**.
  (Le role **lecture seule** reste optionnel, via compte local, hors SSO.)
- A la premiere connexion d'un membre autorise, le compte nominatif est cree/mis a jour a
  partir des claims (nom, email / UPN, identifiant oid).
- **Comptes locaux (mot de passe)** conserves uniquement en **secours (break-glass)** et en
  developpement ; a desactiver ou restreindre en production.
- Concerne les **utilisateurs de l'application** (equipes informatique / RH). Les salaries qui
  recoivent du materiel ne se connectent pas (ils signent sur la tablette).

> Etat actuel du code : authentification locale (JWT + mot de passe) et SSO Microsoft 365 facultatif
> (page Parametrage, onglet Authentification ; procedure dans docs/SSO.md).

## 6. Flux fonctionnels

### 6.0 Arrivée d'un employé (RH)
1. Les **RH** saisissent le nouvel employé via un **formulaire d'entrée** : **nom, prénom,
   filiale/entité**, service, **date d'arrivée**, éventuellement besoins matériels.
   Statut `prevu` → `actif`.
2. L'**informatique** voit l'arrivée (tableau de bord), distribue le matériel, puis fait signer
   l'**accusé de remise** à l'arrivée (§6.1).

### 6.1 Remise de matériel (informatique)
1. L'admin sélectionne un utilisateur, ajoute un ou plusieurs actifs (statut `stock` → `affecte`),
   choisit la version de charte d'usage.
2. Génération du **PDF d'accusé de réception** : identité, liste des actifs (type, marque,
   modèle, n° de série), **charte informatique annexée** (version figée), date, zone de signature.
3. Sur la **tablette**, l'employé relit et **signe à la main** ; l'administrateur IT (connecté)
   est témoin de l'acte.
4. Enregistrement du faisceau de preuves (§3), calcul de l'empreinte du document.
5. **Scellement PAdES + horodatage**, puis **dépôt du PDF scellé sur l'emplacement configuré** (volume
   local, **lecteur réseau SMB** ou **partage de fichiers web WebDAV**), rangé **par année** (`AAAA/`). Le PDF
   est d'abord écrit en local, déposé, relu et vérifié (SHA-256) ; si le partage est indisponible, la
   signature réussit et le dépôt est repris plus tard. Stockage de la **référence** + empreinte dans
   l'enregistrement `signatures`.
6. Le tableau de bord reflète la nouvelle détention.

### 6.2 Restitution / réforme (A.5.11)
- Restitution : actif `affecte` → `rendu`, `date_restitution` renseignée ; **accusé de
  restitution signé sur tablette** (symétrique de la remise - preuve du contrôle A.5.11).
  La restitution peut être conduite par **l'informatique** (contrôle des équipements) **ou
  par les RH** (contrairement à la remise à l'arrivée, réservée à l'informatique).
- Réforme : actif → `reforme` (fin de vie), sortie de l'inventaire actif mais conservé en historique.

### 6.3 Départ d'un employé (RH → informatique)
1. Les **RH** recherchent/sélectionnent le salarié et fixent sa **date de sortie**
   (statut `actif` → `en_depart`).
2. Le système **génère automatiquement la liste des équipements à récupérer** (tous les actifs
   `affecte` à cet employé), avec **échéance de reprise = date de sortie**, et **alerte
   l'informatique** (tableau de bord « départs à venir / matériel à récupérer »).
3. À la restitution physique, l'informatique traite chaque actif (§6.2, accusé signé).
4. Une fois tout rendu : statut employé `sorti` ; **déclenche le compteur de rétention RGPD** (§9).
5. **Garde-fou** : tout employé `en_depart` ou `sorti` détenant encore du matériel reste
   signalé jusqu'à restitution complète.

### 6.4 Import initial du parc (Excel/CSV)

Reprise de l'existant par **plusieurs fichiers CSV** (ou Excel) liés entre eux par des **codes**.
Modèles fournis dans `import-modeles/`.

**Règles de format :**
- Encodage **UTF-8**, séparateur **`;`** (compatible Excel FR ; `,` accepté, détection auto).
- Dates au format ISO **`AAAA-MM-JJ`** ; booléens **`oui`/`non`**.
- Les fichiers se relient par codes (code entité, matricule, identifiant matériel), pas par libellés.

**Fichiers et colonnes :**
- `entites.csv` : `code ; nom ; code_parent ; actif`
- `applications.csv` : `nom ; description ; code_entite ; actif`
- `utilisateurs.csv` : `matricule ; nom ; prenom ; email ; code_entite ; service ; date_arrivee ; statut`
- `materiel.csv` : `identifiant_interne ; type ; marque ; modele ; numero_serie ; date_achat ;
  fin_garantie ; echeance_renouvellement ; statut ; code_entite ; notes`
- `affectations.csv` : `matricule_utilisateur ; identifiant_interne_actif ; date_remise`
- `acces_applicatifs.csv` : `matricule_utilisateur ; application ; acces ; note`

**Ordre d'import** : entites -> applications -> utilisateurs -> materiel -> affectations ->
acces_applicatifs. Priorité pour une première reprise : utilisateurs + materiel + affectations.

**Validation** : chaque fichier est prévisualisé ; les lignes en erreur (code inconnu, date
invalide, doublon de n° de série...) sont signalées et rejetées sans bloquer les lignes valides.
Alimente au passage le catalogue marques/modèles (§5).

> Variante possible : un **fichier unique à plat** (une ligne par matériel avec les infos du
> salarié) ; plus simple à remplir mais inadapté aux salariés multi-applications. À arbitrer.

### 6.5 Accès applicatifs (RH ou informatique)
- Les **RH ou l'informatique** attribuent/retirent des applications au salarié (accès oui/non)
  et renseignent le **champ libre** (niveau : admin, « mêmes droits que *<salarié remplacé>* »…).
- Les changements sont **historisés** (qui, quand) pour la traçabilité.
- La liste des accès peut **optionnellement** être intégrée au document de remise à l'arrivée
  (instantané figé dans le PDF signé) - réglable dans le paramétrage.

## 7. Reporting

- **Rapport « à l'instant T »** : pour chaque utilisateur, le matériel en sa possession
  (filtrable par service, type, statut).
- **Rapport mensuel** : même contenu, figé à une date, pour le contrôle mensuel.
- **Exports** : **CSV** (données brutes) **et PDF** (mise en forme, horodaté, pour archive/audit).
- Génération manuelle en v0.1 ; planification automatique prévue plus tard.

## 8. Interface de paramétrage

Personnalisation maximale, sans toucher au code :
- Types d'actifs, marques/modèles du catalogue (ajout, fusion, nettoyage).
- **Liste des applications** (ajout/désactivation, portée par entité) + option d'inclusion des
  accès dans le document de remise.
- **Charte informatique** (texte, versions) - annexée au document de remise.
- Modèle de PDF d'accusé (logo, mentions légales, pied de page).
- Certificat de scellement (auto-signé) et autorité de temps.
- **Emplacement de dépôt des PDF** (local, lecteur réseau SMB, partage WebDAV), structure par année (`AAAA/`),
  état et test de connexion (page Stockage ; les identifiants restent dans l'environnement).
- **Durée de rétention RGPD** (§9).
- Champs optionnels des fiches (matricule, etc.), services/départements.
- Comptes applicatifs et **rôles** (RH / informatique / lecture seule - cf. §5bis).

## 9. RGPD - rétention paramétrable

- Paramètre `retention_apres_sortie_mois` (durée) ; défaut **12 mois**, modifiable (jamais codé en dur), ainsi que le **délai de grace** (30 jours par défaut)
  entre la mise en quarantaine d'un PDF et sa suppression définitive.
- Un utilisateur `sorti` est conservé jusqu'à `date_sortie + retention`.
- **Prévisualisation obligatoire avant suppression** : l'application de la règle **liste
  d'abord** les utilisateurs/données qui seront supprimés ; l'admin **valide** (ou non)
  avant toute suppression effective.
- Journaliser les suppressions (qui, quand, combien, empreinte SHA-256 des PDF) pour la traçabilité, **sans nom ni matricule**.
- **Purge par bouton réservé à l'informatique**, avec rappel par e-mail si elle n'est pas faite à l'échéance.
- **Partage SMB, WebDAV, volume local** : le PDF va dans `A_PURGER/` puis est supprimé par Kikan après le délai de grace.
- **SharePoint, DocuWare** : Kikan liste les documents, la suppression est faite par l'équipe de la GED puis confirmée dans Kikan.
- Détail : [docs/RGPD.md](docs/RGPD.md).
- Principe de minimisation : ne stocker que les données nécessaires au suivi.

## 10. Statistiques (plus tard)

- Modèles de PC / smartphones les plus distribués.
- Répartition par service, taux d'équipement, âge moyen du parc, renouvellements à venir.
- Mêmes exports CSV/PDF.

## 11. Pile technique (décidée)

Architecture **React (front) + FastAPI/Python (back) + PostgreSQL**. Le back est en Python
parce que le cœur du produit est le **scellement PAdES + horodatage**, dont la meilleure
brique open source est **pyHanko** (Python) ; la garder native évite un composant fragile.

- **React** - interface (front) ; adaptée au paramétrage riche et à l'autocomplétion.
- **FastAPI** (Python) - API REST.
- **PostgreSQL** - base de données (cohérent avec l'environnement Docker existant : LiteLLM, n8n).
- **SQLModel / SQLAlchemy** - ORM ; **Alembic** - migrations appliquées automatiquement au démarrage (reprise d'une base préexistante par marquage de la révision initiale).
- **pyHanko** - signature/scellement PAdES, horodatage RFC 3161.
- **WeasyPrint** (HTML→PDF) ou **ReportLab** - génération des PDF.

### 11.1 Déploiement (Docker)

L'application doit être **entièrement conteneurisée**, déployable via `docker compose`,
sur le modèle de LiteLLM et n8n déjà en place.

Services :
- **`web`** - le front React (build statique servi par Nginx), ou servi par l'API en v0.1.
- **`api`** - FastAPI (uvicorn/gunicorn).
- **`db`** - PostgreSQL, données sur un **volume nommé** persistant.

Déploiement **on-premise** (hébergé en interne, pas de cloud).

Points d'attention :
- **Stockage des PDF** : les PDF scellés sont déposés sur un **lecteur réseau (SMB)** ou un **partage de
  fichiers web (WebDAV)** de l'organisation, ou restent sur le volume local ; la base ne garde que la
  **référence** + l'empreinte SHA-256, recontrôlée à chaque lecture (détection d'altération). Le volume local
  sert de tampon durable : il n'est purgé qu'après un dépôt vérifié, et conserve le document si le partage est
  indisponible (reprise automatique).
- **Base** PostgreSQL sur **volume nommé** persistant, avec sauvegardes.
- **Secret de signature** : la **clé privée du certificat** n'est **jamais** dans l'image ni
  dans le dépôt ; elle est montée en *secret*/volume au démarrage, et lue via variable d'env.
- **`.env`** pour les secrets (mot de passe Postgres, clé maître, accès au partage), comme pour LiteLLM.
- `restart: unless-stopped` + *healthchecks* ; l'`api` attend que `db` soit saine.
- **Exposition réseau** : accessible sur le **réseau local** (la **tablette de signature** s'y
  connecte au moment de la remise) ; pas d'exposition Internet.
- Images reproductibles (versions épinglées), build multi-étapes pour un front léger.

## 12. Sécurité

Le détail des mesures, des risques acceptés et de la liste de contrôle de production figure dans
`SECURITY.md`. Principes retenus :

- **Comptes nominatifs** (un par personne) ; authentification et rôles (§5ter). Cible : SSO
  **Microsoft 365 / Entra ID** (OIDC) avec rôles par groupes ; auth locale en secours/dev.
- **Aucun secret par défaut** : clé de session et mot de passe initial aléatoires ; refus de démarrer
  en production sans clé solide.
- **Protection contre la force brute** (verrouillage temporaire) et politique de mots de passe.
- **HTTPS obligatoire**, en-têtes de sécurité (CSP stricte, HSTS...), CORS en liste blanche.
- **Journal d'audit** des écritures, refus d'accès et connexions (sans corps de requête), non modifiable
  par l'API.
- Entrées neutralisées : requêtes paramétrées, échappement dans les PDF, protection des exports CSV
  contre l'injection de formules, imports plafonnés.
- Conteneurs durcis (non-root, lecture seule, capacités retirées), base non exposée.
- Archive des PDF scellés en stockage immuable ; empreinte en base pour détection d'altération.
- Sauvegardes de la base et des archives.
- Clé privée du certificat de scellement hors base et hors image, droits restreints.
- Dépendances figées et auditées ; tests de sécurité et de non-régression rejoués à chaque mise à jour.

## 13. Feuille de route

Liste validée le 2026-10-28. Origines : **SPEC** (déjà prévu), **Écart** (promis par le SPEC mais non
réalisé dans la v0.1), **Prop.** (proposition). Statut : à faire, sauf mention **Fait**.

### v0.1 (livrée)

Périmètre du §2, réalisé : cycle de vie salarié, remises et restitutions signées et scellées, import CSV (API),
reporting CSV et PDF, statistiques, accès applicatifs, rétention RGPD, authentification et rôles, journal
d'audit, stockage local, SMB et WebDAV, migrations Alembic. Les écarts avec le SPEC sont repris en v0.1.x.

### v0.1.x - combler les écarts avec le SPEC (prioritaire)

| # | Fonctionnalité | Origine |
|---|---|---|
| A1 | **Signature manuscrite à l'écran** (tactile ou souris) insérée dans le PDF, avec le signataire choisi depuis sa fiche plutôt que saisi librement. **Fait (2026-10-28)** : remise et restitution, écran tablette, image assainie côté serveur, nom déduit de la fiche, signature unique, preuves enregistrées (§3) | Écart |
| A2 | **Gestion des chartes d'usage** : dépôt d'un fichier (Word, PDF ou Markdown) par l'informatique, globale ou propre à une entité (héritage entité, parent, globale), versions archivées, jointe d'office à la remise et annexée au PDF signé. **Fait (2026-10-28)** | Écart |
| A3 | **Page d'import CSV** dans l'interface (aperçu, rapport d'erreurs, modèles téléchargeables). **Fait (2026-10-28)** : simulation puis import réel du même fichier (empreinte), tout ou rien, rapport par ligne, erreurs exportables, modèles générés, ré-import sans doublon, audit | Écart |
| A4 | **Modification et suppression dans l'interface** (entités, salariés, matériel, applications). **Fait (2026-10-28)** : suppression refusée avec message précis si l'élément a une histoire (désactiver ou archiver à la place), statuts cohérents avec la remise et la restitution, hiérarchie d'entités protégée, doublons refusés, champs modifiés journalisés ; catalogue des applications géré dans l'interface | Écart |
| A5 | **Interface de paramétrage** : types d'actifs, services, fusion des marques et modèles, modèle de PDF (logo, mentions). **Fait (2026-10-28)** : listes souples, fusion avec aperçu, modèle de PDF figé et empreinte dans chaque document signé, état du scellement en lecture seule | Écart |
| A6 | **Gestion des comptes dans l'interface** (créer, désactiver, réinitialiser). **Fait (2026-10-28)** : comptes nominatifs (nom, e-mail), mot de passe provisoire affiché une seule fois et changement imposé, sessions révoquées au changement de mot de passe, de rôle ou à la désactivation, identifiant contrôlé et unique sans tenir compte de la casse, dernière connexion | Écart |
| A7 | **Option d'inclure les accès applicatifs** dans le document de remise. **Fait (2026-10-28)** : réglage global (désactivé par défaut), instantané figé des accès accordés sur applications actives, empreinte contrôlée entre l'écran et la signature, preuve enregistrée | Écart |
| A8 | **Autocomplétion des modèles** dans le formulaire matériel. **Fait (2026-10-28)** : composant de saisie assistée (type, marque, modèle, service), recherche insensible à la casse et aux accents, modèles filtrés par marque et classés par type, graphie canonique à l'enregistrement et à l'import ; catalogue déduit du matériel | Écart |

### v0.2 - identité, intégrations, automatisation

| # | Fonctionnalité | Origine |
|---|---|---|
| B1 | **SSO Microsoft 365 (Entra ID)** : groupes `Kikan-IT` et `Kikan-RH`, comptes nominatifs, MFA du tenant, comptes locaux en secours (§5ter). **Fait (2026-10-28)** : option activable, rôles d'application Entra attribués aux groupes, jeton vérifié de bout en bout, création et resynchronisation du rôle à chaque connexion, liaison explicite des comptes locaux, mode de secours, durée de session réglable (E4) ; testé contre un faux fournisseur d'identité, **à valider sur le tenant réel** (docs/SSO.md) | SPEC |
| B2 | **Comptes cloisonnés par entité** (global ou limité à une ou plusieurs filiales). **Fait (2026-10-28)** : les comptes RH et lecture sont globaux ou limités à des entités (sous-entités incluses), les comptes informatique sont toujours globaux (administrateurs) ; filtrage serveur sur toutes les lectures et écritures (404 hors périmètre), nouveaux comptes RH et lecture sans périmètre tant qu'il n'est pas défini, pages d'administration réservées à l'informatique, test d'inventaire des routes | SPEC |
| B3 | **Rappels par e-mail** : renouvellements, départs à venir, matériel non restitué. **Fait (2026-10-29)** : serveur SMTP externe configurable (relais interne sans authentification possible, STARTTLS, SSL), un récapitulatif par destinataire et par jour, relances espacées sans doublon, destinataires cloisonnés par périmètre (B2), adresse de liste, planificateur interne avec verrou, message de test, aperçu et envoi immédiat, profil Mailpit de test | SPEC |
| B4 | **Rapport mensuel automatique** : généré, archivé dans le stockage et envoyé par e-mail. **Fait (2026-10-29)** : rapport envoyé chaque mois à l'informatique et à la liste (lien vers Kikan, pièce jointe Excel ou PDF facultative) ; l'**archivage dans le stockage** n'est pas fait (décision du 2026-11-01 : seuls les PDF scellés vont dans SharePoint et DocuWare) | SPEC |
| B5 | **Connecteur GLPI** (synchronisation du matériel et des salariés, champs `source` et `id_externe`). **Fait (2026-10-31)** : API d'import par jetons (`/api/v1`, hachés, expirables, droits et périmètre limités, simulation, lots, idempotente) et connecteur GLPI à la demande, ordinateurs et téléphones avec numéros de série, import sur sélection et export des salariés et de leur matériel vers GLPI, sans suppression ni écrasement, testé contre GLPI 10.0.28, 11.0.12 et 12.0.1 ; la création de tickets reste à faire | SPEC |
| B6 | **Dépôt via l'API SharePoint Online et DocuWare** (SMB et WebDAV existent déjà). **Fait (2026-11-01)** : deux moteurs de stockage de plus (un seul actif à la fois), uniquement pour les PDF scellés (les chartes restent en local) : SharePoint par Microsoft Graph (`Sites.Selected`, fichiers de plus de 4 Mio par blocs) et DocuWare par l'API REST (compte de service, champs d'index à associer, aucune donnée nominative sans association explicite) ; même tampon local, vérification d'empreinte et reprise que SMB et WebDAV ; outil de copie vers le moteur actif sans suppression ; testés contre de faux services, **à valider sur un vrai tenant** (docs/SHAREPOINT.md, docs/DOCUWARE.md) | SPEC |
| B7 | **Besoins matériels saisis par les RH** à l'arrivée, repris par l'informatique. **Fait (2026-10-30)** : page Besoins, quatre statuts (demande, en préparation, satisfait, annulé), type pris dans la liste du Paramétrage, périmètre des RH respecté, proposition automatique des besoins ouverts à la création d'une remise et solde avec elle, compteur du tableau de bord, rappel e-mail des arrivées proches non traitées, purge RGPD | SPEC |
| B8 | **Import et export Excel (.xlsx)** en plus du CSV. **Fait (2026-10-28)** : import avec le même parcours que le CSV (première feuille visible, lignes vides ignorées, formules jamais évaluées), modèles Excel, export du rapport de détention, protections contre archives et XML piégés, macros et liens externes | Prop. |

### v0.3 - pilotage

| # | Fonctionnalité | Origine |
|---|---|---|
| C1 | **Statistiques exportables** (CSV et PDF), avec filtres par entité et période | SPEC |
| C2 | **Revue périodique des droits d'accès** : rapport « qui a accès à quoi » et campagne de validation (ISO A.5.18) | Prop. |
| C3 | **Prévision des renouvellements** avec budget estimé | Prop. |
| C4 | **Étiquettes et QR codes** sur le matériel, recherche par scan | Prop. |
| C5 | **Pièces jointes** au matériel (facture, garantie) | Prop. |

### v0.4 - montée en échelle

| # | Fonctionnalité | Origine |
|---|---|---|
| D1 | **Multi-organisations / multi-sites** | SPEC |
| D2 | **Interface multilingue** (français et anglais) | Prop. |
| D3 | **API publique documentée** avec jetons d'accès | Prop. |
| D4 | **Webhooks** vers des outils externes (par exemple n8n) | Prop. |

### Sécurité et exploitation (en continu)

| # | Fonctionnalité | Origine |
|---|---|---|
| E1 | **MFA locale (TOTP)** pour les comptes de secours | Prop. |
| E2 | **Certificat de scellement reconnu**, clé dans un coffre, horodatage RFC 3161 activé par défaut | SPEC |
| E3 | **Journal d'audit infalsifiable** (chaîné) et export vers un SIEM ou syslog | Prop. |
| E4 | **Révocation des sessions** et durée de session paramétrable | Prop. |
| E5 | **GitHub Actions** (tests, audit des dépendances), **Dependabot**, versions publiées et image Docker prête à l'emploi. **Fait (2026-10-29)** : CI à chaque envoi et demande de fusion (hygiène du dépôt, audit pip et npm, compilation du front, toutes les suites sur la pile complète, sauvegarde de bout en bout, construction des images et analyse Trivy), Dependabot hebdomadaire (pip, npm, Docker, compose, Actions), publication à l'étiquette `vX.Y.Z` de quatre images sur GHCR et de la version GitHub, `docker-compose.ghcr.yml`, `tests/run_all.sh`, CHANGELOG ; **première exécution réelle de la CI à constater après l'envoi** | Prop. |
| E6 | **Tests unitaires** (pytest) et tests automatisés de l'interface | Prop. |
| E7 | **Sauvegarde et restauration** documentées et testées. **Fait (2026-10-29)** : sauvegarde chiffrée (`age`, clé publique) de la base, des PDF scellés locaux, des clés, du certificat HTTPS et du `.env` vers un partage SMB ou un dossier, planifiée chaque nuit, rétention 30 jours plus la première de chaque mois pendant 12 mois, restauration guidée avec contrôle des empreintes, page et alerte dans l'application, test de bout en bout (restauration dans une instance vierge) | Prop. |
| E8 | **Accessibilité** (RGAA/WCAG) et thème sombre | Prop. |

## 14. Décisions

**Tranchées :**
- Nom : **Kikan** (機器管理).
- Pile : **React + FastAPI (Python) + PostgreSQL** (§11).
- Signature : **simple + scellement PAdES-B-T**, **certificat auto-signé** de l'organisation (§3).
- **Signature sur tablette** conduite par un admin IT ; l'employé ne se connecte pas (§3, §6.1).
- **Comptes nominatifs**, cible **SSO Microsoft 365 (Entra ID)** reserve aux groupes
  **Kikan-IT** (informatique) et **Kikan-RH** (rh) ; hors de ces groupes = refuse ; auth locale
  (mot de passe) en secours/dev (§5ter).
- Déploiement **on-premise**, conteneurs Docker (§11.1).
- **Stockage des PDF** sur **lecteur réseau (SMB)** ou **partage de fichiers web (WebDAV)**, **un dossier
  par année** (`AAAA/`) ; dépôt de fichier, sans API propriétaire (§6.1, §11.1). Les connecteurs API
  SharePoint Online et DocuWare sont reportés en v0.2.
- **Charte informatique annexée** au document de remise (couvre A.5.10), versionnée et figée
  dans le PDF signé.
- **Multi-entités / filiales** : salarié rattaché à une entité ; rapports filtrables par
  entité ; pensé pour un usage open source multi-organisations (§4.5).
- **Rôles** : **RH** (cycle de vie employé : entrée, date de départ) et **informatique**
  (actifs, signatures) ; lecture seule optionnelle plus tard (§5bis).
- **Qui fait signer** : remise à l'**arrivée** = informatique ; restitution à la **sortie** =
  informatique **ou** RH.
- **Cycle de vie employé** : formulaire d'entrée (nom, prénom, filiale, service, date d'arrivée) ;
  flux de départ qui **génère la liste du matériel à récupérer** à la date de sortie et alerte
  l'informatique (§6.0, §6.3).
- **Accusé de restitution signé** à la sortie, symétrique de la remise (A.5.11) (§6.2).
- **Accès applicatifs** : liste d'applications paramétrable, attribuée par RH ou informatique,
  avec **champ libre** par application ; soutient A.5.18 (§4.6, §6.5).
- **Reprise de l'existant** : import **Excel/CSV** à colonnes définies (§6.4).
- **Feuille de route** v0.1.x à v0.4 et sécurité en continu : liste validée le 2026-10-28 (§13).

**Ouvertes :**
1. **Formulation juridique** du document combinant réception du matériel + acceptation de la
   charte informatique (à faire relire RH / juridique).
2. Emplacement exact du dépôt (serveur de fichiers SMB ou partage WebDAV, nom du partage, compte de
   service dédié) et besoin éventuel d'un connecteur API SharePoint Online / DocuWare.
3. Format d'import proposé (§6.4, modèles dans `import-modeles/`) à valider : plusieurs
   fichiers liés, ou fichier unique à plat ?
4. **Portée des comptes par entité** : accès global ou restreint à une/des filiale(s) dès la v0.1 ?

