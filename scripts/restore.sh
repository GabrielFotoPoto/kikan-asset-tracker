#!/usr/bin/env bash
# Kikan - suivi des actifs et remise de materiel signee
# Copyright (C) 2026 Gabriel Chollet
# Developpe avec l'assistance d'une IA (Claude, Anthropic).
# Licence GPLv3 (voir LICENSE).
#
# Restauration guidee d'une sauvegarde Kikan (Linux / Git Bash). A lancer depuis la racine du projet.
#
#   scripts/restore.sh kikan-20261029-020000.tar.gz.age /chemin/identity.txt [--sans-sauvegarde-de-securite]
#
# Etapes : confirmation, arret de l'API et du web, sauvegarde de securite de l'etat actuel, restauration (base, PDF scelles, cles,
# certificat), redemarrage, verification des empreintes. Le fichier .env n'est jamais remplace : la copie contenue dans la
# sauvegarde est ecrite dans ./restore-output/env.restored.
set -euo pipefail
ARCHIVE="${1:?Usage : scripts/restore.sh <archive> <cle-privee> [--sans-sauvegarde-de-securite]}"
IDENTITY="${2:?Cle privee requise}"
[ -f "$IDENTITY" ] || { echo "Cle privee introuvable : $IDENTITY" >&2; exit 1; }
IDENTITY="$(cd "$(dirname "$IDENTITY")" && pwd)/$(basename "$IDENTITY")"
mkdir -p ./restore-output

echo "Restauration de $ARCHIVE : la base, les PDF scelles, les cles et le certificat actuels seront REMPLACES."
read -r -p "Tapez RESTAURER pour continuer : " confirm
[ "$confirm" = "RESTAURER" ] || { echo "Annule."; exit 1; }

echo "1/4 Arret de l'API et du web..."
docker compose stop api web

if [ "${3:-}" != "--sans-sauvegarde-de-securite" ]; then
  echo "2/4 Sauvegarde de securite de l'etat actuel..."
  if ! docker compose --profile backup run --rm backup backup; then
    docker compose up -d
    echo "La sauvegarde de securite a echoue : restauration annulee, Kikan redemarre. (Serveur neuf : --sans-sauvegarde-de-securite)" >&2
    exit 1
  fi
fi

echo "3/4 Restauration..."
rc=0
KIKAN_BACKUP_IDENTITY="$IDENTITY" docker compose --profile restore run --rm restore restore "$ARCHIVE" --identity /keys/identity.txt --force || rc=$?

echo "4/4 Redemarrage..."
docker compose up -d
[ "$rc" -eq 0 ] || { echo "La restauration ou sa verification a echoue (voir ci-dessus). L'etat precedent est dans la sauvegarde de securite." >&2; exit 1; }
echo "Restauration terminee et verifiee. Comparez ./restore-output/env.restored avec votre .env si besoin."
