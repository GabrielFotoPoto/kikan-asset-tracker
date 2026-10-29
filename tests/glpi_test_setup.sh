#!/usr/bin/env bash
# Kikan - suivi des actifs et remise de materiel signee
# Copyright (C) 2026 Gabriel Chollet
# Developpe avec l'assistance d'une IA (Claude, Anthropic).
# Licence GPLv3 (voir LICENSE).
#
# Prepare une instance GLPI de TEST (jetable) pour valider le connecteur Kikan : installation, activation de l'API REST,
# acces depuis le reseau Docker, generation du jeton utilisateur. Le jeton est ecrit dans le fichier donne (jamais affiche).
#
#   tests/glpi_test_setup.sh [version] [fichier-jeton]      ex. tests/glpi_test_setup.sh 12.0.1 /tmp/glpi_token.txt
#
# Versions utiles : 12.0.1 (par defaut), 11.0.12, 10.0.28 (images officielles glpi/glpi). Detruit l'instance precedente.
# Ensuite : GLPI_TEST_TOKEN=$(cat fichier-jeton) docker compose -f docker-compose.yml -f tests/glpi-test.override.yml up -d api
# Arret et suppression : docker compose -f tests/glpi-test.yml down -v
set -euo pipefail
TAG="${1:-12.0.1}"
OUT="${2:-glpi_token.txt}"
export GLPI_TEST_TAG="$TAG"
cd "$(dirname "$0")/.."

q() { docker exec kikan-glpi-test-db mysql -uglpi -pglpi-test-only glpi -N -e "$1" 2>/dev/null; }

docker compose -f tests/glpi-test.yml down -v >/dev/null 2>&1 || true
docker compose -f tests/glpi-test.yml up -d

echo "Installation automatique de GLPI $TAG (2 a 5 minutes)..."
for _ in $(seq 1 120); do
  n=$(q "select count(*) from information_schema.tables where table_schema='glpi'" || echo 0)
  if [ "${n:-0}" -gt 300 ] && curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8088/ | grep -q 200 \
     && [ "$(q "select count(*) from glpi_users" || echo 0)" -ge 5 ]; then break; fi
  sleep 5
done
[ "${n:-0}" -gt 300 ] || { echo "Installation de GLPI trop longue ou en echec" >&2; exit 1; }

# API REST : activation, acces depuis le reseau Docker, pas de jeton d'application (client API sans jeton)
q "update glpi_configs set value=1 where name in ('enable_api','enable_api_login_credentials')"
q "update glpi_apiclients set ipv4_range_start=0, ipv4_range_end=4294967295, app_token=NULL where id=1"

# Jeton utilisateur du compte glpi (id 2) : genere par GLPI lui-meme, puis lu (en clair en 10.x, chiffre en 11.x et 12.x)
sess=$(curl -s -u glpi:glpi http://127.0.0.1:8088/apirest.php/initSession | sed -E 's/.*"session_token":"([^"]+)".*/\1/')
curl -s -X PUT -H "Session-Token: $sess" -H 'Content-Type: application/json' \
  -d '{"input":{"id":2,"_reset_api_token":1}}' http://127.0.0.1:8088/apirest.php/User/2 >/dev/null
curl -s -H "Session-Token: $sess" http://127.0.0.1:8088/apirest.php/killSession >/dev/null
raw=$(q "select api_token from glpi_users where id=2")
if [ "${#raw}" -eq 40 ]; then
  printf '%s\n' "$raw" > "$OUT"
else
  docker exec -e ENC="$raw" kikan-glpi-test php -r '
    $key = file_get_contents("/var/glpi/config/glpicrypt.key");
    $s = base64_decode(getenv("ENC")); $n = SODIUM_CRYPTO_AEAD_XCHACHA20POLY1305_IETF_NPUBBYTES;
    echo sodium_crypto_aead_xchacha20poly1305_ietf_decrypt(substr($s, $n), substr($s, 0, $n), substr($s, 0, $n), $key);' > "$OUT"
fi
[ -s "$OUT" ] || { echo "Jeton non obtenu" >&2; exit 1; }
echo "GLPI $TAG pret : http://127.0.0.1:8088 (compte glpi / glpi), jeton ecrit dans $OUT"
