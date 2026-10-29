#!/usr/bin/env bash
# Kikan - suivi des actifs et remise de materiel signee
# Copyright (C) 2026 Gabriel Chollet
# Developpe avec l'assistance d'une IA (Claude, Anthropic).
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Licence GPLv3 (voir LICENSE).
#
# Jeu de donnees de DEMONSTRATION (groupe fictif, 52 salaries, materiel, vrais PDF scelles...) pour montrer ou tester Kikan.
#
#   scripts/demo.sh charger    # charge le jeu (refuse si la base contient deja des donnees reelles)
#   scripts/demo.sh etat       # combien d'elements de demonstration
#   scripts/demo.sh effacer    # retire tout ce que le jeu a cree, et seulement cela (PDF scelles compris)
#
# Prerequis : la pile Kikan demarree (docker compose up -d) et un fichier .env avec KIKAN_ADMIN_PASSWORD.
# KIKAN_PREFIX (defaut : kikan) designe la pile visee ; KIKAN_TEST_PREFIX=kiktest pour la pile de test de tests/run_all.sh.
set -uo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1

ACTION="${1:-}"
case "$ACTION" in charger|effacer|etat) ;; *) echo "Usage : scripts/demo.sh charger | effacer | etat" >&2; exit 2 ;; esac
PFX="${KIKAN_PREFIX:-kikan}"
PW="${KIKAN_ADMIN_PASSWORD:-$(grep '^KIKAN_ADMIN_PASSWORD=' .env 2>/dev/null | cut -d= -f2-)}"
[ -n "$PW" ] || { echo "KIKAN_ADMIN_PASSWORD absent (fichier .env ou variable d'environnement)" >&2; exit 1; }
docker ps --format '{{.Names}}' | grep -qx "$PFX-api" || { echo "Le conteneur $PFX-api n'est pas demarre (docker compose up -d)" >&2; exit 1; }

docker exec -i -e DEMO_ACTION="$ACTION" -e TEST_ADMIN_USER="${KIKAN_ADMIN_USER:-admin}" -e "TEST_ADMIN_PASSWORD=$PW" "$PFX-api" python - < scripts/demo_data.py
