#!/usr/bin/env bash
# Kikan - suivi des actifs et remise de materiel signee
# Copyright (C) 2026 Gabriel Chollet
# Developpe avec l'assistance d'une IA (Claude, Anthropic).
# Licence GPLv3 (voir LICENSE).
#
# Mise a jour guidee de Kikan sur un serveur Linux (Debian, Ubuntu, RHEL). A lancer depuis la racine du projet.
# La verification periodique des mises a jour dans l'interface est active par defaut (KIKAN_UPDATE_CHECK=true) ;
# mettre KIKAN_UPDATE_CHECK=false dans .env sur un serveur sans acces a Internet.
#
#   scripts/update.sh [version] [--sources] [--oui] [--sans-sauvegarde] [--forcer-version]
#
# Exemples :
#   scripts/update.sh 0.5.0                  # met a jour vers la version 0.5.0 (images publiees ghcr.io)
#   scripts/update.sh                        # interroge GitHub pour trouver la derniere version publiee
#   scripts/update.sh --sources              # git pull --ff-only de main puis recompilation locale (methode B)
#
# Etapes : controle de Docker et de la version cible, confirmation, controle des variables .env par rapport a .env.example,
# sauvegarde de securite obligatoire avec verification d'integrite (sauf --sans-sauvegarde), telechargement des nouvelles images
# (ou compilation), redemarrage et controle de la version renvoyee par /health.
set -euo pipefail
cd "$(dirname "$0")/.."
trap 'rm -f .env.tmp' EXIT

VERSION=""
MODE=""
SKIP_BACKUP=0
ASSUME_YES=0
FORCE_VERSION=0

for arg in "$@"; do
  case "$arg" in
    --sources) MODE="sources" ;;
    --ghcr) MODE="ghcr" ;;
    --sans-sauvegarde) SKIP_BACKUP=1 ;;
    --oui|-y) ASSUME_YES=1 ;;
    --forcer-version) FORCE_VERSION=1 ;;
    -h|--help)
      echo "Usage : scripts/update.sh [version] [--sources] [--oui] [--sans-sauvegarde] [--forcer-version]"
      echo "  [version]          Version cible (ex. 0.5.0) pour le mode images publiees (ghcr.io)."
      echo "  --sources          Met a jour la branche Git courante (git pull --ff-only) et recompile les images."
      echo "  --oui              Ne demande pas de confirmation interactive."
      echo "  --sans-sauvegarde  Ne lance pas de sauvegarde prealable (deconseille en production)."
      echo "  --forcer-version   Autorise la reinstallation de la meme version ou un retour arriere."
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

if ! docker compose version >/dev/null 2>&1; then
  echo "Erreur : 'docker compose' (plugin Compose v2) est introuvable. Installez docker-compose-plugin." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Erreur : impossible de communiquer avec le demon Docker (verifiez que le service tourne et que votre utilisateur a les droits)." >&2
  exit 1
fi

read_env() {
  grep -E "^${1}=" .env 2>/dev/null | tail -n 1 | cut -d= -f2- | tr -d '\r' || true
}

# Comparaison de deux versions semver X.Y.Z[-pre] : renvoie 0 si $1 > $2, 1 si $1 == $2, 2 si $1 < $2.
# Note : deux suffixes de preversion d'une meme version X.Y.Z sont compares par ordre lexicographique (sans effet sur les versions finales).
semver_cmp() {
  local v1="${1#v}" v2="${2#v}"
  if [ "$v1" = "$v2" ]; then return 1; fi
  local b1="${v1%%-*}" b2="${v2%%-*}"
  local p1="" p2=""
  [ "$v1" != "$b1" ] && p1="${v1#*-}"
  [ "$v2" != "$b2" ] && p2="${v2#*-}"
  local a1=() a2=()
  IFS=. read -r -a a1 <<< "$b1"
  IFS=. read -r -a a2 <<< "$b2"
  for i in 0 1 2; do
    local n1="${a1[$i]:-0}" n2="${a2[$i]:-0}"
    if [ "$n1" -gt "$n2" ]; then return 0; fi
    if [ "$n1" -lt "$n2" ]; then return 2; fi
  done
  if [ -z "$p1" ] && [ -n "$p2" ]; then return 0; fi
  if [ -n "$p1" ] && [ -z "$p2" ]; then return 2; fi
  if [[ "$p1" > "$p2" ]]; then return 0; else return 2; fi
}

CURRENT_VERSION=$(read_env KIKAN_VERSION | tr -d '[:space:]')
CURRENT_VERSION="${CURRENT_VERSION#v}"

if [ -z "$MODE" ]; then
  if [ -n "$VERSION" ] || [ -n "$CURRENT_VERSION" ] || [ ! -d .git ]; then
    MODE="ghcr"
  else
    MODE="sources"
  fi
fi

if [ "$MODE" = "ghcr" ]; then
  if [ -z "$VERSION" ]; then
    echo "Recherche de la derniere version publiee sur GitHub..."
    CURL_ARGS=(-sf --max-time 10)
    PROXY=$(read_env KIKAN_UPDATE_PROXY)
    [ -z "$PROXY" ] && PROXY=$(read_env KIKAN_SSO_PROXY)
    [ -n "$PROXY" ] && CURL_ARGS+=(--proxy "$PROXY")
    CA_BUNDLE=$(read_env KIKAN_UPDATE_CA_BUNDLE)
    [ -z "$CA_BUNDLE" ] && CA_BUNDLE=$(read_env KIKAN_SSO_CA_BUNDLE)
    [ -n "$CA_BUNDLE" ] && [ -f "$CA_BUNDLE" ] && CURL_ARGS+=(--cacert "$CA_BUNDLE")
    CHECK_URL=$(read_env KIKAN_UPDATE_CHECK_URL)
    [ -z "$CHECK_URL" ] && CHECK_URL="https://api.github.com/repos/GabrielFotoPoto/kikan-asset-tracker/releases/latest"
    TAG=$(curl "${CURL_ARGS[@]}" "$CHECK_URL" | sed -n 's/.*"tag_name":[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1 || true)
    VERSION="${TAG#v}"
    [ -n "$VERSION" ] || { echo "Impossible de determiner la derniere version. Indiquez-la : scripts/update.sh X.Y.Z" >&2; exit 1; }
  fi

  if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
    echo "Numero de version invalide : '$VERSION' (format attendu : X.Y.Z ou X.Y.Z-rc.N)." >&2
    exit 1
  fi

  if [ -n "$CURRENT_VERSION" ] && [[ "$CURRENT_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]] && [ "$FORCE_VERSION" -eq 0 ]; then
    set +e
    semver_cmp "$VERSION" "$CURRENT_VERSION"
    cmp_rc=$?
    set -e
    if [ "$cmp_rc" -eq 1 ]; then
      echo "Kikan est deja en version $VERSION (utilisez --forcer-version pour reinstaller)."
      exit 0
    elif [ "$cmp_rc" -eq 2 ]; then
      echo "Refus du retour arriere de $CURRENT_VERSION vers $VERSION : la base de donnees peut avoir migre." >&2
      echo "Pour revenir a un etat anterieur, restaurez la sauvegarde (scripts/restore.sh) ou passez --forcer-version." >&2
      exit 1
    fi
  fi
fi

echo "================================================================"
echo "Mise a jour de Kikan (mode : $MODE)"
if [ "$MODE" = "ghcr" ]; then
  echo "  Version actuelle : ${CURRENT_VERSION:-non definie}"
  echo "  Version cible    : $VERSION"
else
  echo "  Branche Git      : $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'inconnue') (git pull --ff-only)"
fi
echo "  Important        : lisez la section 'Mise a jour depuis' de CHANGELOG.md avant de continuer."
echo "================================================================"

if [ "$ASSUME_YES" -eq 0 ]; then
  read -r -p "Continuer la mise a jour ? [o/N] : " confirm
  case "$confirm" in
    o|O|oui|OUI|y|Y) ;;
    *) echo "Annule."; exit 1 ;;
  esac
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
BACKUP_KEY=$(read_env KIKAN_BACKUP_RECIPIENT | tr -d '[:space:]')
if [ "$SKIP_BACKUP" -eq 1 ]; then
  echo "Sauvegarde ignoree (--sans-sauvegarde)."
elif [ -n "$BACKUP_KEY" ]; then
  COMPOSE_ARGS=(-f docker-compose.yml)
  if [ "$MODE" = "ghcr" ] && [ -f docker-compose.ghcr.yml ]; then
    COMPOSE_ARGS+=(-f docker-compose.ghcr.yml)
  fi
  docker compose "${COMPOSE_ARGS[@]}" --profile backup run --rm -T backup backup
  STATUS_JSON=$(docker compose "${COMPOSE_ARGS[@]}" --profile backup run --rm -T backup status 2>/dev/null || true)
  ARCHIVE_NAME=$(printf '%s' "$STATUS_JSON" | sed -n 's/.*"fichier":[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1 || true)
  ARCHIVE_SIZE=$(printf '%s' "$STATUS_JSON" | sed -n 's/.*"taille":[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -n 1 || true)
  LAST_ERR=$(printf '%s' "$STATUS_JSON" | sed -n 's/.*"dernier_echec":[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1 || true)
  if [ -z "$ARCHIVE_NAME" ] || [ -z "$ARCHIVE_SIZE" ] || [ "$ARCHIVE_SIZE" -le 0 ] || [ -n "$LAST_ERR" ]; then
    echo "Erreur : l'etat de la sauvegarde prealable n'a pas pu etre valide (fichier : '${ARCHIVE_NAME:-aucun}', taille : '${ARCHIVE_SIZE:-0}')." >&2
    exit 1
  fi
  SMB_SRV=$(read_env KIKAN_BACKUP_SMB_SERVER | tr -d '[:space:]')
  if [ -z "$SMB_SRV" ]; then
    BACKUP_DIR=$(read_env KIKAN_BACKUP_DIR | tr -d '[:space:]')
    BACKUP_DIR="${BACKUP_DIR:-./backups}"
    if [ -d "$BACKUP_DIR" ]; then
      if [ ! -s "${BACKUP_DIR}/${ARCHIVE_NAME}" ] || [ ! -s "${BACKUP_DIR}/${ARCHIVE_NAME}.sha256" ]; then
        echo "Erreur : archive '${BACKUP_DIR}/${ARCHIVE_NAME}' ou fichier .sha256 introuvable ou vide." >&2
        exit 1
      fi
      if command -v sha256sum >/dev/null 2>&1; then
        (cd "$BACKUP_DIR" && sha256sum -c "${ARCHIVE_NAME}.sha256" >/dev/null)
      fi
    fi
  fi
  echo "Sauvegarde verifiee : $ARCHIVE_NAME ($ARCHIVE_SIZE octets)."
else
  echo "Erreur : aucune sauvegarde n'est configuree (KIKAN_BACKUP_RECIPIENT absent de .env)." >&2
  echo "Configurez la sauvegarde (docs/SAUVEGARDE.md) avant de mettre a jour, ou passez explicitement --sans-sauvegarde." >&2
  exit 1
fi

echo "== 3/4 Mise a jour ($MODE) =="
if [ "$MODE" = "ghcr" ]; then
  [ -f docker-compose.ghcr.yml ] || { echo "docker-compose.ghcr.yml introuvable." >&2; exit 1; }
  export KIKAN_VERSION="$VERSION"
  docker compose -f docker-compose.yml -f docker-compose.ghcr.yml pull
  cp -p .env .env.tmp
  if grep -q '^KIKAN_VERSION=' .env; then
    awk -v ver="$VERSION" 'BEGIN{FS=OFS="="} $1=="KIKAN_VERSION"{$2=ver} {print}' .env > .env.tmp
  else
    cat .env > .env.tmp
    printf '\nKIKAN_VERSION=%s\n' "$VERSION" >> .env.tmp
  fi
  cat .env.tmp > .env
  rm -f .env.tmp
  docker compose -f docker-compose.yml -f docker-compose.ghcr.yml up -d --no-build
else
  git pull --ff-only
  docker compose up -d --build
fi

echo "== 4/4 Verification du demarrage =="
API_PORT=$(read_env KIKAN_API_PORT | tr -d '[:space:]')
API_PORT="${API_PORT:-8080}"
OK=0
REPORTED_VER=""
for _ in $(seq 1 30); do
  if HEALTH=$(curl -sf "http://127.0.0.1:${API_PORT}/health" 2>/dev/null); then
    REPORTED_VER=$(printf '%s' "$HEALTH" | sed -n 's/.*"version":[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1 || true)
    REPORTED_VER="${REPORTED_VER#v}"
    if [ "$MODE" = "ghcr" ] && [ -n "$VERSION" ] && [ "$REPORTED_VER" != "$VERSION" ]; then
      sleep 2
      continue
    fi
    OK=1
    echo "API operationnelle : $HEALTH"
    break
  fi
  sleep 2
done

if [ "$OK" -ne 1 ]; then
  echo "Echec : l'API ne repond pas avec la version attendue sur http://127.0.0.1:${API_PORT}/health apres 60 secondes (version recue : '${REPORTED_VER:-aucune}')." >&2
  echo "Consultez les journaux : docker compose logs --tail 80 api" >&2
  echo "Si une migration de base a echoue, restaurez la sauvegarde prealable avec scripts/restore.sh (revenir a l'ancienne image ne suffit pas apres une migration)." >&2
  exit 1
fi
echo "Mise a jour terminee avec succes."
