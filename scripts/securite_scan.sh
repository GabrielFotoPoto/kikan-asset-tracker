#!/usr/bin/env bash
# Kikan - suivi des actifs et remise de materiel signee
# Copyright (C) 2026 Gabriel Chollet
# Developpe avec l'assistance d'une IA (Claude, Anthropic).
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Licence GPLv3 (voir LICENSE).
#
# Analyse de securite du code, en local, sans rien installer (Docker seulement). Utilise par le skill /kikan-securite.
#
#   scripts/securite_scan.sh                 # tout
#   scripts/securite_scan.sh bandit gitleaks # seulement ces controles
#
# Controles : hygiene, bandit (code Python), semgrep (Python, JavaScript, React, Dockerfile), gitleaks (secrets, historique compris),
# hadolint (Dockerfile), workflows (actionlint, zizmor), dependances (pip-audit, npm audit).
# Code de sortie 1 si un controle echoue. Les faux positifs connus sont justifies dans le code (# nosec, # nosemgrep) ou dans
# .gitleaks.toml et .hadolint.yaml : un nouveau constat est donc a traiter, pas a ignorer.
set -uo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
ROOT="$(pwd -W 2>/dev/null || pwd)"

# Images figees par empreinte (reproductible) ; a rafraichir avec Dependabot ou a la main.
SEMGREP=semgrep/semgrep@sha256:451b3d875c00dac7ed5db5293e584a07de11449a409c10b3c2d2652f429630b6
GITLEAKS=zricethezav/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f
HADOLINT=hadolint/hadolint@sha256:32dac94127fd60b7b7e3fbfc65e1383b9b5e25c9bfd7b8536de7a539fe68a12d
ACTIONLINT=rhysd/actionlint@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667
ZIZMOR=ghcr.io/zizmorcore/zizmor@sha256:42d409dbb851d4c5d35a058cf042b828bea1e3f2884378c526eb0974780e18d9
BANDIT=bandit==1.9.4

ALL=(hygiene bandit semgrep gitleaks hadolint workflows dependances)
SELECTED=("$@")
[ ${#SELECTED[@]} -gt 0 ] || SELECTED=("${ALL[@]}")
SUMMARY=()
FAILED=0

run() {  # run <nom> <commande...> : affiche la sortie si echec
  local name="$1"; shift
  local out rc
  out=$("$@" 2>&1); rc=$?
  if [ "$rc" -eq 0 ]; then
    SUMMARY+=("$(printf '%-14s OK' "$name")")
  else
    FAILED=1
    SUMMARY+=("$(printf '%-14s A TRAITER' "$name")")
    echo "---- $name ----"
    printf '%s\n' "$out" | grep -vE '^(Unable to find image|[0-9a-f]{12}: |Digest:|Status:)' | tail -60
  fi
}

c_hygiene()   { python3 tests/hygiene_check.py 2>/dev/null || python tests/hygiene_check.py; }
c_bandit() {
  # Fichiers suivis par Git seulement (un fichier local ignore n'est pas analyse) ; medium et plus.
  git ls-files 'backend/app/*.py' 'backend/app/**/*.py' 'backend/migrations/*.py' 'backup/*.py' 'scripts/*.py' > "$ROOT/.bandit-files.tmp" 2>/dev/null
  docker run --rm -v "$ROOT:/src:ro" -w //src python:3.12-slim sh -c \
    "pip install -q $BANDIT >/dev/null 2>&1 && bandit -ll -q -f custom --msg-template '{test_id} {severity}/{confidence} {relpath}:{line} {msg}' \$(cat .bandit-files.tmp)"
  local rc=$?; rm -f "$ROOT/.bandit-files.tmp"; return $rc
}
c_semgrep()   { docker run --rm -v "$ROOT:/src:ro" -w //src "$SEMGREP" semgrep scan --metrics off --quiet --error \
                  --config p/python --config p/javascript --config p/react --config p/dockerfile --config p/secrets \
                  --exclude node_modules --exclude tests --exclude docs --exclude backend/app/docstore.py \
                  --severity ERROR --severity WARNING; }
c_gitleaks()  { docker run --rm -v "$ROOT:/repo:ro" "$GITLEAKS" detect --source /repo --config /repo/.gitleaks.toml --no-banner --redact --exit-code 1; }
c_hadolint() {
  local rc=0 f
  for f in backend/Dockerfile frontend/Dockerfile converter/Dockerfile backup/Dockerfile; do
    docker run --rm -i -v "$ROOT/.hadolint.yaml:/.hadolint.yaml:ro" "$HADOLINT" hadolint --config /.hadolint.yaml - < "$f" || { echo "(dans $f)"; rc=1; }
  done
  return $rc
}
c_workflows() {
  docker run --rm -v "$ROOT:/repo:ro" -w //repo "$ACTIONLINT" || return 1
  docker run --rm -v "$ROOT:/repo:ro" -w //repo "$ZIZMOR" --offline --no-progress --min-severity medium .github
}
c_dependances() {
  docker run --rm -v "$ROOT/backend/requirements.txt:/r.txt:ro" -v "$ROOT/tests/audit_deps.py:/a.py:ro" python:3.12-slim python /a.py || return 1
  docker run --rm -v "$ROOT/frontend:/app:ro" -w //tmp/app node:20-alpine sh -c \
    "cp -r /app/package.json /app/package-lock.json /tmp/app/ 2>/dev/null; cd /tmp/app && npm ci --silent --ignore-scripts >/dev/null 2>&1 && npm audit --omit=dev --audit-level=high"
}

for s in "${SELECTED[@]}"; do
  case " ${ALL[*]} " in *" $s "*) run "$s" "c_$s" ;; *) echo "Controle inconnu : $s (attendus : ${ALL[*]})" >&2; exit 2 ;; esac
done

echo
echo "================ Analyse de securite ================"
printf '%s\n' "${SUMMARY[@]}"
[ "$FAILED" -eq 0 ] && echo "RIEN A SIGNALER" || echo "A TRAITER : voir les constats ci-dessus"
exit "$FAILED"
