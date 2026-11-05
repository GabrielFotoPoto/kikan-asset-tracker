# Registre des activités de traitement (Article 30 du RGPD) - Application Kikan

> **Modèle fourni avec Kikan (version 0.7.0).** Ce document décrit ce que fait Kikan ; il n'a pas de valeur juridique tant que l'organisation ne l'a pas complété, adapté à son déploiement et fait **valider par son DPO ou son juriste**. Les mentions `[À compléter…]`, `[À décider…]` et `[À vérifier…]` sont à traiter avant usage ; supprimez les rubriques des intégrations que vous n'activez pas (GLPI, SMTP, SharePoint, DocuWare, SSO, API). Les durées de conservation indiquées sont les valeurs **par défaut** de Kikan, réglables dans la page *RGPD*. Kikan n'est pas « certifié RGPD » ni « certifié ISO 27001 » : il facilite la conformité du traitement de l'organisation, qui reste responsable de traitement.

> **Objet du document** : Ce registre recense l'ensemble des traitements de données à caractère personnel mis en œuvre au sein de l'application **Kikan** (*suivi du parc informatique, remise/échange/restitution de matériel signés sur tablette, gestion des accès applicatifs et conformité ISO 27001*), conformément à l'article 30 du Règlement (UE) 2016/679 (RGPD), en s'inspirant des rubriques du modèle de registre de la CNIL.
>
> **Note d'adaptation** : Les mentions entre crochets `[À compléter par l'organisation]` doivent être renseignées par le responsable de traitement ou le DPO de l'entité qui déploie Kikan.

---

## 1. Identification générale

| Rubrique | Valeur |
|---|---|
| **Nom du logiciel / Système** | **Kikan** (Asset & Access Tracker - hébergement *on-premise*) |
| **Responsable de traitement** | `[Nom de l'organisation / Groupe et filiales]` |
| **Représentant légal** | `[Nom, Prénom, Fonction]` |
| **Délégué à la Protection des Données (DPO)** | `[Nom / Coordonnées du DPO ou Référent RGPD]` |
| **Service gestionnaire (Exploitation)** | Direction / Service Informatique (rôle `informatique`) |
| **Services métiers utilisateurs** | Service Ressources Humaines (rôle `rh`), Service Informatique (`informatique`), Direction / RSSI / Audit (rôle `lecture`) |
| **Mode d'hébergement** | Interne (*On-premise*, conteneurs Docker : `web`, `api`, `db`, `converter`), non exposé sur Internet |
| **Version de Kikan décrite** | 0.7.0 |
| **Date de mise à jour du registre** | `[JJ mois AAAA]` |
| **Analyse d'impact (AIPD)** | `[À décider par le DPO : non jugée nécessaire car traitement d'outils de travail sans donnée sensible, sans surveillance systématique ni profilage ; à justifier ou à réaliser]` |

---

## 2. Vue synthétique des fiches de traitement dans Kikan

| Réf. | Intitulé du traitement | Finalité principale | Base légale (Art. 6 RGPD) | Réf. ISO 27001:2022 |
|---|---|---|---|---|
| **T-01** | Gestion du cycle de vie des salariés (Entrée, mobilité, départ) | Identifier les collaborateurs par entité/service, exprimer les besoins de matériel à l'arrivée et préparer la récupération au départ | Intérêt légitime (Art. 6.1.f) / Exécution du contrat de travail (Art. 6.1.b) | A.6.1, A.6.5 |
| **T-02** | Remise, échange et restitution de matériel avec signature électronique (PAdES) | Attribuer le matériel informatique, recueillir l'acceptation de la charte IT et constituer la preuve de remise/échange/restitution | Intérêt légitime (Art. 6.1.f) - Protection des actifs et preuve d'opposabilité | A.5.9, A.5.10, A.5.11 |
| **T-03** | Gestion des droits d'accès applicatifs et campagnes de revue périodique | Tenir le registre des habilitations applicatives par salarié et conduire les revues périodiques de conformité | Intérêt légitime (Art. 6.1.f) - Sécurité du SI et contrôle des accès | A.5.15, A.5.18 |
| **T-04** | Gestion des comptes d'accès à Kikan, authentification et journalisation d'audit | Contrôler l'accès à l'application Kikan (SSO / comptes locaux), cloisonner les droits par entité et tracer les opérations sensibles | Intérêt légitime (Art. 6.1.f) - Sécurité et traçabilité du traitement (Art. 32 RGPD) | A.5.16, A.8.5, A.8.15 |

---

## 3. Fiches détaillées des activités de traitement

### Fiche T-01 : Gestion du cycle de vie des salariés et des besoins matériels

#### 3.1.1 Finalités et base légale
- **Finalités** :
  - Enregistrer l'arrivée prévue ou effective d'un collaborateur (`prevu`, `actif`) afin d'anticiper son équipement informatique.
  - Exprimer les souhaits de matériel à l'embauche (catégorie et gamme souhaitée) et suivre le parcours d'arrivée (`/arrivee/:id`).
  - Synchroniser le référentiel des salariés avec l'outil de gestion de parc **GLPI** ou par import CSV/Excel contrôlé.
  - Déclarer le départ d'un collaborateur (`en_depart`), suivre le parcours de départ (`/depart/:id`), déclencher les alertes de récupération du matériel et passer le collaborateur au statut `sorti`.
- **Base légale** :
  - **Intérêt légitime de l'employeur** (Art. 6.1.f RGPD) : bonne organisation matérielle de l'entreprise, dotation des outils de travail et préservation du patrimoine informatique lors des départs.
  - **Exécution du contrat de travail** (Art. 6.1.b RGPD) : fourniture des moyens nécessaires à l'exercice des fonctions.

#### 3.1.2 Catégories de personnes concernées
- Salariés, futurs embauchés (statut `prevu`), stagiaires, alternants et prestataires équipés par l'organisation ou ses filiales.

#### 3.1.3 Catégories de données personnelles traitées
| Catégorie | Champs dans Kikan (`users`, `besoins`, `external_links`) | Caractère obligatoire / facultatif |
|---|---|---|
| **Identité professionnelle** | `nom`, `prenom`, `acronyme` (3 lettres générées pour le nommage des PDF), `matricule` | Nom et prénom obligatoires ; matricule facultatif |
| **Coordonnées professionnelles** | `email` professionnel | Facultatif |
| **Rattachement organisationnel** | `entite_id` (filiale / entité), `service` (département) | Facultatif (recommandé pour le cloisonnement par entité) |
| **Cycle de vie contractuel** | `statut` (`prevu`, `actif`, `en_depart`, `sorti`), `date_arrivee`, `date_sortie` | Statut obligatoire ; dates selon l'événement |
| **Besoins d'équipement** | `type` (catégorie de matériel), `gamme`, `quantite`, `commentaire`, `date_souhaitee`, `statut` du besoin | Lié au souhait d'entrée |
| **Identifiants techniques tiers** | `externe_id` (identifiant utilisateur dans GLPI si le connecteur GLPI est utilisé) | Automatique si synchro GLPI |

> **Données sensibles (Art. 9 RGPD)** : **Aucune**. Kikan ne traite ni NIR (numéro de sécurité sociale), ni donnée de santé, ni donnée personnelle privée (pas d'adresse postale ni de téléphone personnel).

#### 3.1.4 Destinataires habilités
- **Service RH** (rôle `rh`) : lecture et écriture limitées aux salariés de son **périmètre d'entités** (`account_scopes`). Dans les parcours guidés (`/depart/:id`), le matricule et l'e-mail sont masqués par minimisation.
- **Service Informatique** (rôle `informatique`) : accès global pour la préparation du matériel, la gestion du parc et la purge RGPD.
- **Direction / RSSI / Contrôle interne** (rôle `lecture`) : consultation en lecture seule, limitée à son périmètre d'entités.

---

### Fiche T-02 : Remise, échange (renouvellement) et restitution de matériel signés sur tablette

#### 3.2.1 Finalités et base légale
- **Finalités** :
  - Tracer les équipements informatiques (`assets`) confiés à chaque salarié (ordinateurs, smartphones, écrans, accessoires).
  - Recueillir sur tablette la **signature manuscrite** du salarié lors de la remise initiale, du renouvellement (échange en un seul acte) et de la restitution de départ.
  - Annexer et rendre opposable la **Charte informatique** en vigueur au moment de la remise.
  - Générer un **document PDF scellé cryptographiquement (PAdES)** avec horodatage RFC 3161 et faisceau de preuves.
- **Base légale** :
  - **Intérêt légitime de l'employeur** (Art. 6.1.f RGPD) : traçabilité du patrimoine matériel (ISO 27001 A.5.9 / A.5.11) et preuve de prise de connaissance des règles d'usage sécurité (A.5.10).

#### 3.2.2 Catégories de données personnelles traitées
| Catégorie | Données enregistrées (`assignments`, `signatures`, PDF scellés) | Détail de minimisation dans Kikan |
|---|---|---|
| **Détention de matériel** | Liste des actifs affectés (`type`, `marque`, `modele`, `numero_serie`, `identifiant_interne`), `date_remise`, `date_retour`, `date_restitution` | Les statistiques et prévisions budgétaires (`/previsions`) n'exposent aucune donnée de salarié |
| **Signature manuscrite** | Image PNG du tracé apposé au doigt ou au stylet sur la tablette | **Non stockée en base de données** : l'image est assainie (sans métadonnées), insérée uniquement dans le PDF scellé, puis détruite de la mémoire. La base ne conserve que le nombre de traits, la durée en ms et l'empreinte SHA-256. Ces éléments servent de preuve de l'acte de signature ; ils ne sont pas utilisés pour identifier ou authentifier la personne (pas de traitement biométrique) |
| **Faisceau de preuves (`audit_json`)** | Nom et prénom du signataire (déduits de sa fiche, jamais saisis librement), compte témoin (admin IT ou RH connecté), adresse IP du terminal de signature, User-Agent, horodatage UTC / TSA, empreintes SHA-256 du document, de la charte et des accès | Figé à la signature ; toute modification ultérieure du PDF invalide le sceau PAdES |
| **Document PDF scellé** | Fichier nommé `AAAA_MM_JJ_NOM_PRENOM_ACR_NNN.pdf` stocké dans le moteur configuré (`local`, `smb`, `webdav`, `sharepoint` ou `docuware`) | Empreinte SHA-256 vérifiée à chaque dépôt et à chaque lecture |

#### 3.2.3 Destinataires et stockage externe éventuel
- **Interne** : Service Informatique, Service RH (dans son périmètre d'entités), Rôle Lecture (dans son périmètre).
- **Moteur de stockage documentaire configuré** (un seul actif à la fois) :
  - *Volume local Docker*, *Partage réseau SMB 3* ou *WebDAV interne* ;
  - Ou *SharePoint Online* (Microsoft Graph API, permission restreinte `Sites.Selected`) ;
  - Ou *DocuWare* (API REST ; aucune donnée nominative n'est transmise dans les champs d'index sans association explicite par l'administrateur).

---

### Fiche T-03 : Gestion des accès applicatifs et campagnes de revue des droits (ISO 27001 A.5.18)

#### 3.3.1 Finalités et base légale
- **Finalités** :
  - Documenter les applications métier auxquelles chaque salarié est habilité (`user_applications`), avec le niveau de profil/droits attendu.
  - Détecter automatiquement les anomalies d'accès (accès restés actifs pour un salarié `sorti`, dont la date de sortie est dépassée, ou vers une application désactivée).
  - Organiser des campagnes périodiques de revue des droits d'accès (`revues_acces`, `revue_lignes`), recueillir les décisions (« Maintenir » / « À retirer »), suivre la confirmation des retraits par l'IT et produire un **rapport de clôture PDF scellé**.
- **Base légale** :
  - **Intérêt légitime** (Art. 6.1.f RGPD) et **obligation de sécurité des traitements** (Art. 32 RGPD) : maîtrise des habilitations d'accès aux systèmes d'information contenant des données de l'entreprise.

#### 3.3.2 Catégories de données personnelles traitées
- **Habilitations (`user_applications`)** : identifiant du salarié (`user_id`), application (`application_id`), statut d'accès (`acces` oui/non), précision/profil (`note`), auteur de l'attribution (`attribue_par`), date de mise à jour (`date_maj`).
- **Campagnes de revue (`revue_lignes` et rapport PDF scellé)** :
  - En base pendant la campagne : `user_id`, `matricule`, `entite_id`, `application`, `decision`, `commentaire`, `decide_par`, `decide_le`, `retrait_par`, `retrait_le`.
  - **Minimisation dans le rapport PDF scellé de clôture** : le rapport PDF scellé ne mentionne les salariés **que par leur matricule** (jamais leur nom ni leur prénom), ce qui permet de conserver la preuve d'audit ISO 27001 même après la purge RGPD du salarié.

---

### Fiche T-04 : Gestion des comptes d'accès à Kikan, authentification et journal d'audit

#### 3.4.1 Finalités et base légale
- **Finalités** :
  - Gérer les comptes nominatifs des opérateurs de l'application (équipes Informatique, RH, Lecture seule). *Note : les salariés équipés ne disposent pas de compte de connexion à Kikan.*
  - Authentifier les opérateurs via **SSO Microsoft 365 (Entra ID)** (OpenID Connect + PKCE) ou par mot de passe local (comptes de secours *break-glass*).
  - Tracer les connexions, échecs d'authentification, refus d'accès (401/403) et actions d'écriture dans un journal d'audit (`audit_log`) en ajout seul (*append-only*).
- **Base légale** :
  - **Intérêt légitime** (Art. 6.1.f RGPD) et **sécurité du traitement** (Art. 32 RGPD) : imputabilité des actions d'administration et détection des tentatives d'intrusion.

#### 3.4.2 Catégories de données personnelles traitées
| Catégorie | Champs dans Kikan (`accounts`, `audit_log`, `reminder_sent`) | Mesures de minimisation (Privacy by Design) |
|---|---|---|
| **Identité du compte opérateur** | `username`, `nom_affiche`, `email`, `role` (`informatique`, `rh`, `lecture`), `portee_globale`, `account_scopes` | Comptes strictement nominatifs |
| **Données d'authentification** | `hashed_password` (bcrypt), `sso_oid` (identifiant immuable Entra ID), `sso_upn`, `derniere_connexion`, `token_epoch` | Mot de passe jamais stocké en clair ; jetons de réinitialisation et d'API stockés uniquement sous forme d'empreinte SHA-256 |
| **Journal d'audit (`audit_log`)** | `ts` (horodatage UTC), `actor` (identifiant du compte), `action`, `target`, `status` (code HTTP), `ip` (adresse IP), `detail` | **Zéro donnée personnelle de salarié dans le journal** : lors d'une création, modification, suppression en lot ou purge RGPD, seuls l'identifiant technique (`users/{id}`), les noms des colonnes modifiées, des compteurs chiffrés et les empreintes SHA-256 des PDF sont journalisés |
| **Tentatives sur compte inconnu** | `actor` sous la forme `inconnu:<empreinte_HMAC_12_car>` | Si un utilisateur saisit par erreur un nom, un e-mail tiers ou un mot de passe dans le champ identifiant, **la chaîne saisie n'est jamais enregistrée** : seule une empreinte HMAC irréversible est tracée |
| **Rappels par e-mail (`reminder_sent`)** | `kind`, `cle`, `destinataire` (e-mail de l'opérateur), `envoye_le` | Les e-mails de rappel RGPD et de revue ne contiennent que des **compteurs**, jamais de noms de salariés |

---

## 4. Durées de conservation et politique de purge RGPD

Kikan intègre un moteur dédié de purge RGPD (page `/rgpd`, module `backend/app/purge.py`), paramétrable sans modification du code.

| Catégorie de données | Durée de conservation active / intermédiaire | Modalités de purge dans Kikan |
|---|---|---|
| **Salarié en poste (`prevu`, `actif`, `en_depart`)** | Toute la durée de présence dans l'organisation | - (Suppression directe bloquée par garde-fou si le salarié possède un historique de matériel, d'accès ou de besoin) |
| **Salarié ayant quitté l'organisation (`sorti`)** | **`retention_apres_sortie_mois`** à compter de `date_sortie` (**12 mois par défaut**, réglable de 0 à 240 mois) | À l'échéance, le salarié remonte dans la prévisualisation de purge (`/rgpd`) et dans les rappels e-mail hebdomadaires. La purge (validée par l'IT) **supprime définitivement** la fiche salarié, ses besoins, ses affectations, ses signatures en base, ses accès applicatifs, ses lignes de revue et ses liens externes (GLPI) |
| **Documents PDF scellés (remise, échange, restitution)** - *Stockage local, SMB ou WebDAV* | Durée de conservation du salarié sorti + **délai de grâce en quarantaine** (`purge_delai_grace_jours`, **30 jours par défaut**, réglable de 0 à 365 jours) | Lors de la purge du salarié, ses PDF sont déplacés dans le dossier de quarantaine `A_PURGER/` (pour permettre une restauration en cas d'erreur sur la date de sortie). Une fois le délai de grâce écoulé, l'action *Supprimer définitivement les documents échus* efface les fichiers PDF et ne conserve que leur empreinte SHA-256 anonyme dans le journal |
| **Documents PDF scellés** - *SharePoint Online ou DocuWare* | Durée de conservation du salarié sorti | Kikan ne supprime pas directement dans la GED externe : il génère la liste des références échues (`ged_a_supprimer`) à transmettre à l'administrateur de la GED, puis enregistre la confirmation de suppression |
| **Rapports PDF scellés de revue des accès (`/revues`)** | Durée de conservation probatoire ISO 27001 `[ex. 3 à 5 ans selon politique interne]` | Les lignes individuelles en base (`revue_lignes`) sont supprimées lors de la purge RGPD du salarié ; le rapport PDF scellé de campagne ne contient que des matricules (sans nom ni prénom) |
| **Journal d'audit (`audit_log`)** : compte opérateur, action, adresse IP, horodatage | `[À décider par le DPO : durée à fixer, par exemple 1 à 3 ans]`. *État actuel de Kikan : le journal est en ajout seul, sans purge automatique ni fonction de suppression ; il est conservé tant qu'il n'est pas purgé par l'administrateur de la base. Il ne contient aucune donnée de salarié.* | Aucune purge dans l'application : à traiter par l'administrateur de la base selon la durée décidée, ou à documenter comme conservé sans limite avec sa justification (preuve et sécurité, ISO 27001 A.8.15) |
| **Comptes opérateurs Kikan (`accounts`)** | Tant que l'opérateur est habilité | Désactivation immédiate (`actif = false`, révocation instantanée des sessions via `token_epoch`) au départ ou changement de fonction de l'opérateur |
| **Jetons révoqués (`revoked_tokens`) et liens de réinitialisation (`password_reset_tokens`)** | Durée de vie du jeton (30 min pour la réinitialisation ; 4 h par défaut pour la session) | Purge automatique des jetons expirés |
| **Sauvegardes chiffrées (`age`)** | **30 jours** (sauvegardes quotidiennes) + **12 mois** (1ère sauvegarde de chaque mois) | Rotation automatique par le service de sauvegarde. *Note : en cas de restauration d'une sauvegarde antérieure à une purge, relancer la purge sur la page `/rgpd`. Les sauvegardes contiennent encore les données purgées jusqu'à leur expiration.* `[À confirmer : durée réellement appliquée sur le serveur de production ; la préproduction en conserve 3 par un script de purge dédié]` |

---

## 5. Sous-traitants, destinataires externes et transferts hors UE

Par conception, Kikan fonctionne en **circuit fermé (*on-premise*)** sans télémétrie ni dépendance cloud obligatoire. Des flux externes n'existent que si l'organisation active explicitement certaines intégrations :

| Tiers / Système | Rôle | Données transmises | Localisation / Transfert hors UE |
|---|---|---|---|
| **Hébergeur de l'infrastructure interne** | Hébergement des conteneurs Docker et de la base PostgreSQL | Toutes les données de l'application | `[Interne / France / UE - Aucun transfert hors UE]` |
| **Serveur de fichiers interne (SMB / WebDAV)** | Stockage des PDF scellés et des sauvegardes chiffrées | PDF scellés (nom, prénom, matériel, signature manuscrite), archives chiffrées `age` | `[Interne / France / UE - Aucun transfert hors UE]` |
| **GLPI (interne)** *(si activé)* | Import (sur sélection) du matériel et des salariés depuis GLPI, et export vers GLPI des salariés et du matériel créés dans Kikan | Import : nom, prénom, e-mail, matricule, entité, matériel. Export : identifiant de connexion, nom, prénom, matricule, e-mail, matériel et numéro de série | `[Interne - Aucun transfert hors UE]` |
| **API d'import (`/api/v1`) et imports CSV / Excel** *(si utilisés)* | Chargement de matériel, de salariés ou d'affectations par un système tiers (jeton d'API nominatif, expirable, limité à un périmètre) ou par un fichier importé par l'informatique | Selon le fichier ou le système émetteur : nom, prénom, matricule, e-mail, entité, matériel | `[Système émetteur interne ; fichiers importés à ne pas conserver hors Kikan]` |
| **Relais SMTP** *(si activé)* | Envoi des rappels et du rapport mensuel | E-mail des opérateurs Kikan, compteurs d'alertes | `[Serveur de messagerie de l'organisation]` |
| **Microsoft Entra ID (Microsoft 365)** *(si SSO ou SharePoint activé)* | Authentification OIDC des opérateurs RH/IT et/ou dépôt des PDF scellés sur SharePoint Online | Identité des comptes opérateurs (`oid`, `upn`, nom, e-mail) ; PDF scellés si moteur SharePoint actif | Hébergement selon la région du tenant Microsoft 365 de l'organisation (clauses contractuelles types / DPA Microsoft) |
| **DocuWare** *(si activé)* | Archivage GED des PDF scellés | PDF scellés + métadonnées techniques (aucun index nominatif sans configuration explicite) | Selon l'hébergement DocuWare de l'organisation (On-premise ou Cloud UE) |
| **Autorité d'horodatage RFC 3161 (TSA)** *(si configurée)* | Horodatage cryptographique des PDF scellés | **Aucune donnée personnelle** : seule l'empreinte SHA-256 (hash non réversible) du PDF est envoyée au serveur TSA | Aucune donnée à caractère personnel transmise |

---

## 6. Mesures de sécurité techniques et organisationnelles (Article 32 du RGPD)

### 6.1 Confidentialité et contrôle d'accès
- **Cloisonnement strict par entité (`scope.py`)** : les comptes RH et Lecture peuvent être restreints à une ou plusieurs filiales (et leurs sous-entités). Toute tentative d'accès à un salarié hors périmètre renvoie une erreur `404` identique à un identifiant inexistant (aucune fuite d'existence ni énumération).
- **Authentification robuste** : support du SSO Microsoft 365 (OIDC + PKCE + MFA du tenant, filtrage par groupes `Kikan-IT` et `Kikan-RH`), mots de passe locaux hachés en `bcrypt` (12 caractères min., remplacement obligatoire du mot de passe provisoire), verrouillage anti-force brute par couple `(compte, IP)`.
- **Protection des sessions** : jetons JWT stockés dans un cookie `HttpOnly`, `SameSite=Strict`, `Secure`, avec protection CSRF par en-tête `X-Kikan-Request: 1` et révocation immédiate en base (`revoked_tokens` et `token_epoch`).
- **Chiffrement des flux** : HTTPS obligatoire (TLS 1.2/1.3 avec suites ECDHE AEAD uniquement, HSTS activé), SMB 3 chiffré par défaut, WebDAV/SharePoint/DocuWare en HTTPS avec vérification stricte des certificats.

### 6.2 Intégrité et valeur probante
- **Scellement PAdES-B / PAdES-B-T** via `pyHanko` : chaque PDF signé (remise, échange, restitution, clôture de revue d'accès) est scellé cryptographiquement.
- **Contrôle d'intégrité continu** : l'empreinte SHA-256 de chaque PDF est enregistrée en base et recalculée à chaque dépôt et à chaque lecture ; un fichier altéré sur le stockage est immédiatement rejeté et signalé dans le journal d'audit.
- **Verrous transactionnels (`SELECT ... FOR UPDATE`)** : protection contre les accès concurrents et doubles soumissions lors des remises, échanges, restitutions et purges.

### 6.3 Minimisation et protection de la vie privée dès la conception (*Privacy by Design*)
- **Absence de stockage de l'image de signature en base** : l'image PNG du tracé manuscrit est intégrée au PDF scellé à la volée et n'est jamais conservée dans PostgreSQL.
- **Journal d'audit anonymisé vis-à-vis des salariés** : aucune opération (modification de fiche, suppression unitaire ou en lot, échange, rapport de revue, purge RGPD) n'inscrit le nom, le prénom, l'e-mail ou le matricule d'un salarié dans `audit_log`.
- **Champs libres** : les commentaires (besoins, lignes de revue d'accès, note d'accès applicatif, motif de report) sont du texte libre où une donnée superflue peut être saisie. Consigne aux utilisateurs : ne saisir que le nécessaire, jamais de donnée de santé, de situation personnelle ou d'appréciation sur la personne.
- **Hachage HMAC des identifiants inconnus** : les erreurs de saisie à la connexion sont transformées en `inconnu:<HMAC>` pour éviter toute collecte accidentelle de données personnelles ou de mots de passe dans les journaux.
- **Isolation du convertisseur de documents** : le conteneur LibreOffice (`converter`) utilisé pour convertir les chartes Word en PDF s'exécute sans accès réseau externe (`internal: true`), en lecture seule et sans privilèges.

### 6.4 Disponibilité et résilience
- **Sauvegardes chiffrées par clé publique (`age`)** : les sauvegardes automatiques (base PostgreSQL, PDF locaux, certificats, configuration) sont chiffrées avec une clé publique `age` dont la clé privée est détenue hors du serveur. L'intégrité est contrôlée par manifeste SHA-256 avant toute restauration.
- **Tampon local résilient** : en cas d'indisponibilité temporaire du partage externe (SMB, WebDAV, SharePoint, DocuWare), le PDF scellé est conservé en sécurité dans le tampon local et synchronisé ultérieurement sans perte de preuve.

---

## 7. Exercice des droits des personnes concernées (Articles 15 à 22 du RGPD)

Les salariés peuvent exercer leurs droits auprès de `[Adresse e-mail / contact RGPD ou RH de l'organisation]` :

| Droit RGPD | Modalités pratiques de réponse via Kikan |
|---|---|
| **Droit à l'information (Art. 13 & 14)** | Mention d'information RGPD intégrée à la Charte informatique annexée aux remises et/ou au livret d'accueil RH `[À vérifier par le DPO]`. |
| **Droit d'accès (Art. 15)** | Les RH (dans leur périmètre) ou l'IT consultent la fiche du salarié (page *Utilisateurs*), son matériel affecté, ses accès applicatifs (page *Accès applicatifs*) et ses accusés PDF scellés (page *Remises*), puis lui transmettent l'extraction. Kikan ne propose pas d'export dédié par salarié `[À vérifier avant d'indiquer un autre moyen]`. |
| **Droit de rectification (Art. 16)** | Modification directe de la fiche salarié (nom, prénom, e-mail, service, entité, dates) par les RH ou l'IT dans la page *Utilisateurs*. *(Un PDF scellé antérieur reste figé en tant que preuve datée ; la fiche active reflète la rectification).* |
| **Droit à l'effacement (Art. 17)** | - **Fiche créée par erreur sans historique** : suppression immédiate unitaire ou en lot depuis la page *Utilisateurs* (rôle `informatique`).<br>- **Salarié ayant détenu du matériel ou des accès** : limitation du traitement pendant la période de conservation probatoire (statut `sorti`), puis effacement complet (base + PDF) via la **Purge RGPD** (`/rgpd`). |
| **Droit à la limitation et d'opposition (Art. 18 & 21)** | Traitement géré manuellement par le service RH / IT après instruction de la demande par le DPO. |
