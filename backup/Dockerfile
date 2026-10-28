# Image de sauvegarde et de restauration de Kikan : pg_dump et pg_restore 16 (comme la base), age (chiffrement), SMB (smbprotocol).
FROM postgres:16

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv age ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir smbprotocol==1.17.0 psycopg2-binary

ENV PATH=/opt/venv/bin:$PATH
WORKDIR /app
COPY kikan_backup.py test_retention.py /app/
ENTRYPOINT ["python", "/app/kikan_backup.py"]
