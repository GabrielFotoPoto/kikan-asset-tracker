FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

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
ARG KIKAN_RELEASE_DATE=
ENV KIKAN_RELEASE_DATE=$KIKAN_RELEASE_DATE

USER kikan
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
