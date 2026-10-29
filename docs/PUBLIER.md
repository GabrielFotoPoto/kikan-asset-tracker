# Publier une version et utiliser l'intégration continue

## Ce que fait l'intégration continue

À chaque envoi sur `main` et à chaque demande de fusion, GitHub Actions (`.github/workflows/ci.yml`, `codeql.yml` et `dependency-review.yml`) rejoue **les mêmes contrôles qu'en local** :

| Travail | Contenu |
|---|---|
| Hygiène du dépôt | pas de tiret long, tests en ASCII, en-têtes de licence, aucun secret ni fichier sensible versionné, code Python compilable, YAML et JSON valides (`tests/hygiene_check.py`) |
| Audit des dépendances | `pip-audit` (Python) et `npm audit` (front, niveau élevé) |
| Compilation du front | `npm ci` puis `npm run build` |
| Suites de tests | la pile complète (base, convertisseur, API) puis **toutes les suites** : sécurité, fonctionnel, signatures, chartes, import, comptes, cloisonnement, e-mails, API, GLPI (faux GLPI), SharePoint et DocuWare (faux services), SSO (faux fournisseur) (`tests/run_all.sh`) |
| Sauvegarde et restauration | restauration dans une instance vierge, mauvaise clé, archive altérée, partage Samba (`tests/backup_check.py`) |
| Images Docker | construction des quatre images (api, web, convertisseur, sauvegarde) et analyse Trivy (information, ne bloque pas) |
| Sécurité des workflows | `actionlint` et `zizmor` sur `.github/` (injection, permissions, actions vulnérables) |
| CodeQL | analyse statique du Python et du JavaScript (aussi chaque lundi) : `.github/workflows/codeql.yml` |
| Revue des dépendances | une demande de fusion qui introduit une dépendance vulnérable de gravité haute est refusée : `.github/workflows/dependency-review.yml` |

Le fichier `.env` de la CI est fabriqué avec des secrets aléatoires jetables : aucun secret réel n'est nécessaire. Le nom du projet Docker Compose
est fixé à `kikan` (`COMPOSE_PROJECT_NAME`) pour les étapes de sauvegarde et d'images ; les suites de tests, elles, tournent dans leur propre projet
`kiktest` (voir ci-dessous).

**En local** : `bash tests/run_all.sh` (tout), `bash tests/run_all.sh --avec-sauvegarde` (plus la sauvegarde de bout en bout),
`bash tests/run_all.sh security_check crud_check` (certaines suites), `python tests/hygiene_check.py` (hygiène seule). Uniquement sur une
**pile de test séparée** que le script crée lui-même (projet Docker `kiktest` : conteneurs `kiktest-*`, volumes, réseau et port 8081 propres,
secrets repris de `.env` sans le reste) : les tests créent puis effacent des données `ZZ...` et des réglages (e-mails, GLPI...), et ne touchent jamais à
votre instance ni à votre `.env`. Pour la supprimer : `docker compose -p kiktest down -v`. `KIKAN_TEST_PREFIX` et `KIKAN_TEST_API_PORT` changent le nom et
le port. Les suites lancées à la main (`docker exec -i ... kikan-api`, voir SECURITY.md) visent la pile qui porte ce nom : remplacer par `kiktest-api`
pour la pile de test.

## Réglages GitHub

**En place** (à contrôler de temps en temps, dans *Settings* du dépôt) :

- **Règle « Protection de main »** (*Rules, Rulesets*) : passage par une demande de fusion, **9 contrôles obligatoires** (hygiène, audit des dépendances, compilation du
  front, suites de tests, sauvegarde et restauration, sécurité des workflows, analyses CodeQL Python et JavaScript, revue des dépendances), branche à jour avant fusion,
  envois forcés et suppression de `main` interdits. Le nombre d'approbations exigé est **0** tant que le projet n'a qu'un mainteneur : à repasser à 1 dès qu'une deuxième
  personne relit.
- **Code security** : alertes Dependabot, mises à jour de sécurité Dependabot, *Secret scanning* avec *Push protection* (bloque l'envoi d'un secret) et
  *Private vulnerability reporting* (le signalement privé annoncé par `SECURITY.md`).
- **Actions** : jeton des workflows en **lecture seule** par défaut (chaque workflow demande ce dont il a besoin) ; les workflows d'un contributeur extérieur à sa première
  contribution attendent l'**approbation d'un mainteneur** (bouton « Approuver et exécuter les workflows » en bas de la demande de fusion).
- Toutes les actions des workflows sont **figées sur une empreinte de commit**, et le dépôt **l'exige** (*Actions, General, Require actions to be pinned to a full-length commit SHA*) :
  un workflow qui utiliserait une action non figée est refusé. `tests/hygiene_check.py` le contrôle aussi en amont.
- **Règle « Protection des étiquettes de version »** (cible : étiquettes `v*`) : seuls les administrateurs du dépôt peuvent créer une étiquette de version ; une étiquette
  existante ne peut être ni déplacée, ni modifiée, ni supprimée. Une version publiée ne peut donc pas être remplacée en silence.

## Dependabot

`.github/dependabot.yml` ouvre chaque lundi des demandes de fusion groupées pour les dépendances Python, npm, les images Docker, le
fichier compose et les actions GitHub. **La CI les teste avant fusion** : une mise à jour qui casse un test est visible tout de suite.
Ne fusionnez que ce qui est au vert ; lisez les notes de version des mises à jour majeures.

## Publier une version

1. Mettre à jour `CHANGELOG.md` : renommer la section **[Non publié]** en `[X.Y.Z] - date`, puis en rouvrir une vide au-dessus.
2. Vérifier que la CI est verte sur `main`.
3. Étiqueter et envoyer :
   ```bash
   git tag v0.3.0
   git push origin v0.3.0
   ```
4. Le workflow `.github/workflows/release.yml` construit et publie sur le **GitHub Container Registry** quatre images (`amd64` et `arm64`),
   `ghcr.io/gabrielfotopoto/kikan-api`, `kikan-web`, `kikan-converter` et `kikan-backup`, étiquetées `0.3.0`, `0.3` et `latest` (`latest` seulement pour une version finale, pas pour une préversion `-rc`), puis crée la
   **version GitHub** (notes générées, `docker-compose.yml`, `docker-compose.ghcr.yml` et `.env.example` en pièces jointes).
5. Au premier envoi, ouvrir chaque paquet dans *Packages* et le rendre **public** si vous voulez que d'autres puissent le télécharger sans
   identifiants (les paquets créés par un workflow sont privés par défaut).

La version s'affiche dans `/health` (variable `KIKAN_VERSION` fixée à la construction ; `dev` en développement).

## Installer à partir des images publiées

Aucune compilation sur le serveur (pas à pas complet dans le [guide d'installation](INSTALLATION.md)) :

```bash
export KIKAN_VERSION=0.3.0            # ou latest
docker compose -f docker-compose.yml -f docker-compose.ghcr.yml pull
docker compose -f docker-compose.yml -f docker-compose.ghcr.yml up -d --no-build
```

La configuration (volumes, réseaux, durcissement, variables) reste celle de `docker-compose.yml` ; seule l'origine des images change.
Mise à jour : changer `KIKAN_VERSION`, `pull`, `up -d --no-build` ; les migrations de base s'appliquent au démarrage. **Faites une
sauvegarde avant** ([SAUVEGARDE.md](SAUVEGARDE.md)).
