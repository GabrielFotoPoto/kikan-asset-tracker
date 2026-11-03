#!/usr/bin/env bash
# Kikan - suivi des actifs et remise de materiel signee
# Copyright (C) 2026 Gabriel Chollet
# Developpe avec l'assistance d'une IA (Claude, Anthropic).
# Licence GPLv3 (voir LICENSE).
#
# Mise a jour guidee de Kikan (Linux / macOS / Git Bash). A lancer depuis la racine du projet.
#
#   scripts/update.sh [version] [--sources] [--sans-sauvegarde]
#
# Exemples :
#   scripts/update.sh 0.5.0                  # met a jour vers la version 0.5.0 (images publiees ghcr.io)
#   scripts/update.sh                        # interroge GitHub pour trouver la derniere version publiee
#   scripts/update.sh --sources              # git pull --ff-only puis recompilation locale (methode B)
#
# Etapes : controle des variables .env par rapport a .env.example, sauvegarde de securite (si configuree),
# telechargement des nouvelles images (ou compilation), redemarrage et controle de /health.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=""
MODE=""
SKIP_BACKUP=0

for arg in "$@"; do
  case "$arg" in
    --sources) MODE="sources" ;;
    --ghcr) MODE="ghcr" ;;
    --sans-sauvegarde) SKIP_BACKUP=1 ;;
    -h|--help)
      echo "Usage : scripts/update.sh [version] [--sources] [--sans-sauvegarde]"
      exit 0
      ;;
    -*)
      echo "Option inconnue : $arg" >&2
      exit 1
      ;;
    *)
      VERSION="${arg#v}"
      ;;
  esac
done

[ -f .env ] || { echo "Fichier .env introuvable a la racine du projet." >&2; exit 1; }

# Detection automatique du mode si non precise : si KIKAN_VERSION est dans .env ou qu'une version est passee, mode images publiees.
if [ -z "$MODE" ]; then
  if [ -n "$VERSION" ] || grep -q '^KIKAN_VERSION=' .env 2>/dev/null || [ ! -d .git ]; then
    MODE="ghcr"
  else
    MODE="sources"
  fi
fi

if [ "$MODE" = "ghcr" ] && [ -z "$VERSION" ]; then
  echo "Recherche de la derniere version publiee sur GitHub..."
  TAG=$(curl -sf --max-time 10 https://api.github.com/repos/GabrielFotoPoto/kikan-asset-tracker/releases/latest \
    | sed -n 's/.*"tag_name":[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1 || true)
  VERSION="${TAG#v}"
  [ -n "$VERSION" ] || { echo "Impossible de determiner la derniere version. Indiquez-la : scripts/update.sh X.Y.Z" >&2; exit 1; }
fi

echo "== 1/4 Controle du fichier .env =="
MODEL_FILE=".env.example"
[ -f "$MODEL_FILE" ] || MODEL_FILE="default.env.example"
if [ -f "$MODEL_FILE" ]; then
  MISSING=()
  while IFS= read -r key; do
    [ -n "$key" ] || continue
    if ! grep -qE "^[[:space:]]*#?[[:space:]]*${key}=" .env; then
      MISSING+=("$key")
    fi
  done < <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$MODEL_FILE" | cut -d= -f1)
  if [ "${#MISSING[@]}" -gt 0 ]; then
    echo "Attention : variables presentes dans $MODEL_FILE mais absentes de .env : ${MISSING[*]}"
  else
    echo "Fichier .env conforme aux variables obligatoires de $MODEL_FILE."
  fi
fi

echo "== 2/4 Sauvegarde prealable =="
BACKUP_KEY=$(grep '^KIKAN_BACKUP_RECIPIENT=' .env 2>/dev/null | cut -d= -f2- | tr -d '[:space:]' || true)
if [ "$SKIP_BACKUP" -eq 1 ]; then
  echo "Sauvegarde ignoree (--sans-sauvegarde)."
elif [ -n "$BACKUP_KEY" ]; then
  if [ "$MODE" = "ghcr" ] && [ -f docker-compose.ghcr.yml ]; then
    docker compose -f docker-compose.yml -f docker-compose.ghcr.yml --profile backup run --rm backup backup
  else
    docker compose --profile backup run --rm backup backup
  fi
else
  echo "KIKAN_BACKUP_RECIPIENT non renseigne dans .env : sauvegarde ignoree (voir docs/SAUVEGARDE.md)."
fi

echo "== 3/4 Mise a jour ($MODE) =="
if [ "$MODE" = "ghcr" ]; then
  [ -f docker-compose.ghcr.yml ] || { echo "docker-compose.ghcr.yml introuvable." >&2; exit 1; }
  echo "Version cible : $VERSION"
  export KIKAN_VERSION="$VERSION"
  docker compose -f docker-compose.yml -f docker-compose.ghcr.yml pull
  if grep -q '^KIKAN_VERSION=' .env; then
    sed "s/^KIKAN_VERSION=.*/KIKAN_VERSION=$VERSION/" .env > .env.tmp && mv .env.tmp .env
  else
    printf '\nKIKAN_VERSION=%s\n' "$VERSION" >> .env
  fi
  docker compose -f docker-compose.yml -f docker-compose.ghcr.yml up -d --no-build
else
  git pull --ff-only
  docker compose up -d --build
fi

echo "== 4/4 Verification du demarrage =="
API_PORT=$(grep '^KIKAN_API_PORT=' .env 2>/dev/null | cut -d= -f2- | tr -d '[:space:]' || true)
API_PORT="${API_PORT:-8080}"
OK=0
for _ in $(seq 1 30); do
  if HEALTH=$(curl -sf "http://127.0.0.1:${API_PORT}/health" 2>/dev/null); then
    OK=1
    echo "API operationnelle : $HEALTH"
    break
  fi
  sleep 2
done

if [ "$OK" -ne 1 ]; then
  echo "L'API ne repond pas sur http://127.0.0.1:${API_PORT}/health apres 60 secondes. Verifiez : docker compose logs api" >&2
  exit 1
fi
echo "Mise a jour terminee avec succes."
