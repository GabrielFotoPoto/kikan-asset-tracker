# Publier une version et utiliser l'intégration continue

## Ce que fait l'intégration continue

À chaque envoi sur `main` et à chaque demande de fusion, GitHub Actions (`.github/workflows/ci.yml`) rejoue **les mêmes contrôles qu'en local** :

| Travail | Contenu |
|---|---|
| Hygiène du dépôt | pas de tiret long, tests en ASCII, en-têtes de licence, aucun secret ni fichier sensible versionné, code Python compilable, YAML et JSON valides (`tests/hygiene_check.py`) |
| Audit des dépendances | `pip-audit` (Python) et `npm audit` (front, niveau élevé) |
| Compilation du front | `npm ci` puis `npm run build` |
| Suites de tests | la pile complète (base, convertisseur, API) puis **toutes les suites** : sécurité, fonctionnel, signatures, chartes, import, comptes, cloisonnement, e-mails, API, GLPI (faux GLPI), SharePoint et DocuWare (faux services), SSO (faux fournisseur) (`tests/run_all.sh`) |
| Sauvegarde et restauration | restauration dans une instance vierge, mauvaise clé, archive altérée, partage Samba (`tests/backup_check.py`) |
| Images Docker | construction des quatre images (api, web, convertisseur, sauvegarde) et analyse Trivy (information, ne bloque pas) |

Le fichier `.env` de la CI est fabriqué avec des secrets aléatoires jetables : aucun secret réel n'est nécessaire. Le nom du projet Docker Compose
est fixé à `kikan` (`COMPOSE_PROJECT_NAME`), car les tests supposent les réseaux et volumes `kikan_*` ; en local, le dossier du projet doit donc
s'appeler `kikan`, ou la variable être définie de la même façon.

**En local** : `bash tests/run_all.sh` (tout), `bash tests/run_all.sh --avec-sauvegarde` (plus la sauvegarde de bout en bout),
`bash tests/run_all.sh security_check crud_check` (certaines suites), `python tests/hygiene_check.py` (hygiène seule). Uniquement sur une
pile de **développement** : les tests créent puis nettoient des données `ZZ...`.

## Réglages GitHub (appliqués le 2026-10-29, à contrôler de temps en temps)

Dans le dépôt : protection de `main` (demande de fusion et contrôles de la CI obligatoires, envois forcés et suppression interdits), analyse des secrets avec blocage à l'envoi, alertes Dependabot et mises à jour de sécurité, signalement privé des vulnérabilités, approbation obligatoire des workflows des contributeurs extérieurs, actions exigées sur empreinte de commit, étiquettes `v*` protégées.

## Réglages GitHub recommandés (référence)

*Settings du dépôt* :

- **Branches, règle de protection de `main`** : exiger les contrôles *Hygiène du dépôt*, *Audit des dépendances*, *Compilation du front*,
  *Suites de tests* et *Sauvegarde et restauration* avant fusion, interdire les envois forcés.
- **Code security** : activer *Dependabot alerts*, *Dependabot security updates*, *Secret scanning* avec *Push protection* (bloque l'envoi
  d'un secret) et *Private vulnerability reporting* (déjà mentionné dans `SECURITY.md`).
- **Actions, General** : *Workflow permissions* en lecture seule par défaut (les workflows demandent eux-mêmes ce dont ils ont besoin).

## Dependabot

`.github/dependabot.yml` ouvre chaque lundi des demandes de fusion groupées pour les dépendances Python, npm, les images Docker, le
fichier compose et les actions GitHub. **La CI les teste avant fusion** : une mise à jour qui casse un test est visible tout de suite.
Ne fusionnez que ce qui est au vert ; lisez les notes de version des mises à jour majeures.

## Publier une version

1. Mettre à jour `CHANGELOG.md` (déplacer la section « à publier » sous le numéro et la date).
2. Vérifier que la CI est verte sur `main`.
3. Étiqueter et envoyer :
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```
4. Le workflow `.github/workflows/release.yml` construit et publie sur le **GitHub Container Registry** quatre images,
   `ghcr.io/gabrielfotopoto/kikan-api`, `kikan-web`, `kikan-converter` et `kikan-backup`, étiquetées `0.2.0`, `0.2` et `latest`, puis crée la
   **version GitHub** (notes générées, `docker-compose.yml`, `docker-compose.ghcr.yml` et `.env.example` en pièces jointes).
5. Au premier envoi, ouvrir chaque paquet dans *Packages* et le rendre **public** si vous voulez que d'autres puissent le télécharger sans
   identifiants (les paquets créés par un workflow sont privés par défaut).

La version s'affiche dans `/health` (variable `KIKAN_VERSION` fixée à la construction ; `dev` en développement).

## Installer à partir des images publiées

Aucune compilation sur le serveur :

```bash
export KIKAN_VERSION=0.2.0            # ou latest
docker compose -f docker-compose.yml -f docker-compose.ghcr.yml pull
docker compose -f docker-compose.yml -f docker-compose.ghcr.yml up -d --no-build
```

La configuration (volumes, réseaux, durcissement, variables) reste celle de `docker-compose.yml` ; seule l'origine des images change.
Mise à jour : changer `KIKAN_VERSION`, `pull`, `up -d --no-build` ; les migrations de base s'appliquent au démarrage. **Faites une
sauvegarde avant** ([SAUVEGARDE.md](SAUVEGARDE.md)).
