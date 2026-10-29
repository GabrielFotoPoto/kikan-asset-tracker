#!/usr/bin/env bash
# Kikan - suivi des actifs et remise de materiel signee
# Copyright (C) 2026 Gabriel Chollet
# Developpe avec l'assistance d'une IA (Claude, Anthropic).
# Licence GPLv3 (voir LICENSE).
#
# Rejoue TOUTES les suites de tests sur la pile de DEVELOPPEMENT (jamais sur une production : les tests creent puis nettoient des
# donnees ZZ...). Utilise par l'integration continue (.github/workflows/ci.yml) et en local.
#
#   tests/run_all.sh                 # tout, sauf la sauvegarde de bout en bout
#   tests/run_all.sh --avec-sauvegarde   # + tests/backup_check.py (restauration dans une instance vierge, plus long)
#   tests/run_all.sh security_check crud_check   # seulement ces suites (mode normal)
#
# Prerequis : Docker, un fichier .env (POSTGRES_PASSWORD, KIKAN_ADMIN_PASSWORD, KIKAN_SECRET_KEY) ; la pile db, converter et api
# est demarree par ce script. Code de sortie 1 si une suite echoue.
set -uo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1

ENV_ADMIN_PW=$(grep '^KIKAN_ADMIN_PASSWORD=' .env | cut -d= -f2-)
[ -n "$ENV_ADMIN_PW" ] || { echo "KIKAN_ADMIN_PASSWORD absent de .env" >&2; exit 1; }
WITH_BACKUP=0
ONLY=()
for a in "$@"; do
  case "$a" in --avec-sauvegarde) WITH_BACKUP=1 ;; *) ONLY+=("$a") ;; esac
done

NORMAL_SUITES=(security_check functional_smoke signature_check policy_check import_check crud_check parametres_check accounts_check
               acces_pdf_check catalogue_check xlsx_check besoins_check scope_check mail_check api_check storage_check verrous_check purge_check import_annulation_check)
SUMMARY=()
FAILED=0

wait_api() {
  for _ in $(seq 1 60); do
    curl -sf http://localhost:8080/health >/dev/null 2>&1 && return 0
    sleep 2
  done
  echo "L'API ne repond pas" >&2
  return 1
}

# up_api <fichiers compose -f ...> ; env GLPI_TEST_TOKEN facultatif
up_api() {
  docker compose "$@" up -d --force-recreate api >/dev/null 2>&1 || true
  wait_api
}

cleanup_data() {
  docker exec -i kikan-db psql -U kikan -d kikan < tests/cleanup_test_data.sql >/dev/null 2>&1 || true
}

# suite <nom> : execute tests/<nom>.py dans l'API, enregistre PASS/FAIL
suite() {
  local name="$1" label="${2:-$1}" out pass fail
  cleanup_data
  out=$(docker exec -i -e TEST_ADMIN_USER=admin -e "TEST_ADMIN_PASSWORD=$ENV_ADMIN_PW" kikan-api python - < "tests/$name.py" 2>&1)
  local rc=$?
  pass=$(printf '%s\n' "$out" | grep -c '^PASS')
  fail=$(printf '%s\n' "$out" | grep -c '^FAIL')
  # Echec = une ligne FAIL, ou un code de sortie non nul (suite plantee). Certaines suites affichent des traces d'erreur ATTENDUES
  # (validation d'un certificat auto-signe, par exemple) : leur seule presence n'est pas un echec.
  if [ "$rc" -ne 0 ] && [ "$fail" -eq 0 ]; then fail=1; fi
  if [ "$pass" -eq 0 ] && [ "$fail" -eq 0 ]; then fail=1; fi
  SUMMARY+=("$(printf '%-34s PASS=%-4s FAIL=%s' "$label" "$pass" "$fail")")
  if [ "$fail" -ne 0 ]; then
    FAILED=1
    printf '%s\n' "$out" | grep -E '^FAIL|^Traceback|^[A-Za-z.]*Error' | head -12
  fi
}

echo "== Demarrage de la pile =="
docker compose up -d --build db converter api >/dev/null 2>&1 || { echo "Demarrage de la pile impossible" >&2; docker compose logs --tail 40 2>&1; exit 1; }
wait_api || { docker compose logs --tail 60 api; exit 1; }

if [ ${#ONLY[@]} -gt 0 ]; then
  for s in "${ONLY[@]}"; do suite "$s"; done
else
  echo "== Hygiene du depot =="
  if python3 tests/hygiene_check.py >/tmp/hygiene.out 2>&1 || python tests/hygiene_check.py >/tmp/hygiene.out 2>&1; then
    SUMMARY+=("$(printf '%-34s OK' 'hygiene_check')")
  else
    cat /tmp/hygiene.out | grep -E '^FAIL' ; SUMMARY+=("$(printf '%-34s ECHEC' 'hygiene_check')"); FAILED=1
  fi

  echo "== Suites en configuration normale =="
  for s in "${NORMAL_SUITES[@]}"; do suite "$s"; done

  echo "== Connecteur GLPI (faux GLPI integre) =="
  up_api -f docker-compose.yml -f tests/glpi-test.override.yml
  suite glpi_check

  echo "== Stockage SharePoint et DocuWare (faux services integres) =="
  up_api -f docker-compose.yml -f tests/storage-sharepoint.override.yml
  suite documents_check "documents_check (sharepoint)"
  up_api -f docker-compose.yml -f tests/storage-docuware.override.yml
  suite documents_check "documents_check (docuware)"

  echo "== Connexion Microsoft 365 (faux fournisseur d'identite) =="
  up_api -f docker-compose.yml -f tests/sso-test.override.yml
  suite sso_check

  echo "== Mot de passe oublie (adresse publique d'essai) =="
  up_api -f docker-compose.yml -f tests/reset-test.override.yml
  suite reset_check

  echo "== Retour a la configuration normale =="
  up_api -f docker-compose.yml
  cleanup_data

  if [ "$WITH_BACKUP" -eq 1 ]; then
    echo "== Sauvegarde et restauration de bout en bout =="
    if python3 tests/backup_check.py >/tmp/backup.out 2>&1 || python tests/backup_check.py >/tmp/backup.out 2>&1; then
      SUMMARY+=("$(printf '%-34s PASS=%-4s FAIL=0' 'backup_check' "$(grep -c '^PASS' /tmp/backup.out)")")
    else
      grep -E '^FAIL' /tmp/backup.out | head -10
      SUMMARY+=("$(printf '%-34s ECHEC' 'backup_check')"); FAILED=1
    fi
    cleanup_data
  fi
fi

echo
echo "================ Resume ================"
printf '%s\n' "${SUMMARY[@]}"
if [ "$FAILED" -eq 0 ]; then echo "TOUT EST VERT"; else echo "AU MOINS UNE SUITE EN ECHEC"; fi
exit "$FAILED"
