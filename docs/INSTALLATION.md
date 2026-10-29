# Guide d'installation

Ce guide s'adresse à la personne qui installe et exploite Kikan (administrateur système). Il va du serveur vide à une instance utilisable,
sauvegardée et à jour. Pour l'utilisation au quotidien, voir le [guide d'utilisation](GUIDE-UTILISATEUR.md).

> Kikan manipule des données personnelles (salariés) et produit des documents qui font preuve (remises signées). Il se déploie **sur le réseau de
> l'organisation** (on-premise) et ne doit **jamais être exposé directement sur Internet**.

## 1. Avant de commencer

| Il vous faut | Détail |
|---|---|
| Un serveur | Linux (recommandé) ou Windows avec Docker Desktop. Le service de conversion Word est limité à 1 Go de mémoire ; prévoyez de la place disque pour les PDF scellés si le stockage reste local. |
| **Docker** et **Docker Compose** (v2) | `docker --version` et `docker compose version` doivent répondre. |
| Un accès à GitHub Container Registry | seulement pour la méthode A (images publiées). |
| Un nom ou une adresse pour Kikan | par exemple `kikan.exemple.local` : sert au certificat HTTPS et aux liens des e-mails. |
| *Facultatif* : un serveur SMTP interne | rappels, rapport mensuel et « Mot de passe oublié ? ». |
| *Facultatif* : un partage réseau (SMB) | sauvegarde nocturne chiffrée, et stockage des PDF scellés. |

Deux méthodes d'installation :

- **A. Images publiées** (recommandée) : rien à compiler, on télécharge les images de la version voulue.
- **B. Depuis les sources** : on clone le dépôt et Docker compile les images (utile pour tester une version en cours de développement).

## 2. Récupérer les fichiers

**Méthode A**, sans cloner le dépôt : sur la page de la version (https://github.com/GabrielFotoPoto/kikan-asset-tracker/releases), télécharger
`docker-compose.yml`, `docker-compose.ghcr.yml` et le modèle de configuration, et les mettre dans un dossier dédié, par exemple `/opt/kikan` ou `C:\kikan`.

> GitHub renomme le modèle de configuration : le fichier s'appelle `default.env.example` sur la page de la version. Il se copie en `.env` (étape 3).

**Méthode B** :

```bash
git clone https://github.com/GabrielFotoPoto/kikan-asset-tracker.git /opt/kikan
cd /opt/kikan
```

## 3. Configurer `.env`

Le fichier `.env` contient les secrets : **ne le versionnez jamais** et gardez-en une copie en lieu sûr (il est aussi inclus, chiffré, dans les sauvegardes).

```bash
cp .env.example .env            # méthode B ;  cp default.env.example .env  (méthode A)
```

Renseignez au minimum :

| Variable | Rôle | Comment la remplir |
|---|---|---|
| `POSTGRES_PASSWORD` | mot de passe de la base | une valeur longue et aléatoire |
| `KIKAN_SECRET_KEY` | signature des sessions (32 caractères minimum) | `python -c "import secrets; print(secrets.token_urlsafe(48))"` ou `openssl rand -base64 48` |
| `KIKAN_ENV` | `production` en exploitation | refuse de démarrer sans clé solide, masque la documentation interactive de l'API et impose le cookie de session sécurisé |
| `KIKAN_PUBLIC_URL` | adresse publique en HTTPS, par exemple `https://kikan.exemple.local` | **nécessaire** pour les liens des e-mails et « Mot de passe oublié ? » |
| `KIKAN_ADMIN_USER` / `KIKAN_ADMIN_PASSWORD` | premier compte | facultatif : sinon un mot de passe aléatoire est généré (voir étape 5) |

Autres réglages utiles (tous facultatifs, commentés dans `.env.example`) : `KIKAN_BIND` et `KIKAN_TLS_SAN` (accès depuis le réseau, étape 6),
`KIKAN_TIMEZONE` (fuseau des dates des noms de fichier, `Europe/Paris` par défaut), `KIKAN_STORAGE_BACKEND` (étape 8), `KIKAN_TOKEN_TTL_MIN` (durée de session, 240 min par défaut ; réglable ensuite dans Paramétrage).

## 4. Démarrer

**Méthode A** (images publiées) :

```bash
export KIKAN_VERSION=0.2.0       # la version voulue ; par défaut : la dernière version finale
docker compose -f docker-compose.yml -f docker-compose.ghcr.yml pull
docker compose -f docker-compose.yml -f docker-compose.ghcr.yml up -d --no-build
```

**Méthode B** (sources) :

```bash
docker compose up -d --build
```

Sous Windows (PowerShell), remplacez `export KIKAN_VERSION=0.2.0` par `$env:KIKAN_VERSION = "0.2.0"`. Si le téléchargement des images est refusé
(paquets non publics), connectez-vous d'abord : `docker login ghcr.io` avec un jeton personnel GitHub autorisé à lire les paquets (`read:packages`).

Vérification (une minute après le démarrage) :

```bash
docker compose ps                      # db, api, web et converter : "Up" (healthy)
curl -sk https://localhost:3443/api/health
```

La réponse attendue est `{"status":"ok","app":"Kikan","version":"0.2.0"}`. La base est créée et les migrations s'appliquent seules au démarrage de l'API.

## 5. Première connexion

1. Ouvrez **https://localhost:3443** (ou l'adresse du serveur). Le certificat est **auto-signé** : le navigateur affiche un avertissement à accepter
   (voir l'étape 6 pour le remplacer par celui de l'organisation).
2. Si vous n'avez pas défini `KIKAN_ADMIN_PASSWORD`, le mot de passe du compte `admin` est affiché **une seule fois** dans les journaux :

   ```bash
   docker compose logs api | grep "COMPTE INITIAL"
   ```

   Ce mot de passe est **provisoire** : Kikan impose de le changer dès la première connexion.
3. Créez ensuite des **comptes nominatifs** (page *Comptes*) et gardez `admin` comme compte de secours.

![Écran de connexion](captures/guide-connexion.png)

## 6. Accès depuis le réseau et HTTPS

Par défaut, l'interface n'est publiée que sur la machine locale (`127.0.0.1`). Pour l'ouvrir au réseau de l'organisation (postes, **tablette de signature**) :

1. Dans `.env` : `KIKAN_BIND=<adresse IP du serveur>` et `KIKAN_TLS_SAN=DNS:kikan.exemple.local,IP:192.168.1.10` (noms et adresses ajoutés au certificat).
2. À faire **avant le premier démarrage** (le certificat est généré une fois) ; sinon supprimer le volume `kikan_webcerts` pour le régénérer.
3. Ouvrir le port `3443` du pare-feu vers le réseau interne **uniquement**.

**Certificat de l'organisation** : montez-le dans le volume `kikan_webcerts` (fichiers `kikan.crt` et `kikan.key`) à la place du certificat auto-signé ; les postes ne verront alors plus d'avertissement.

**Derrière un reverse-proxy d'entreprise** : Nginx ne voit alors que l'adresse du proxy, et tous les utilisateurs partageraient la même limite de tentatives
de connexion. Décommentez dans `frontend/nginx.conf` les lignes `set_real_ip_from` / `real_ip_header` en indiquant l'adresse du proxy (jamais un réseau plus large).

## 7. Premier paramétrage

Dans cet ordre, depuis un compte informatique (détail dans le [guide d'utilisation](GUIDE-UTILISATEUR.md)) :

1. **Entités** : le groupe et ses filiales (ou import CSV / Excel).
2. **Paramétrage** : types de matériel, services, catégories de besoin, **modèle de PDF** (logo, mentions).
3. **Chartes** : déposer la charte informatique (Word, PDF ou Markdown), globale ou par entité.
4. **Comptes** : un compte nominatif par personne, avec son rôle (informatique, RH, lecture) et, pour RH et lecture, le périmètre d'entités.
5. **Salariés, matériel, accès applicatifs** : saisie, ou **Import** de l'existant (modèles CSV et Excel fournis).
6. **E-mails** (Paramétrage, onglet E-mails) : serveur SMTP interne, expéditeur, adresse de liste, puis message de test. `KIKAN_PUBLIC_URL` doit être défini.
7. **Stockage** et **Sauvegarde** : étapes 8 et 9.

Pour **essayer avant de saisir les vraies données**, utilisez le jeu de démonstration sur une instance vide : `bash scripts/demo.sh charger` (retrait : `bash scripts/demo.sh effacer`).
Il refuse de se charger si la base contient déjà des données réelles.

## 8. Où sont stockés les PDF scellés ?

Par défaut dans le volume Docker `kikan_archive`. On peut les déposer ailleurs, un seul moteur à la fois (`KIKAN_STORAGE_BACKEND`) :

| Moteur | Quand | Documentation |
|---|---|---|
| `local` | par défaut ; le volume peut être un lecteur réseau monté sur l'hôte | ce guide |
| `smb` | partage Windows/Samba | `.env.example` |
| `webdav` | partage web (HTTPS) | `.env.example` |
| `sharepoint` | SharePoint Online | [SHAREPOINT.md](SHAREPOINT.md) |
| `docuware` | DocuWare | [DOCUWARE.md](DOCUWARE.md) |

Le PDF est toujours écrit d'abord en local, déposé, relu et **comparé par empreinte SHA-256** ; si le stockage distant est indisponible, la signature réussit et le dépôt est repris plus tard.
La page **Stockage** teste la connexion et permet de copier les documents vers un nouveau moteur.

## 9. Sauvegarde (à faire dès le premier jour)

Kikan fournit une sauvegarde **chiffrée** (base, PDF scellés locaux, clés, certificat, `.env`). Elle se met en place en quatre commandes ; le détail,
la planification nocturne (tâche Windows ou `cron`), la rétention (30 jours, puis une par mois pendant un an) et la restauration sont dans [SAUVEGARDE.md](SAUVEGARDE.md).

```bash
docker compose --profile backup run --rm -v ./cles:/keys backup keygen --out /keys   # 1. paire de clés
#  2. copier la clé privée (cles/identity.txt) HORS du serveur, en deux exemplaires, puis la supprimer du serveur
#  3. renseigner KIKAN_BACKUP_RECIPIENT et le partage KIKAN_BACKUP_SMB_* dans .env
docker compose --profile backup run --rm backup backup                               # 4. première sauvegarde
```

> **Sans la clé privée, aucune sauvegarde ne peut être restaurée.** Faites une restauration d'essai avant de compter dessus, puis chaque trimestre.
> La page **Sauvegarde** de Kikan et le tableau de bord alertent si la dernière sauvegarde a plus de 36 heures.

## 10. Mettre à jour Kikan

1. **Sauvegardez** (étape 9), et lisez le [CHANGELOG](../CHANGELOG.md) : les changements qui demandent une action y sont signalés.
2. **Méthode A** :

   ```bash
   export KIKAN_VERSION=0.3.0          # la nouvelle version
   docker compose -f docker-compose.yml -f docker-compose.ghcr.yml pull
   docker compose -f docker-compose.yml -f docker-compose.ghcr.yml up -d --no-build
   ```

   **Méthode B** :

   ```bash
   git pull
   docker compose up -d --build
   ```

3. Les **migrations de la base s'appliquent seules** au démarrage de l'API. Vérifiez : `curl -sk https://localhost:3443/api/health` (version) et `docker compose exec api alembic current`.
4. Les utilisateurs peuvent devoir **se reconnecter une fois** (la session est un cookie sécurisé, renouvelé à chaque version qui change son format).
5. En cas de problème : restaurez la sauvegarde faite à l'étape 1 (`scripts/restore.sh` ou `scripts/restore.ps1`, voir [SAUVEGARDE.md](SAUVEGARDE.md)).

## 11. Dépannage

| Symptôme | Cause probable | Que faire |
|---|---|---|
| **502 Bad Gateway** | le serveur web a gardé l'ancienne adresse de l'API après sa recréation | `docker compose restart web` (corrigé depuis la version qui résout l'adresse à chaque requête) |
| L'API ne démarre pas, « clé de session » | `KIKAN_ENV=production` sans `KIKAN_SECRET_KEY` solide | renseigner une clé de 32 caractères minimum |
| `POSTGRES_PASSWORD est requis` | `.env` absent ou incomplet | créer `.env` (étape 3) |
| « Mot de passe oublié ? » n'apparaît pas | e-mails non configurés, ou `KIKAN_PUBLIC_URL` vide | Paramétrage > E-mails, et `.env` |
| Plus aucun administrateur ne peut se connecter | mot de passe perdu | `docker compose exec api python -m app.reset_admin <identifiant> [--activer]` (mot de passe provisoire affiché une fois) |
| Avertissement du navigateur | certificat auto-signé | normal en local ; installer le certificat de l'organisation (étape 6) |
| Un utilisateur est déconnecté trop vite | durée de session | Paramétrage (authentification) ou `KIKAN_TOKEN_TTL_MIN` (minutes) |
| Trop de tentatives de connexion | limite anti-force-brute (5 échecs par compte, 15 minutes) | attendre, ou voir les journaux (`login_bloque`) |
| Le PDF n'apparaît pas sur le partage | partage indisponible : le dépôt est repris plus tard | page **Stockage** : test de connexion puis « Reprendre » |

Commandes de diagnostic :

```bash
docker compose ps                    # état des conteneurs
docker compose logs --tail 100 api   # journaux de l'API
docker compose logs --tail 50 web    # journaux du serveur web
docker compose exec api alembic current   # version du schéma de la base
```

Le **journal d'audit** de l'application (page *Journal d'audit*) enregistre les connexions, les écritures et les refus d'accès, sans mot de passe ni donnée personnelle superflue.

## 12. Aller plus loin

- [SECURITY.md](../SECURITY.md) : modèle de sécurité, liste de contrôle de mise en production, risques acceptés.
- [SSO.md](SSO.md) : connexion Microsoft 365 (Entra ID), facultative.
- [GLPI.md](GLPI.md) et [API.md](API.md) : intégration avec GLPI et API d'import par jetons.
- [RGPD.md](RGPD.md) : durée de conservation, purge et traçabilité.
- [REVUE-ACCES.md](REVUE-ACCES.md) : revue périodique des droits d'accès.
- [PUBLIER.md](PUBLIER.md) : publier une version (pour les mainteneurs du projet).
