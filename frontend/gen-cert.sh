#!/bin/sh
# Genere un certificat TLS auto-signe si absent.
# Pour un usage reel, montez le certificat de l'organisation dans /etc/nginx/certs
# (kikan.crt et kikan.key) : ce script n'y touchera pas.
set -e
CERT_DIR=/etc/nginx/certs
mkdir -p "$CERT_DIR"
if [ ! -f "$CERT_DIR/kikan.key" ] || [ ! -f "$CERT_DIR/kikan.crt" ]; then
  SAN="DNS:localhost,IP:127.0.0.1"
  [ -n "$KIKAN_TLS_SAN" ] && SAN="$SAN,$KIKAN_TLS_SAN"
  echo "kikan: generation d'un certificat auto-signe (SAN: $SAN)"
  openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
    -keyout "$CERT_DIR/kikan.key" -out "$CERT_DIR/kikan.crt" \
    -subj "/CN=${KIKAN_TLS_CN:-localhost}/O=Kikan" \
    -addext "subjectAltName=$SAN"
  chmod 600 "$CERT_DIR/kikan.key"
fi
