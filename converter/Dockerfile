# Kikan : service isole de conversion Word (.docx) vers PDF.
# Aucun acces a Internet (reseau interne), systeme de fichiers en lecture seule, utilisateur non privilegie.
# Les polices Carlito et Caladea sont metriquement compatibles avec Calibri et Cambria (mise en page fidele).
FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

RUN apt-get update \
 && apt-get install -y --no-install-recommends libreoffice-writer fonts-liberation fonts-dejavu-core \
        fonts-crosextra-carlito fonts-crosextra-caladea \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10002 --no-create-home --shell /usr/sbin/nologin converter

COPY server.py /srv/server.py
USER converter
EXPOSE 8090
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8090/health', timeout=3)"]
CMD ["python", "/srv/server.py"]
