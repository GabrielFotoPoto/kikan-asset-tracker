---
name: kikan-securite
description: Teste la sécurité du code de Kikan. Lance les scans automatiques (Bandit, Semgrep, gitleaks, hadolint, actionlint, zizmor, audit des dépendances, hygiène) puis relit les changements avec la liste de contrôle propre à Kikan (rôles, cloisonnement par entité, journal sans donnée personnelle, secrets, fichiers, verrous). À utiliser avant une demande de fusion, après un nouvel endpoint ou une nouvelle page, ou quand on demande un audit de sécurité.
---

# /kikan-securite

Kikan manipule des données personnelles (salariés) et produit des documents qui font preuve (remises et restitutions signées et scellées).
Ce skill vérifie en deux temps : des **outils** (rapides, objectifs), puis une **relecture** guidée par les règles du projet (ce que les outils
ne voient pas : rôles, périmètre, données personnelles dans le journal).

Arguments facultatifs : `rapide` (outils seulement), `diff` (relecture seulement), ou un nom de contrôle (`bandit`, `semgrep`, `gitleaks`,
`hadolint`, `workflows`, `dependances`, `hygiene`).

## 1. Scans automatiques

Depuis la racine du dépôt (Docker requis, rien d'autre à installer) :

```bash
bash scripts/securite_scan.sh              # tout (environ une minute)
bash scripts/securite_scan.sh bandit semgrep   # seulement certains contrôles
```

| Contrôle | Cherche |
|---|---|
| `hygiene` | secrets ou fichiers sensibles versionnés, tirets longs, en-têtes de licence, actions GitHub non figées |
| `bandit` | failles Python (shell, eval, SQL construit à la main, TLS non vérifié, aléatoire faible), niveau moyen et plus |
| `semgrep` | Python, JavaScript, React, Dockerfile, secrets (règles de sécurité de la communauté) |
| `gitleaks` | secrets dans le code **et dans tout l'historique Git** |
| `hadolint` | mauvaises pratiques des Dockerfile |
| `workflows` | actionlint et zizmor sur `.github/` (injection, permissions, actions vulnérables) |
| `dependances` | pip-audit (Python) et npm audit (front, niveau haut) |

Lecture du résultat :
- **RIEN A SIGNALER** : tout est vert.
- **A TRAITER** : chaque constat est à corriger **ou** à justifier. Un faux positif se justifie dans le code, avec une phrase qui dit
  pourquoi (`# nosec B310` en fin de ligne, `# nosemgrep: <règle>` avant la ligne), ou dans `.gitleaks.toml` / `.hadolint.yaml`
  (une valeur ou une règle à la fois, jamais un dossier entier). Ne jamais désactiver un contrôle pour faire passer un scan.
- Un fichier ignoré par Git (par exemple `backend/app/docstore.py`) n'est pas analysé : il ne fait pas partie du dépôt.

## 2. Relecture des changements

Lire le diff (`git diff main...HEAD`, ou `git diff` si rien n'est commité) et vérifier, pour chaque fichier touché :

**Accès et rôles**
- Tout nouvel endpoint a une garde : `require_roles(...)`, `writer_guard(...)` ou la dépendance du routeur. Le rôle `lecture` ne modifie rien,
  le rôle `rh` n'a pas l'administration (comptes, paramétrage, stockage, RGPD, import).
- **Cloisonnement par entité** : les comptes `rh` et `lecture` peuvent être limités à des entités. Chaque lecture ou écriture passe par
  `scope_dep` / `visible_user` / `visible_assignment` ; hors périmètre, la réponse est **404** (pas 403, pour ne pas révéler l'existence).
  Le rôle `informatique` est toujours global.
- Les routes publiques sont l'exception (`/health`, connexion, mot de passe oublié, configuration SSO) et ne renvoient aucun secret.

**Données personnelles et journal**
- `audit(...)` ne reçoit **jamais** de nom, prénom, matricule, e-mail ni texte libre saisi par un utilisateur : seulement des identifiants
  techniques, des nombres et des noms de champs. Les PDF supprimés se tracent par leur empreinte SHA-256.
- Aucune donnée personnelle dans les messages d'erreur, les logs ni les e-mails de rappel (nombres seulement).
- Une purge ou une suppression passe par les règles existantes (`rules.refuse_delete`, `purge.py`) : jamais de suppression directe d'un
  PDF scellé ni d'un salarié avec historique.

**Secrets**
- Mots de passe, jetons et secrets viennent de l'environnement (`.env`), **jamais** de la base, d'un journal, d'une réponse d'API ni du dépôt.
  Les jetons d'API et de réinitialisation ne sont stockés que sous forme d'empreinte SHA-256.
- Aucune valeur secrète dans les tests autre qu'une valeur de test évidente (`kikan-test-pw-12345`).

**Entrées et fichiers**
- Clés de stockage uniquement via `filestore.safe_key` ; jamais de chemin construit avec une saisie.
- SQL uniquement par SQLModel ou SQLAlchemy ; pas de `text()` ni de f-string SQL avec une valeur venue de l'extérieur.
- Dépôts de fichiers : taille et type vérifiés (`KIKAN_MAX_*`), archives contrôlées (voir `xlsx_io.check_archive`), contenu jamais interprété.
- Adresses sortantes (SMTP, WebDAV, GLPI, SharePoint, DocuWare) fixées par l'administrateur, HTTPS vérifié ; pas d'adresse saisie par un
  utilisateur sans liste blanche (SSRF).

**Intégrité et concurrence**
- Une opération qui ne doit réussir qu'une fois (remise, signature, restitution, purge) verrouille les lignes (`with_for_update()`) et
  répond 409 au second appel.
- Les migrations sont additives (pas de perte de données) ; une nouvelle table sans donnée personnelle superflue.

**Interface (front)**
- Pas de `dangerouslySetInnerHTML`, pas de jeton ni de donnée personnelle dans l'adresse (URL), pas de `eval`. La politique CSP de
  `frontend/nginx.conf` reste respectée (pas de script ni de style externe).

**Tests**
- Chaque nouvel endpoint est ajouté à `tests/security_check.py` : sans jeton 401, rôle insuffisant 403.
- Une règle de périmètre ou de refus a son test (voir `tests/scope_check.py`) ; un verrou a un test simultané (`tests/verrous_check.py`).
- Les fichiers de test restent en ASCII ; aucun tiret long (cadratin, demi-cadratin) dans les fichiers versionnés.

## 3. Compte rendu

Terminer par un compte rendu court, en français :
1. **Scans** : tableau des contrôles (OK ou A TRAITER) et, pour chaque constat, le fichier et la ligne, la gravité, et ce qui a été fait
   (corrigé, justifié, ou à décider).
2. **Relecture** : liste des problèmes trouvés dans le diff, du plus grave au moins grave, avec fichier:ligne et la correction proposée.
   Si rien n'est trouvé, le dire clairement : « aucun problème relevé » plutôt qu'une liste de précautions génériques.
3. **Suite** : la prochaine commande à lancer (corrections, tests : `bash tests/run_all.sh`).

Ne corriger sans demander que ce qui est sans ambiguïté (faux positif à justifier, secret de test, commentaire). Pour tout le reste, présenter
la correction et attendre l'accord. Ne jamais publier ni pousser sans demande explicite.

## Aller plus loin

- La CI exécute déjà CodeQL, l'audit des dépendances, la revue des dépendances, Trivy sur les images et zizmor/actionlint sur les
  workflows ; ce skill ajoute en local Bandit, Semgrep, gitleaks et hadolint.
- Les tests de sécurité de l'application (`tests/security_check.py`, `scope_check.py`, `verrous_check.py`) se lancent avec `bash tests/run_all.sh`.
- Le modèle de sécurité, les risques acceptés et la façon de signaler une faille sont dans [SECURITY.md](../../../SECURITY.md).
