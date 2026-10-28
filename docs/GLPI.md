# Connecteur GLPI

Kikan lit et alimente **GLPI** par son **API REST** :

- **Import** : Kikan lit GLPI et vous **propose** les ordinateurs, les téléphones et les utilisateurs ; rien n'est créé sans votre
  sélection. Le matériel importé arrive **en stock**, avec son **numéro de série**.
- **Export** : Kikan crée dans GLPI les **salariés** choisis (matricule, e-mail et profil) et leur **matériel affecté avec les
  numéros de série**, ce qui permettra ensuite de créer des tickets d'assistance pour eux.

Seuls les **ordinateurs** (*Computer*) et les **téléphones** (*Phone*) sont suivis ; écrans, casques, claviers… relèvent de la
fourniture et sont ignorés.

## Règles

- **Rien n'est jamais supprimé ni écrasé**, ni dans Kikan ni dans GLPI.
- **Kikan est la source de vérité des salariés** (la RH y saisit les arrivants). Une fiche Kikan existante n'est jamais
  écrasée par GLPI : seuls ses champs vides sont complétés.
- Un élément déjà connu (même **numéro de série**, même **matricule**, même **e-mail**) est **lié** à son équivalent, jamais
  dupliqué. Un salarié de même nom et prénom (homonyme) n'est lié que sur votre décision explicite.
- Un matériel GLPI **déjà affecté à quelqu'un d'autre** n'est pas modifié ; un matériel GLPI **sans utilisateur** reçoit le salarié.
- Un élément déjà lié à une autre fiche est signalé en **conflit**, pas écrasé.
- Les données sont **relues dans GLPI au moment de l'application** : le navigateur ne fait que choisir les éléments.
- Aucune synchronisation automatique : tout se fait **à la demande**, par un bouton (page *Paramétrage, onglet Intégrations*).
- Matériel sans numéro de série : proposé à l'import (signalé), **non exporté** vers GLPI.

## Préparer GLPI

Testé avec **GLPI 10.0.28, 11.0.12 et 12.0.1** (images officielles `glpi/glpi`). Le connecteur utilise l'API REST « historique »
(`/apirest.php`), identique dans ces trois versions.

1. **Activer l'API** : *Configuration, Générale, API* : « Activer l'API Rest ». Laissez « connexion avec identifiants » désactivée.
2. **Client API** : dans la même page, ajoutez (ou modifiez) un client autorisé pour l'**adresse IP du serveur Kikan**, avec un
   **jeton d'application** si vous le souhaitez (recommandé).
3. **Compte de service** : créez dans GLPI un utilisateur dédié (par exemple `kikan`) dont le profil permet de **lire et créer**
   des ordinateurs, des téléphones et des utilisateurs, et de **créer** des fabricants et des modèles (menus déroulants). Évitez
   un super-administrateur si vous pouvez l'éviter.
4. **Jeton utilisateur** : dans les préférences de ce compte, section « Clé d'accès distant », générez le **jeton d'API**.
5. Profil donné aux utilisateurs créés par Kikan : **Self-Service** par défaut (réglable, vide = aucun profil).

## Configurer Kikan

Dans le fichier `.env` (**jamais** dans l'interface, jamais affichés) :

```
KIKAN_GLPI_USER_TOKEN=<jeton utilisateur du compte de service>
KIKAN_GLPI_APP_TOKEN=<jeton d'application, si le client API de GLPI en exige un>
# KIKAN_GLPI_CA_BUNDLE=/certs/ca-entreprise.pem   # autorité de certification interne (facultatif)
# KIKAN_GLPI_PROXY=http://proxy:3128              # facultatif
```

Puis `docker compose up -d api`, et dans **Paramétrage, onglet Intégrations, section GLPI** :

1. Adresse du serveur (`https://glpi.entreprise.local`). **HTTPS est exigé en production** (les jetons ne doivent pas circuler en
   clair) ; `KIKAN_GLPI_ALLOW_HTTP=1` lève cette exigence pour un réseau de confiance, à vos risques.
2. **Types Kikan** correspondant à un ordinateur et à un téléphone (ex. *PC portable* ; *Smartphone*).
3. Entité Kikan par défaut pour l'import, entité GLPI par défaut pour l'export, correspondance des entités (facultatif).
4. **Tester la connexion** : affiche le nombre d'ordinateurs, de téléphones et d'utilisateurs, et les entités GLPI.
5. Cocher **Activer le connecteur GLPI**.

Messages d'erreur courants : *GLPI exige un jeton d'application* (renseignez `KIKAN_GLPI_APP_TOKEN`), *adresse IP non autorisée*
(client API de GLPI), *API REST désactivée*, *certificat* (utilisez `KIKAN_GLPI_CA_BUNDLE`).

## Importer depuis GLPI

*Lire GLPI* affiche le matériel et les utilisateurs avec leur état :

| État | Sens |
|---|---|
| Nouveau | Pas encore dans Kikan : sera créé |
| Existe dans Kikan (sera lié) | Même numéro de série, matricule ou e-mail : sera lié, sans modification |
| Homonyme dans Kikan | Même nom et prénom qu'une fiche existante : à vous de choisir *lier* ou *créer* |
| Déjà lié | Importé ou lié précédemment : rien à faire |
| Sans numéro de série / nom ou prénom manquant | Signalé |

Cochez ce que vous voulez, choisissez au besoin l'entité Kikan, puis **Importer la sélection**.

## Exporter vers GLPI

*Préparer l'export* liste les salariés (hors sortis) avec leur matériel affecté et leur état dans GLPI. Les salariés à traiter sont
cochés ; **Exporter la sélection** :

- crée l'utilisateur GLPI (identifiant tiré de l'e-mail, ou `prénom.nom` ; suffixe si l'identifiant est pris par quelqu'un d'autre),
  avec nom, prénom, matricule (*numéro d'enregistrement*), e-mail et profil ;
- crée les ordinateurs et téléphones affectés avec **numéro de série**, numéro d'inventaire (identifiant interne Kikan), fabricant,
  modèle, entité et utilisateur ;
- lie, sans les modifier, les utilisateurs et matériels déjà présents dans GLPI.

L'historique des synchronisations (compteurs, sans données personnelles) est affiché en bas de la section.

## Limites

- L'API REST historique de GLPI pourrait être dépréciée dans une version future ; tous les appels sont isolés dans
  `backend/app/glpi.py` et pourront être portés vers l'API de nouvelle génération.
- Pas de mise à jour automatique des fiches déjà liées dans un sens ou dans l'autre (par choix : jamais d'écrasement).
- Pas de création de tickets pour l'instant ; l'export prépare ce chantier (utilisateurs et matériel présents dans GLPI).

## Tester sans toucher à votre GLPI

Une instance jetable est fournie :

```bash
tests/glpi_test_setup.sh 12.0.1 jeton.txt      # installe GLPI, active l'API, génère le jeton (versions : 12.0.1, 11.0.12, 10.0.28)
GLPI_TEST_TOKEN=$(cat jeton.txt) docker compose -f docker-compose.yml -f tests/glpi-test.override.yml up -d api
# Suite complète contre ce vrai GLPI :
docker exec -i -e GLPI_LIVE=1 -e GLPI_TEST_TOKEN=$(cat jeton.txt) -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/glpi_check.py
# Suite avec le faux GLPI intégré (sans jeton) :
docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/glpi_check.py
# Arrêt et retour à la normale :
docker compose -f tests/glpi-test.yml down -v ; docker compose up -d --force-recreate api
```

L'interface de ce GLPI de test est sur http://127.0.0.1:8088 (compte `glpi` / `glpi`, instance **de test uniquement**).
