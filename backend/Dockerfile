FROM python:3.12-slim

# Utilisateur non privilegie ; /certs et /archive sont les volumes d'ecriture.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin kikan \
 && mkdir -p /certs /archive \
 && chown kikan:kikan /certs /archive

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

# Version affichee par /health (positionnee a la construction des images publiees)
ARG KIKAN_VERSION=dev
ENV KIKAN_VERSION=$KIKAN_VERSION

USER kikan
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
