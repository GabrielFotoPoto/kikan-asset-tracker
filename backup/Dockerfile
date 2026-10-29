# Image de sauvegarde et de restauration de Kikan : pg_dump et pg_restore 16 (comme la base), age (chiffrement), SMB (smbprotocol).
FROM postgres:16@sha256:1beaa3084eee2676f20a9cd9928f0bf2c5bf674f8e49f81017912183d377c61c

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv age ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir smbprotocol==1.17.0 psycopg2-binary

ENV PATH=/opt/venv/bin:$PATH
WORKDIR /app
COPY kikan_backup.py test_retention.py /app/
# Execute en root a dessein : la sauvegarde ecrit sur un partage ou un dossier de l'hote (droits DAC_READ_SEARCH et DAC_OVERRIDE, voir
# docs/SAUVEGARDE.md) ; le conteneur n'ecoute aucun port et n'est lance que par le profil backup ou restore.
# nosemgrep: dockerfile.security.missing-user-entrypoint.missing-user-entrypoint
ENTRYPOINT ["python", "/app/kikan_backup.py"]
