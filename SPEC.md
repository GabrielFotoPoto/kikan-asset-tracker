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
| type | texte | `remise` (par défaut) ou `echange` (renouvellement, §6.2bis) |
| cree_par | FK → compte admin | |

> Une remise peut porter **plusieurs actifs** → table de liaison `assignment_assets`
> (assignment_id, asset_id, **date_retour**). Un même actif a un historique d'affectations. La **date de retour est portée par chaque actif** :
> une affectation ne se clôture que lorsque tout son matériel est parti (restitution partielle ou échange partiel).
> `echange_retours` (assignment_id, asset_id, destination) rattache à l'échange l'ancien matériel restitué et son devenir (`rendu`, `stock`, `reforme`).
> `echeance_reports` (asset_id, ancienne, nouvelle, motif, par, le) conserve l'**historique des reports** d'échéance de renouvellement (le motif y reste, jamais dans le journal d'audit).

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
- `couts_remplacement` : **coût de remplacement estimé** (C3) par type de matériel, avec exception possible pour un modèle précis (marque et modèle) ; montant en **centimes d'euro** (entier), clé unique insensible à la casse (type, marque, modèle) ; modifiable par l'informatique seule.
- `besoin_categories` : catégories de besoin cochées par les RH, avec leurs **gammes** (liste JSON, 10 au plus ; ex. Normal, Pro, XL) ; `besoins` : un souhait par salarié (catégorie, **gamme** facultative parmi celles de la catégorie, quantité, précisions, date souhaitée, statut).
- `asset_types` et `services` : listes de paramétrage (actif ou non), enrichies à la saisie et à l'import ; `settings` : modèle de PDF (organisation, mentions, pied de page, logo) et **icône de l'application** (`app_icone`, PNG réencodé).
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
- **Besoins de matériel** : les RH n'expriment qu'un **souhait** (création, depuis le formulaire d'entrée) ; le suivi est à l'informatique, sans accès pour les RH.
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
   filiale/entité**, service, **date d'arrivée**, éventuellement **souhaits de matériel** (catégorie et gamme ; elles ne choisissent pas le matériel définitif).
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

### 6.2bis Renouvellement du matériel d'un salarié en poste (échange)
- **Décision et déclenchement : informatique seule.** Aucune demande ne passe par les RH ou le salarié. L'`echeance_renouvellement` n'est qu'un **repère** :
  l'informatique renouvelle quand elle le décide, **avant** l'échéance (le besoin a changé) comme **après** (échéance dépassée mais prolongée).
- **Une seule opération, un seul document signé** (« Accusé d'échange de matériel ») : le nouveau matériel est **remis** et l'ancien **restitué** ensemble.
  Deux tableaux (remis, restitué), une déclaration, **une signature manuscrite** sur la tablette, scellement PAdES, **un seul numéro** de document du salarié.
- **Écran** (`/renouveler`, depuis la page Matériel ou Utilisateurs) : à gauche le matériel détenu (on coche ce qui est rendu, avec son **devenir** : *rendu* à traiter
  ensuite, *retour en stock* ou *à réformer*) ; à droite le matériel en stock à remettre ; besoins ouverts du salarié soldés avec l'échange ; **charte au choix, décochée
  par défaut** (le salarié l'a signée à son arrivée) ; motif facultatif.
- **Tout ou rien, en une fois sur la tablette** : tant que la signature n'est pas enregistrée, aucun statut ne change (pas d'état « en attente »). Verrous sur le salarié puis sur
  tout le matériel concerné ; un second échange simultané des mêmes matériels est refusé (409). Réservé à un salarié au statut **actif**.
- **Effets** : nouveaux actifs `affecte` (nouvelle affectation de type `echange`) ; anciens actifs `rendu`, `stock` ou `reforme` avec leur **date de retour** ; les affectations
  entièrement restituées sont clôturées, les autres restent ouvertes (échange partiel).
- **Preuves** : type `echange` dans le faisceau de preuves (matériel remis et restitué, devenirs, affectations clôturées, témoin, IP, empreintes du modèle de PDF, de la charte et des accès).
- Statistiques de mouvements : une restitution est comptée **par actif**, à sa date de retour (restitution classique et échange).
- **Page « Renouvellements »** (informatique, `/renouvellements`) : matériel **en stock ou affecté** dont l'échéance est dépassée ou tombe dans l'horizon choisi (dépassée seulement,
  1, 3, 6 ou 12 mois ; filtre d'entité), avec détenteur, situation (*en retard*, *ce mois-ci*, *à venir*) et dernier report ; actions **Renouveler** (échange) et **Reporter**.
- **Report d'échéance** : nouvelle date (aujourd'hui ou plus tard : report **ou avancement**), ou *aucun renouvellement prévu* ; **motif facultatif** ; historique conservé ; trace dans le journal
  par les dates seulement. Impossible pour un matériel rendu ou réformé.
- Un matériel **rendu ou réformé n'est plus à renouveler** : il sort des prévisions, des rappels, des statistiques d'échéances et de la page Renouvellements.

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

### 6.3bis Parcours guidés en étapes (départ, puis remise et renouvellement)

*Révisée le 2026-11-04 après analyse critique : correction de la date de purge, précision sur l'identification du matériel par les RH, voie « matériel non restitué »,
suppression du compteur « k sur N ».*

**Objectif.** Étendre au départ, à la remise et au renouvellement le principe du parcours d'arrivée (§6.0) :
l'utilisateur voit où il en est, ce qui reste à faire, qui doit agir, et accède en un clic à la prochaine action.

**Découpage en lots.**

| Lot | Contenu | Statut |
|---|---|---|
| 1 | Composant partagé `EtapesParcours` (extrait de `Arrivant.jsx`), **parcours de départ en lecture seule** | **réalisé** (PR #99, fusionnée le 2026-11-04) |
| 1bis | Voie d'exception : **constat de matériel non restitué** et **clôture d'un départ sans matériel** (écritures, nouvelle valeur de statut, migration) | après validation du lot 1 |
| 2 | Remise guidée : salarié, besoins ouverts, charte, matériel, signature, PDF | après le lot 1bis, **à décider après mesure** de l'usage des lots 1 et 1bis ; point à trancher avant : où vit le brouillon de l'assistant (voir « Points à valider ») |
| 3 | Indicateur d'étapes, en lecture seule, sur le renouvellement existant | **abandonné (décision du 2026-11-04)** : le renouvellement est une opération unique à un seul document, un indicateur d'étapes n'apporterait presque rien |

Hors périmètre : revue des accès, fiche salarié 360° (abandonnée). Le détail ci-dessous porte sur les lots 1 et 1bis ; le lot 2
reprendra les mêmes principes et fera l'objet d'un complément avant sa réalisation (le lot 3 est abandonné).

**Principes (security et privacy by design).**
- **Aucune nouvelle donnée stockée par le lot 1** : l'avancement est calculé à partir de données existantes, comme pour l'arrivée. Pas de
  nouvelle table ni de migration. Les nouvelles données du lot 1bis sont décrites et justifiées dans sa propre section.
- **Lecture seule pour le lot 1** : les routes du parcours n'écrivent rien. Toute écriture passe par les routes existantes et leurs contrôles
  (lot 1) ou par les routes dédiées du lot 1bis, avec leurs propres contrôles.
- **Droits appliqués côté serveur**, jamais seulement masqués dans l'interface. Un salarié hors portée renvoie **404**, réponse
  identique à celle d'un identifiant inexistant (pas d'énumération).
- **Minimisation** : seul le nécessaire est renvoyé (tableau ci-dessous). Le serveur **omet** les données non autorisées pour le
  rôle, il ne les masque pas à l'écran.
- **Jamais plus que l'existant** : pour un même rôle, le parcours ne révèle pas plus de données que les écrans et routes déjà en place.
  Quand une route existante en révèle davantage que la règle voulue, elle est signalée et traitée à part.

**Étapes du parcours de départ.**

| # | Étape | Qui | Fait quand | Nature |
|---|---|---|---|---|
| 1 | Départ déclaré | RH ou informatique | statut `en_depart` ou `sorti`, avec une date de sortie | action |
| 2 | Matériel à récupérer | automatique | liste établie ; sans objet s'il n'y a aucun matériel détenu | informative |
| 3 | Matériel récupéré | informatique (ou RH) | plus aucun actif au statut `affecte` pour le salarié : restitution signée, ou constat de non-restitution (lot 1bis), ou aucun matériel au départ | action |
| 4 | Accès applicatifs retirés | RH ou informatique | plus aucun accès actif | **informative** |
| 5 | Salarié sorti | automatique (restitution signée, constat ou clôture) | statut `sorti` | informative |
| 6 | Purge RGPD possible | informatique uniquement | à partir de `date_sortie` + durée de rétention (voir ci-dessous) | informative |

- L'**étape courante** est la première étape d'**action** (1 ou 3) non faite. Le parcours est **terminé** quand le salarié est `sorti`.
- **Étape 3 : restant, pas « k sur N ».** Tant qu'il reste du matériel, l'étape affiche « r matériel(s) restant(s) » (nombre d'actifs `affecte`,
  calculé à la lecture). **Aucun compteur « k sur N »** : il exigerait une date de déclaration du départ, que l'on **ne stocke pas** (décision), et N
  varie si du matériel est remis après la déclaration ou rendu en plusieurs signatures. La restitution signée reste la seule preuve de
  restitution (A.5.11) ; le détail de l'étape distingue « restitué (signé) », « non restitué (constat) » et « aucun matériel ».
- **Salarié sans matériel** : l'étape 2 est « sans objet » et l'étape 3 est faite d'office. Le seul chemin existant vers `sorti` est la signature
  d'une restitution ; sans matériel, le départ ne peut donc pas se clôturer aujourd'hui. Le lot 1 affiche un message d'attente (aucune action proposée). Message affiché : « Aucun matériel détenu : la clôture du départ n'est pas encore disponible dans
  l'application » (sans terme interne ; aligné dans le code par la PR #101). Le lot 1bis ajoute la clôture.
- **Retard** : si la date de sortie est dépassée, que le salarié est encore `en_depart` et qu'il reste du matériel, l'étape 3 affiche une pastille
  « en retard de n jour(s) » (calculée, rien de stocké).
- **Fin avec réserve** : quand le salarié est `sorti` mais qu'il reste des accès actifs ou du matériel au statut non restitué, le parcours est
  affiché « Terminé, avec réserve : n accès à retirer ; n matériel(s) non restitué(s) », **visuellement distinct** du « Terminé » complet
  (texte et icône, pas seulement la couleur). Ces réserves ne bloquent pas la fin du parcours. Elles prolongent la revue des accès
  (A.5.18), qui signale déjà l'accès d'un salarié sorti comme anomalie, et les responsabilités après la fin du contrat (A.6.5).
- L'étape 4 est **informative** : elle n'empêche pas le parcours d'être terminé. Le serveur ne renvoie que le **nombre** d'accès restants (pas
  les noms d'applications) ; le lien secondaire « Voir les accès » mène à l'écran existant, avec ses propres droits. Jamais proposé comme
  prochaine action.
- **Étape 6 : date.** Elle affiche `date_sortie` + durée de rétention (`retention_apres_sortie_mois`), soit la date à partir de laquelle la purge
  est possible (`purge.py` et `rgpd.py` : « suppression prévue »). Le **délai de grâce** (`purge_delai_grace_jours`) ne s'ajoute pas à cette date :
  il court **après** le clic sur la purge, entre la mise en quarantaine d'un PDF et sa suppression définitive (§9). La purge restant un bouton
  manuel, l'étape se libelle « purge possible à partir du », jamais « purge prévue ». L'étape reste **toujours `a_venir`** (jamais `fait`) ; le libellé devient « Purge possible depuis le <date> » une fois la date passée.
- L'étape 6 n'est **renvoyée par le serveur qu'au rôle informatique** ; elle est absente de la réponse pour les RH et le rôle lecture.
- **Salarié sans départ déclaré** (statut `prevu` ou `actif`) : la route répond 200 ; l'étape 1 est la courante et les autres sont « à venir ».
  Un salarié inexistant, hors portée ou purgé répond 404.

**API.** `GET /parcours/depart/{user_id}`, dans un routeur sur le modèle d'`arrivee.py`. Les lots 2 et 3 réutiliseront le même schéma sous
`/parcours/remise/...` et `/parcours/renouvellement/...`. La route d'arrivée `/arrivee/{user_id}` **ne change pas** (aucun changement de
comportement) ; le petit assistant `_etape(cle, titre, qui, etat, detail)` d'`arrivee.py` est extrait dans un module partagé, sans en modifier
le résultat.
- Compte authentifié obligatoire (401 sinon). Rôles : tous en lecture, y compris le rôle lecture.
- Portée par entité : `visible_user(...)`. Hors portée ou inexistant : **404 identique**, corps identique.
- Réponse : `salarie`, `etapes[]` (`cle`, `titre`, `qui`, `etat` parmi `fait`, `courante`, `a_venir`, `sans_objet`, `detail`), `etape_courante`,
  `prochaine_action`, `materiel_a_recuperer` (`id`, `identifiant_interne`, `type`, `marque`, `modele`, `numero_serie`),
  `acces_restants` (nombre), `reserves`, `message_attente`, `journal`. `identifiant_interne` est l'étiquette d'inventaire, utile quand un matériel n'a pas
  de numéro de série ; `message_attente` n'est renseigné que pour un salarié en départ sans matériel détenu.
- `prochaine_action` porte un champ `autorise`, calculé côté serveur d'après le rôle (vrai pour RH et informatique, faux pour lecture). Le bouton n'apparaît que si `autorise` est vrai ;
  la route d'écriture appelée refuse de toute façon un rôle non habilité (contrôle existant, non modifié).
- `user_id` est un entier ; aucune entrée libre. Aucune écriture en base.
- Liens d'action existants : `/sorties?user=...`, `/signer/restitution/{id}`.
- **Nombre de requêtes borné** : le calcul d'un parcours fait un nombre fixe de requêtes, indépendant du nombre d'actifs (pas de requête par actif).

**Données renvoyées (minimisation).**

| Donnée | RH | Informatique | Lecture |
|---|---|---|---|
| Nom, prénom, service, entité, statut, date de sortie | oui | oui | oui |
| Matricule | non | non | non |
| Matériel à récupérer : type, marque, modèle et **numéro de série** (identification formelle) | oui | oui | oui |
| Nombre d'accès restants (sans nom d'application) | oui | oui | oui |
| Étape 6 (purge possible à partir du) | non | oui | non |
| Journal : événements datés, sans nom de compte ni numéro de série | oui | oui | oui |
| E-mail, notes libres | non | non | non |

Le RH voit le numéro de série du matériel à récupérer parce qu'il doit **identifier formellement** le matériel restitué (A.5.11), comme
dans l'écran « Sorties » actuel. Cette visibilité se limite aux salariés de sa portée et au matériel détenu ; elle n'ouvre ni le matricule ni
l'e-mail. La règle « jamais plus que l'existant » vaut dans les deux sens : le parcours ne montre ni plus ni moins que les écrans actuels.

L'URL ne contient que l'identifiant numérique du salarié, jamais son nom.

**Journal : sources autorisées.** Le journal ne reprend que des événements dont la date est **déjà stockée** : date de sortie (information, pas
un événement de déclaration), horodatage d'une signature de restitution ou d'échange, `date_retour` d'un actif, constat de non-restitution
(lot 1bis), retrait d'accès **seulement si** une date de retrait est stockée. **Ce n'est pas le cas aujourd'hui** : `UserApplication.date_maj` est la date de dernière modification (attribution, note ou retrait), pas une date de retrait ; l'événement n'est donc pas produit. Il n'y a **pas** d'événement « départ déclaré » : `maj_le` change à chaque
modification et ne date pas la déclaration. Un événement sans date stockée est omis, jamais déduit. L'auteur ou le témoin d'un événement n'est
jamais renvoyé.

**Routes existantes : aucun alignement nécessaire (décision du 2026-11-04).** `GET /lifecycle/holdings/{user_id}` et
`POST /lifecycle/depart/{user_id}` renvoient le matériel avec marque, modèle et numéro de série aux comptes authentifiés dans leur portée.
C'est voulu pour le RH, qui doit identifier formellement le matériel qu'il récupère. Elles ne changent pas, et le parcours s'aligne sur elles.
- Pour mémoire : `writer_guard` ne limite que les écritures ; les lectures de ce routeur sont ouvertes à tout compte authentifié dans sa portée,
  rôle lecture compris. À garder en tête pour toute nouvelle donnée sensible exposée par ce routeur.
- Une réduction pour le RH (par exemple masquer la marque et le modèle, garder le numéro de série) reste possible plus tard si le besoin évolue.

**Lot 1bis : voie d'exception « matériel non restitué » et clôture sans matériel.**
Ce cas ne devrait pas arriver, mais il doit être prévu et tracé : sans lui, un salarié parti avec du matériel (perte, vol, refus) ne peut jamais
passer `sorti`, et un salarié sans matériel non plus.

- **Constat de non-restitution** (action informatique) : pour un salarié `en_depart`, l'informatique constate, par actif encore `affecte`, qu'il ne sera
  pas restitué. Réservé au rôle **informatique** (le rôle RH reçoit 403). Confirmation explicite dans l'interface (récapitulatif et case à cocher) :
  l'action est sensible et tracée.
- **Motif obligatoire, liste fermée** : `perte`, `vol`, `refus_de_restituer`, `salarie_injoignable`, `autre`. **Pas de texte libre** (minimisation).
- **Effet** : l'actif passe au nouveau statut `non_restitue` (nouvelle valeur d'`AssetStatus`). Il sort de « à récupérer », reste dans l'inventaire et
  l'historique (jamais supprimé), et sort des prévisions, des rappels et des renouvellements comme un actif rendu ou réformé. Un actif retrouvé
  repasse par une restitution signée normale (action dédiée, tracée : détail à fournir dans le complément du lot).
- **Données nouvelles** (proposition d'emplacement, à confirmer en relecture) : sur `assignment_assets`, `non_restitue_le` (date-heure) et
  `motif_non_restitution` (liste fermée). L'auteur du constat est inscrit dans le journal d'audit existant, **sans nom de salarié ni numéro de série**.
  Migration Alembic nécessaire, avec test ; si `AssetStatus` est un type énuméré de la base, la migration doit l'étendre.
- **Passage à `sorti`** : la logique actuelle (`lifecycle.py`, restitution signée : « si le salarié partait et n'a plus rien, il est sorti ») est
  extraite dans une fonction partagée, appelée aussi par le constat et par la clôture. Elle ne se déclenche que si aucun actif `affecte` ne reste.
- **Clôture d'un départ sans matériel** : `POST /lifecycle/depart/{user_id}/cloturer` (RH ou informatique), autorisée seulement si le statut est
  `en_depart` et qu'aucun actif `affecte` ne reste (409 sinon) ; passe le salarié à `sorti` ; tracée ; aucun document (rien à signer).
- **Droits** : constat réservé à l'informatique (`require_roles("informatique")` explicite sur la route, le garde du routeur ne suffit pas) ;
  clôture : RH ou informatique ; salarié hors portée : 404.
- **Purge RGPD** : les nouvelles colonnes suivent la ligne d'affectation du salarié ; vérifier à la réalisation que la purge et l'anonymisation
  existantes les couvrent.

| Question (lot 1bis) | Réponse |
|---|---|
| Quelle donnée ? | Date-heure et motif (liste fermée) de non-restitution d'un actif ; l'auteur dans le journal d'audit existant |
| Pourquoi ? | Tracer les actifs non rendus après un départ et pouvoir clôturer le départ (A.5.11, A.6.5) |
| Qui la voit ? | Le motif : informatique seulement. Le nombre d'actifs non restitués : informatique, RH et lecture (parcours) |
| Combien de temps ? | Comme l'affectation et le salarié : durée de rétention existante |
| Comment l'effacer ? | Purge RGPD existante du salarié (à vérifier à la réalisation) |

**Interface.**
- Composant partagé `EtapesParcours` : liste ordonnée (`<ol>`), états fait, courante, à venir, sans objet, carte « Prochaine action », bandeau « Terminé,
  avec réserve ». Il reprend l'accessibilité d'`Arrivant.jsx` (`aria-label`, `aria-current="step"`, puce ✓ en plus de la couleur). L'état de chaque étape est aussi annoncé aux lecteurs d'écran par un texte masqué (« fait », « en cours », « a venir », « sans objet »), via une fonction pure testée. Il reste
  **présentationnel** (il reçoit des étapes et une action, il n'écrit pas) pour pouvoir servir aux lots suivants.
- `Arrivant.jsx` est refactoré pour l'utiliser **sans aucun changement de comportement**.
- Page `/depart/:id`, fil d'Ariane « Cycle de vie > Sorties > Parcours de départ » (à ajouter dans `nav.js`) ; lien « Suivre le
  parcours » par salarié dans « Départs en cours ».
- Une action principale par écran, grandes zones tactiles pour la signature. CSP stricte (pas de script inline). États de chargement,
  d'erreur avec relance, de parcours terminé, de parcours terminé avec réserve.
- La **maquette** de l'écran est validée avant le code.

**Critères d'acceptation du lot 1.**
1. Un salarié en départ avec 2 matériels et 1 accès affiche l'étape 3 comme courante, avec « 2 matériel(s) restant(s) ».
2. Après la restitution signée du dernier matériel, le salarié passe `sorti` et le parcours est « terminé, avec réserve : 1 accès à retirer ».
3. Un RH hors de l'entité du salarié reçoit 404, identique à un identifiant inexistant.
4. Un RH voit, pour le matériel à récupérer d'un salarié de sa portée, le type, la marque, le modèle et le numéro de série (identification formelle) ; il ne voit jamais le matricule ni l'e-mail.
5. L'étape 6 n'apparaît que pour l'informatique (absente de la réponse pour les autres rôles).
6. Le rôle lecture voit le parcours sans aucun bouton d'action (`autorise` faux).
7. Le matricule n'apparaît dans aucune réponse du parcours.
8. L'appel n'écrit rien en base (vérifié par un test).
9. Le parcours d'arrivée fonctionne exactement comme avant.
10. Après la purge RGPD, le parcours renvoie 404.
11. La date de l'étape 6 est `date_sortie` + rétention, sans le délai de grâce.
12. Un salarié sans matériel : étape 2 « sans objet », étape 3 faite, message d'attente (texte ci-dessus), aucune action proposée.
13. Une restitution en deux signatures : « 2 restants » puis « 1 restant » puis terminé.
14. Un salarié `actif` ou `prevu` : réponse 200, étape 1 courante.
15. Les routes `GET /lifecycle/holdings/{id}` et `POST /lifecycle/depart/{id}` restent inchangées pour tous les rôles (test de non-régression).
16. Pour un même rôle, le parcours ne renvoie aucune donnée que les routes existantes ne lui donnent pas.
17. Date de sortie dépassée avec du matériel restant : pastille « en retard de n jour(s) ».
18. Le nombre de requêtes du parcours ne dépend pas du nombre d'actifs.
19. Aucun événement « départ déclaré » dans le journal ; ni nom de compte, ni témoin, ni numéro de série.

**Critères d'acceptation du lot 1bis.**
1. Le constat de non-restitution est refusé au RH (403) et au rôle lecture (403) ; accepté pour l'informatique dans sa portée.
2. Un motif hors de la liste fermée est refusé (422) ; le motif est obligatoire.
3. Un actif qui n'est pas `affecte` à ce salarié est refusé (409) ; un salarié hors portée renvoie 404.
4. Après le constat du dernier actif détenu, le salarié passe `sorti`, le parcours est « terminé, avec réserve : n matériel(s) non restitué(s) ».
5. L'actif `non_restitue` reste dans l'inventaire et l'historique, et sort des prévisions, rappels et renouvellements.
6. La clôture d'un départ sans matériel passe le salarié `sorti` ; elle est refusée (409) s'il reste un actif `affecte` ou si le statut n'est pas `en_depart`.
7. Le constat et la clôture sont tracés dans le journal d'audit, sans nom de salarié ni numéro de série.
8. La migration est réversible et testée ; la purge RGPD couvre les nouvelles colonnes.

**Tests** (environnement séparé, données fictives nettoyées ensuite) :
- fonctionnels : chaque étape (aucun matériel, restitution partielle, restitution en plusieurs signatures, accès restants, salarié sorti, salarié sans départ), étape courante, retard, fin avec réserve, journal ;
- sécurité et droits : 401 sans session ; 404 identique hors portée et inexistant ; présence du numéro de série pour les RH dans leur portée ; absence de l'étape 6 hors informatique ; `autorise` faux pour le rôle lecture ;
  absence de matricule ; aucune écriture ; constat refusé hors informatique ; motif hors liste refusé ;
- non-régression : parcours d'arrivée, écran « Sorties », routes `/lifecycle/holdings` et `/lifecycle/depart` inchangées, tests du composant partagé ;
- accessibilité : navigation clavier et lecteur d'écran sur la liste d'étapes ;
- suite complète avant toute PR.

**Privacy : les cinq questions (lot 1).**

| Question | Réponse |
|---|---|
| Quelle donnée ? | Aucune nouvelle ; affichage calculé de données existantes, réduit au nécessaire |
| Pourquoi ? | Éviter les oublis de restitution et d'accès (A.5.11, A.5.18, A.6.5) |
| Qui la voit ? | Comptes authentifiés dans leur portée, avec réduction des données selon le rôle |
| Combien de temps ? | Durée de conservation existante ; rien n'est stocké en plus |
| Comment l'effacer ? | Purge RGPD existante : le parcours disparaît avec le salarié (404) |

**Consignes de réalisation** (pour toute personne ou tout modèle qui réalise le lot ; le relecteur les vérifie).
- **Périmètre strict** : le lot 1 d'abord, sans toucher à d'autres comportements ; le lot 1bis seulement après validation du lot 1. Aucune nouvelle dépendance.
- **Fichiers attendus (noms indicatifs, à aligner sur les fichiers voisins)** : nouveau routeur `backend/app/routers/parcours.py` enregistré dans `main.py` ;
  assistant `_etape` extrait d'`arrivee.py` ; `frontend/src/components/EtapesParcours.jsx` ; page de départ ;
  `nav.js` ; refactor d'`Arrivant.jsx` ; lien dans `Departures.jsx`.
- **Tests** : un script au format des `tests/*_check.py` existants (`show(...)`, code de sortie 1 en cas d'échec), ajouté à `tests/run_all.sh` ;
  tests unitaires du composant ; **suite complète exécutée avant toute PR** ; données fictives, nettoyées ensuite. Les tests de sécurité et de droits
  s'ajoutent aux tests fonctionnels.
- **Conventions** : même style que les fichiers voisins (en-tête de licence, densité de commentaires, noms) ; « - » et jamais le tiret long dans les fichiers ;
  aucun secret ni donnée personnelle dans les journaux, les URL ou les tests.
- **Git** : une branche, des commits petits ; **rien n'est poussé sans demande explicite** ;
  une PR, fusion en squash.
- **Livraison** : mettre à jour `GUIDE-UTILISATEUR.md` (§5.5), `CHANGELOG.md` et les captures (données fictives). Dire franchement ce qui n'est pas vérifié.
- **Liste de contrôle du relecteur** : droits appliqués côté serveur ; 404 uniforme ; réduction des données côté serveur ; aucune écriture sur les routes
  du parcours ; aucune requête par actif ; tests présents, pertinents et verts ; comportement de l'arrivée inchangé ; pas de script inline ; écarts à la
  spécification signalés et non masqués.

**Décisions validées (2026-11-04).** Matricule non affiché ; RH : identification formelle du matériel avec le numéro de série (décision du 2026-11-04, qui remplace « type et quantité seulement ») ; étape 6 réservée à l'informatique ;
étape 4 informative ; spécification intégrée à `SPEC.md`.

**Décisions validées (2026-11-04, seconde série).** Une voie « matériel non restitué » est prévue (lot 1bis) ; aucune date de déclaration de départ n'est
stockée (donc pas de compteur « k sur N » ni d'événement « départ déclaré ») ; les routes existantes ne sont pas modifiées (le RH garde le numéro de série).

**Décisions validées (2026-11-04, troisième série).** Le constat de non-restitution est réservé à l'**informatique seule**, avec trois garde-fous :
motif obligatoire dans une liste fermée et tracé dans le journal d'audit ; actif conservé dans l'inventaire et l'historique ; nombre d'actifs non
restitués visible des RH et du rôle lecture (sans le motif). La variante « confirmation du RH » (quatre yeux) est écartée pour ce lot, à reconsidérer
si un besoin d'audit l'exige. Le **lot 3 est abandonné** ; le lot 2 est à décider après mesure des lots 1 et 1bis.

**Constats après réalisation du lot 1 (2026-11-04).** Le lot 1 est réalisé et fusionné (PR #99). Tel que réalisé, le RH voit la marque, le modèle et le numéro de série du
matériel à récupérer (valeur par défaut, comme dans l'écran « Sorties » ; à infirmer si besoin). Le nom de route `/parcours/depart/{user_id}` est celui du code fusionné.
Les champs `materiel_a_recuperer`, `acces_restants` et `message_attente` sont ajoutés au contrat. Le message d'attente a été reformulé sans le terme interne « lot 1bis » (PR #101).

**Points à valider avant réalisation.**
1. **Emplacement des nouvelles colonnes** du lot 1bis (`assignment_assets`) et nom des motifs : propositions.
2. **Lot 2** : le brouillon de l'assistant de remise vit-il dans le navigateur (perdu au rechargement ou au passage de la main à la tablette) ou sur le serveur
   (donnée nouvelle, cinq questions) ? Cela décide du contrat de `EtapesParcours`.

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
- Statistiques du parc et prévisions de renouvellement, exportables : voir §10.

## 8. Interface de paramétrage

Personnalisation maximale, sans toucher au code :
- Types d'actifs, marques/modèles du catalogue (ajout, fusion, nettoyage).
- **Coûts de remplacement estimés** par type (exception par modèle), qui chiffrent le budget des prévisions de renouvellement (§10).
- **Liste des applications** (ajout/désactivation, portée par entité) + option d'inclusion des
  accès dans le document de remise.
- **Charte informatique** (texte, versions) - annexée au document de remise.
- Modèle de PDF d'accusé (logo, mentions légales, pied de page).
- **Apparence** : **icône de l'application** (menu, page de connexion, onglet du navigateur), déposée par l'informatique ; sans icône déposée, le **logo Kikan** par défaut s'affiche ; le nom « Kikan » reste celui du produit.
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

## 10. Statistiques et prévisions

**Statistiques (C1, fait)** - `GET /stats`
- Modèles de PC / smartphones les plus distribués, répartition par statut, entité et service, taux d'équipement, âge moyen du parc.
- **Filtres** : entité (sous-entités incluses, toujours dans la portée du compte, 404 hors portée) et période (`du`, `au`).
- Les répartitions décrivent le parc **à la date du jour** ; la période pilote les **mouvements** (matériels remis, restitués, achetés,
  au total et par mois, en dates locales de l'organisation) et la fenêtre des renouvellements (sans période : 12 mois).
- Exports **CSV, Excel et PDF** (modèle de PDF de l'organisation).

**Prévisions de renouvellement (C3, fait)** - `GET /previsions`
- **Budget estimé** = somme des coûts de remplacement (§8) du matériel dont l'`echeance_renouvellement` tombe dans la période ; le
  matériel **réformé** est ignoré. Sans période : du mois en cours aux 11 mois suivants (12 mois) ; durée maximale 60 mois.
- **Coût d'un matériel** : l'exception de son modèle (marque et modèle) si elle existe, sinon le coût de son type. Sans coût, le matériel est
  compté **« sans estimation »** et n'entre pas dans les totaux (le manque est affiché, jamais masqué).
- Vues : par **mois** (mois vides compris), par **année civile**, par **type**, par **entité**, détail du matériel ; échéances **antérieures
  à la période** et non renouvelées signalées à part (« en retard »).
- Mêmes **filtres d'entité** et exports **CSV, Excel et PDF** ; consultation ouverte aux trois rôles dans leur portée (B2), **sans aucune
  donnée de salarié**. Montants en euros ; une seule devise.
- Les coûts suivent le **renommage d'un type** et partent avec un type supprimé (inutilisé) ; une exception dont la marque ou le modèle a été
  fusionné reste listée avec « 0 matériel concerné » et se supprime à la main.

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

- **Icône publique** : `GET /branding` et `GET /branding/icone` sont lisibles **sans session** (la page de connexion n'en a pas) ; c'est la seule image servie
  ainsi. Le dépôt est réservé à l'informatique, l'image est vérifiée par son contenu, bornée en taille et en dimensions, puis réécrite en PNG (aucune métadonnée, aucun SVG).

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
| A3b | **Annulation d'un import** : chaque import réel est un lot (lignes créées) ; bouton *Annuler cet import*, tout ou rien, refusé si un élément est déjà utilisé (salarié avec matériel, accès ou besoin, actif remis, entité utilisée, remise signée ou restituée, lien GLPI) ; les actifs remis par un import d'affectations reprennent leur statut. **Fait (2026-11-04)** | Confort |
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
| B5 | **Connecteur GLPI** (synchronisation du matériel et des salariés, champs `source` et `id_externe`). **Fait (2026-10-31)** : API d'import par jetons (`/api/v1`, hachés, expirables, droits et périmètre limités, simulation, lots, idempotente) et connecteur GLPI à la demande, ordinateurs et téléphones avec numéros de série, correspondance du champ GLPI vers l'identifiant interne (`otherserial` par défaut, `name` avec suffixe `-ANNÉE` en cas de doublon, ou `serial`), import sur sélection et export des salariés et de leur matériel vers GLPI, sans suppression ni écrasement, testé contre GLPI 10.0.28, 11.0.12 et 12.0.1 ; la création de tickets reste à faire | SPEC |
| B6 | **Dépôt via l'API SharePoint Online et DocuWare** (SMB et WebDAV existent déjà). **Fait (2026-11-01)** : deux moteurs de stockage de plus (un seul actif à la fois), uniquement pour les PDF scellés (les chartes restent en local) : SharePoint par Microsoft Graph (`Sites.Selected`, fichiers de plus de 4 Mio par blocs) et DocuWare par l'API REST (compte de service, champs d'index à associer, aucune donnée nominative sans association explicite) ; même tampon local, vérification d'empreinte et reprise que SMB et WebDAV ; outil de copie vers le moteur actif sans suppression ; testés contre de faux services, **à valider sur un vrai tenant** (docs/SHAREPOINT.md, docs/DOCUWARE.md) | SPEC |
| B7 | **Besoins matériels exprimés par les RH** à l'arrivée (souhait : catégorie et gamme), repris par l'informatique. **Fait (2026-10-30), revu (2026-10-30)** : les RH n'ont plus accès à la page Besoins (création seule, au formulaire d'entrée) ; **gamme** par catégorie (liste définie par l'informatique, migration 0018) ; page Besoins réservée à l'informatique (lecture pour le rôle lecture) ; quatre statuts (demande, en préparation, satisfait, annulé), type pris dans la liste du Paramétrage, périmètre des RH respecté, proposition automatique des besoins ouverts à la création d'une remise et solde avec elle, compteur du tableau de bord, rappel e-mail des arrivées proches non traitées, purge RGPD | SPEC |
| B8 | **Import et export Excel (.xlsx)** en plus du CSV. **Fait (2026-10-28)** : import avec le même parcours que le CSV (première feuille visible, lignes vides ignorées, formules jamais évaluées), modèles Excel, export du rapport de détention, protections contre archives et XML piégés, macros et liens externes | Prop. |

### v0.3 - pilotage

| # | Fonctionnalité | Origine |
|---|---|---|
| C1 | **Statistiques exportables** (CSV et PDF), avec filtres par entité et période. **Fait (2026-10-30)** : filtre par entité (sous-entités incluses, limité à la portée du compte, 404 hors portée) et par période (mouvements remis, restitués et achetés, au total et par mois ; fenêtre des renouvellements) ; export CSV, Excel et PDF (modèle de PDF de l'organisation) ; les répartitions décrivent le parc à la date du jour | SPEC |
| C2 | **Revue périodique des droits d'accès** : rapport « qui a accès à quoi » et campagne de validation (ISO A.5.18) **Fait (2026-10-29)** : anomalies (salarié sorti, application désactivée) et rapport exportable ; campagne à la demande, décisions par les RH dans leur périmètre et l'informatique ; clôture seulement si tout est décidé, accès à retirer passés à non, rapport PDF scellé, retraits suivis jusqu'à confirmation ; rappels (échéance, retraits, revue annuelle) | Prop. |
| C3 | **Prévision des renouvellements** avec budget estimé. **Fait (2026-10-30)** : coût de remplacement par type (exception par modèle) saisi par l'informatique dans le Paramétrage (migration 0017) ; page Prévisions par mois, année, type et entité sur une période au choix (12 mois par défaut), échéances dépassées signalées, matériel sans coût compté à part ; filtre d'entité dans la portée du compte ; export CSV, Excel et PDF ; aucune donnée de salarié | Prop. |
| C4 | **Étiquettes et QR codes** sur le matériel, recherche par scan | Prop. |
| C5 | **Pièces jointes** au matériel (facture, garantie) | Prop. |
| C6 | **Renouvellement du matériel d'un salarié en poste (échange)** : remise du nouveau matériel et restitution de l'ancien en un seul document signé (§6.2bis). **Fait (2026-10-30), lots 1 et 2** : opération d'échange (API, document, signature tablette), devenir de l'ancien matériel choisi, charte au choix, date de retour par actif (migration 0019), boutons *Renouveler* ; page **Renouvellements** (en retard, à venir, détenteur), **report d'échéance** avec motif facultatif et historique (migration 0020), tuile du tableau de bord, prévisions, rappels et statistiques sans le matériel rendu ou réformé | Prop. |

### v0.4 - montée en échelle

| # | Fonctionnalité | Origine |
|---|---|---|
| D1 | **Multi-organisations / multi-sites** | SPEC |
| D2 | **Interface multilingue** (français et anglais) | Prop. |
| D3 | **API publique documentée** avec jetons d'accès | Prop. |
| D4 | **Webhooks** vers des outils externes (par exemple n8n) | Prop. |
| D5 | **Personnalisation de l'apparence** : icône de l'application (menu, page de connexion, favicon). **Fait (2026-10-30)** : dépôt PNG ou JPEG par l'informatique (Paramétrage, Apparence), image vérifiée et réécrite en PNG, lecture publique limitée à cette image, prévisualisation, suppression ; sans icône déposée, le **logo Kikan** (jeu de favicons dans `frontend/public/`, `docs/logo/`) s'affiche partout ; le nom de l'application reste « Kikan » | Prop. |
| D6 | **Listes triables et paginées** (Matériel, Utilisateurs, Remises) et sélection du matériel en stock limitée à 20 lignes à la fois. **Fait (2026-11-02, version 0.4.1)** : tri par clic sur l'en-tête (casse, accents et nombres bien classés, valeurs vides en fin), 10, 20 ou 50 lignes par page selon l'écran, vue gardée dans l'adresse, ordre par défaut « derniers ajoutés d'abord » | Prop. |
| D7 | **Journal d'audit paginé et trié par le serveur**. **Fait (2026-11-02, version 0.4.2)** : `GET /audit` accepte `offset`, `tri` et `sens` et renvoie `X-Total-Count` ; la page ne se limite plus aux 300 dernières entrées | Prop. |

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
| E9 | **Intégrité des données**. **Fait (2026-11-03, version 0.5.0)** : unicité garantie par la base (matricule, numéro de série, identifiant interne sans tenir compte de la casse, code d'entité ; migration 0021), refus 409 d'une course perdante, longueurs maximales des champs texte | Audit |
| E10 | **Durcissement du journal et de la purge RGPD**. **Fait (2026-11-03, version 0.5.0)** : plafond des refus 401/403 journalisés par couple (adresse IP, appelant), saisie d'un compte inconnu remplacée par une empreinte HMAC, purge qui supprime aussi les liens externes du salarié | Audit |

## 14. Décisions

**Tranchées :**
- **Renouvellement** (C6) : décidé par l'**informatique seule** ; l'échéance est indicative (renouvellement avant ou après) ; **une seule opération et un seul document signé** (remise + restitution) ; **signature en une fois** sur la tablette, sans état « en attente » ; devenir de l'ancien matériel **choisi à l'échange** ; **charte au choix, décochée par défaut** ; motif de report **facultatif**.
- **Licence du logo et du nom** : le code est en GPL-3.0-or-later ; le **logo** et le **nom « Kikan »** ne sont pas couverts (© 2026 Gabriel Chollet, tous droits réservés). Usage autorisé sans modification pour désigner le projet et pour utiliser le logiciel tel quel ; une version modifiée ou dérivée prend un autre nom et un autre logo. Le nom n'est pas déposé comme marque (`docs/logo/LICENCE.md`).
- **Couleur de marque** (barre latérale, boutons, liens, chiffres, couleur du navigateur, PDF et Excel) : le **bleu du logo, #1D428A** (RVB 29, 66, 138), validé comme référence par l'auteur. La conversion écran du quadri C100 M75 J0 N0 (#024B8F, profil CMJN générique d'Apple) n'a pas été retenue, et la référence Pantone indiquée (« 7387 ») n'a pas pu être rattachée à ce bleu : à confirmer si une valeur Pantone officielle est nécessaire. Le même bleu (constante unique `backend/app/theme.py`, variable CSS `--brand`) sert aux **en-têtes de tableau des PDF et des exports Excel** : l'ancien bleu `#2b4c7e` n'est plus utilisé nulle part.
- **Besoins de matériel** : les RH expriment un **souhait** (catégorie et gamme), sans accès au suivi (page Besoins, liste, modification, statuts) ; l'informatique choisit le matériel exact (§5bis, §6.0).
- **Apparence** : seule l'**icône** est personnalisable (pas le nom du produit), le **logo Kikan** (carré bleu, K blanc, pastille orange à coche) étant l'icône par défaut ; PNG ou JPEG, même vérification que le logo des PDF ; servie sans session pour la page de connexion (§12).
- **Budget de renouvellement** (C3) : coût de remplacement **par type** avec exception par modèle (pas de prix d'achat par matériel), saisi par l'informatique ; matériel sans coût compté à part ; devise unique (euro) (§10).
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
  SharePoint Online et DocuWare ont été livrés ensuite (B6).
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
   service dédié). Les connecteurs API SharePoint Online et DocuWare existent (B6).
3. Format d'import proposé (§6.4, modèles dans `import-modeles/`) à valider : plusieurs
   fichiers liés, ou fichier unique à plat ?
4. **Portée des comptes par entité** : accès global ou restreint à une/des filiale(s) dès la v0.1 ?

