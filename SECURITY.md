# Sécurité

Ce document décrit le modèle de sécurité de Kikan, ce qui est en place, ce qui est volontairement
laissé en risque accepté, et comment vérifier le tout.

> Kikan manipule des données personnelles (salariés) et produit des documents ayant valeur de
> preuve (remises et restitutions signées). Il doit être déployé **on-premise**, derrière le réseau
> de l'organisation, et jamais exposé directement sur Internet.

## Signaler une vulnérabilité

Merci d'utiliser le signalement privé de GitHub (onglet **Security** > **Report a vulnerability**
du dépôt) plutôt qu'une issue publique. Décrivez le problème, comment le reproduire et son impact.

## Mesures en place

| Domaine | Mesure |
|---|---|
| Authentification | Jetons JWT (HS256) à durée limitée (4 h par défaut), mots de passe hachés avec bcrypt, 401 systématique sans jeton valide. |
| Secrets | Aucune clé ou mot de passe par défaut : `KIKAN_SECRET_KEY` absente = clé aléatoire (sessions perdues au redémarrage) ; en `KIKAN_ENV=production`, l'application **refuse de démarrer** sans clé de 32 caractères minimum. Le premier compte reçoit un mot de passe aléatoire affiché une seule fois dans les journaux. `POSTGRES_PASSWORD` est obligatoire. |
| Mots de passe | 12 caractères minimum, 72 octets maximum (limite de bcrypt). Changement par l'utilisateur et réinitialisation par l'informatique. Le dernier compte informatique actif ne peut pas être désactivé ni rétrogradé. |
| Force brute | Verrouillage temporaire (15 min) après 5 échecs par couple compte + adresse IP, et limite globale par IP. Un attaquant distant ne peut pas verrouiller l'administrateur depuis une autre adresse. Temps de réponse identique que le compte existe ou non. |
| Autorisations | Rôles `informatique`, `rh`, `lecture` appliqués côté serveur sur chaque routeur (jamais seulement dans l'interface). |
| Journal d'audit | Toute écriture, tout refus d'accès (401/403) et toute connexion (réussie, échouée, bloquée) sont journalisés (compte, action, statut, IP). Aucun corps de requête n'est enregistré (pas de mot de passe ni de donnée personnelle). Consultable par l'informatique, sans endpoint de modification ni de suppression. |
| Transport | HTTPS obligatoire (TLS 1.2/1.3) : le port HTTP redirige vers HTTPS, HSTS activé. Certificat auto-signé généré au premier démarrage, remplaçable par celui de l'organisation. |
| En-têtes | `Content-Security-Policy` stricte, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Cache-Control: no-store` sur l'API, version des serveurs masquée. |
| Entrées | Requêtes SQL paramétrées (ORM). Texte utilisateur échappé dans les PDF. Cellules des exports CSV neutralisées contre l'injection de formules (`=`, `+`, `-`, `@`). Imports plafonnés (5 Mo, 20 000 lignes). |
| CORS | Liste blanche d'origines (`KIKAN_CORS_ORIGINS`), jamais `*`. |
| Conteneurs | API en utilisateur non privilégié, système de fichiers en lecture seule, toutes les capacités Linux retirées, `no-new-privileges`. Base de données sans port publié. Ports publiés sur `127.0.0.1` par défaut. |
| Signature | Clé privée du certificat de scellement en mode `0600`, hors de l'image et du dépôt (volume dédié). PDF scellé PAdES : toute modification invalide la signature. |
| Stockage des documents | Dépôt sur lecteur réseau (SMB 3, chiffrement activé par défaut) ou partage WebDAV (HTTPS obligatoire, certificat toujours vérifié sans aucune option pour le désactiver, HTTP refusé sauf autorisation explicite). Dépôt toujours vérifié par empreinte SHA-256 puis relu ; empreinte recontrôlée à chaque lecture (un fichier altéré sur le partage est refusé et journalisé). Clés de stockage strictement filtrées (pas de `..` ni de chemin absolu). Identifiants du partage uniquement dans l'environnement, jamais en base ni dans les journaux. Signature jamais bloquée par une panne du partage (dépôt différé, repris ensuite). |
| Signature manuscrite | L'image reçue du navigateur est traitée comme non fiable : PNG uniquement, taille et dimensions vérifiées avant décodage (bombes de décompression refusées), trace réel exigé, ré-encodage sans métadonnées. Le nom du signataire est déduit de la fiche du salarié (jamais fourni par le client), l'acceptation est obligatoire et une remise ne se signe qu'une fois. L'image n'est stockée que dans le PDF scellé : la base ne garde que ses empreintes, le nombre de traits et la durée du tracé. |
| Chartes deposees | Le fichier est traité comme non fiable : format reconnu par son contenu (pas par l'extension), taille et pages plafonnées, PDF reconstruit (pages seules, sans JavaScript, action, lien ni annotation) puis contrôlé par un second moteur ; Markdown rendu avec balises échappées. Les documents Word sont convertis par un service dédié **sans accès à Internet** (réseau Docker interne), en lecture seule, non privilégié, une conversion à la fois, avec délai maximal ; archives piégées (bombes de décompression) et macros refusées avant conversion. Empreinte de la charte recontrôlée à chaque lecture et avant chaque signature. Dépôt réservé à l'informatique, versions jamais supprimées. |
| Production | `KIKAN_ENV=production` masque la documentation interactive (`/docs`). |
| Dépendances | Versions figées et auditées avec `pip-audit` et `npm audit` (aucune vulnérabilité connue à la date de la dernière vérification). |

## Déploiement en production : liste de contrôle

1. Copier `.env.example` en `.env` et renseigner **`POSTGRES_PASSWORD`** et **`KIKAN_SECRET_KEY`**
   (`python -c "import secrets; print(secrets.token_urlsafe(48))"`), puis `KIKAN_ENV=production`.
2. Premier démarrage : récupérer le mot de passe initial (`docker compose logs api | grep "COMPTE INITIAL"`),
   se connecter, puis le changer depuis **Mon compte**. Créer ensuite des comptes **nominatifs** (un par personne).
3. Tablette de signature sur le réseau local : définir `KIKAN_BIND` (adresse IP du serveur) et
   `KIKAN_TLS_SAN` (ex. `DNS:kikan.exemple.local,IP:192.168.1.10`) **avant** le premier démarrage, ou monter le
   certificat de l'organisation (`kikan.crt` et `kikan.key`) dans le volume `kikan_webcerts`. Un certificat
   auto-signé affiche un avertissement tant que son certificat n'est pas installé comme approuvé sur la tablette.
4. Ne jamais publier le port de l'API (8080) ni celui de la base hors de la machine.
5. Mettre en place une sauvegarde de la base PostgreSQL et du volume des PDF scellés.
6. Un pare-feu doit limiter l'accès aux seules machines de l'informatique et des RH.

## Risques acceptés et limites connues

- **Jeton de session dans le navigateur** (`localStorage`) : exposé en cas de faille XSS. Atténué par la
  politique CSP stricte (aucun script externe ni en ligne) et la durée de vie courte. Les jetons ne sont
  pas révocables individuellement (désactiver le compte les invalide, car le compte est revérifié à chaque requête).
- **Limiteur de tentatives en mémoire**, mono-processus : réinitialisé au redémarrage de l'API.
- **Pas d'authentification multifacteur en local.** Cible v0.2 : SSO Microsoft 365 (Entra ID) avec MFA du tenant,
  comptes nominatifs, rôles par groupes. Les comptes locaux sont alors un secours.
- **Certificats auto-signés** (TLS et scellement des PDF) : valides techniquement, affichés « non approuvés » tant
  que la racine de l'organisation n'est pas installée sur les postes.
- **Clé privée du scellement non chiffrée** dans son volume (protégée par les droits `0600`). Un coffre ou un HSM est
  recommandé pour un usage à forte valeur probante.
- **Journal d'audit non chaîné** : un administrateur de la base PostgreSQL peut le modifier. Pour une preuve
  renforcée, exporter régulièrement le journal vers un système externe.
- **Pas d'analyse d'images** de conteneurs, ni de limitation de débit au-delà de la connexion.
- **La signature manuscrite est une donnée personnelle** : elle figure dans le PDF scellé, donc dans le stockage choisi (volume,
  partage SMB ou WebDAV). Protéger l'accès à ce stockage et appliquer la durée de rétention RGPD.
- **Service de conversion Word** : LibreOffice traite des fichiers déposés par l'informatique. Il est isolé (aucun réseau externe,
  aucun secret, système de fichiers en lecture seule) ; une faille de LibreOffice resterait donc confinée à ce conteneur.
  Maintenir l'image à jour (`docker compose build --pull converter`) et la retirer si les chartes Word ne sont pas utilisées.
- **Identifiants du partage dans `.env`** (SMB ou WebDAV) : utiliser un compte de service dédié, limité au seul
  dossier de Kikan, et protéger le fichier `.env` (droits restreints, sauvegardes chiffrées).

## Vérifier la sécurité

Les tests suivants s'exécutent sur une instance de **développement** (ils créent des données marquées `ZZ…`).

```bash
# Tests offensifs : jetons falsifiés, contournement de rôles, injections, force brute, CORS, audit...
docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD='...' kikan-api python - < tests/security_check.py

# Non-régression fonctionnelle des flux métier (remise signée, départ, RGPD, import...)
docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD='...' kikan-api python - < tests/functional_smoke.py

# Audit des dépendances Python (le même contrôle existe côté front avec `npm audit`)
docker run --rm -v "$PWD/backend/requirements.txt:/r.txt:ro" -v "$PWD/tests/audit_deps.py:/a.py:ro" python:3.12-slim python /a.py

# Signature manuscrite : images invalides ou piégées, nom non falsifiable, preuves, PDF scellé, restitution
docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD='...' kikan-api python - < tests/signature_check.py

# Chartes : fichiers hostiles (PDF piégé, bombe ZIP, macros), Word, Markdown, portées, annexe signée, altération
docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD='...' kikan-api python - < tests/policy_check.py

# Stockage SMB et WebDAV : dépôt, relecture, intégrité, purge (serveurs de test jetables)
docker compose -f tests/storage-test-servers.yml up -d
#   puis, pour chaque backend, configurer l'API (voir tests/storage-test.override.yml) et lancer :
docker exec -i -e TEST_EXPECT_BACKEND=smb -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD='...' kikan-api python - < tests/storage_check.py
# Garde-fous : mauvais mot de passe, partage inexistant (délai), HTTP refusé, certificat inconnu...
docker exec -i kikan-api python - < tests/storage_guards.py
docker compose -f tests/storage-test-servers.yml down -v

# Schéma de la base : aucune dérive entre le modèle et les migrations
docker compose exec api alembic check

# Nettoyage des données de test
docker exec -i kikan-db psql -U kikan -d kikan < tests/cleanup_test_data.sql
```

### Installation neuve vérifiée

Les tests de sécurité (70) et de non-régression (28) ont été rejoués avec succès sur une **installation neuve**
en `KIKAN_ENV=production`, faite à partir d'un clone du dépôt en suivant le README : migrations appliquées depuis une
base vide, mot de passe initial aléatoire affiché une seule fois (y compris après un redémarrage), HTTPS et certificat
générés, `/docs` masqué, conteneurs non-root en lecture seule, refus de démarrer sans `POSTGRES_PASSWORD`.

Relancer ces vérifications après chaque mise à jour de dépendances : une montée de version peut introduire une
régression silencieuse (exemple rencontré : SQLModel exigeant des dates avec fuseau horaire).
