# Le dist est du JavaScript statique, identique pour toutes les architectures : on le construit sur la machine de build
# (pas sous emulation QEMU, dont `npm ci` plantait par moments en arm64).
FROM --platform=$BUILDPLATFORM node:26-alpine@sha256:6bd9ab43c0ec0190ca7b2d193906cb8b7edf6e7f4afa43ddeccd6452710bffb5 AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.29-alpine@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de
RUN apk add --no-cache openssl
# Modele de configuration : les variables ${KIKAN_*} sont substituees au demarrage.
COPY nginx.conf /etc/nginx/templates/default.conf.template
# Genere un certificat TLS auto-signe au premier demarrage (volume /etc/nginx/certs).
COPY gen-cert.sh /docker-entrypoint.d/40-kikan-cert.sh
RUN chmod +x /docker-entrypoint.d/40-kikan-cert.sh
COPY --from=build /app/dist /usr/share/nginx/html
ENV KIKAN_HTTPS_PORT=3443
EXPOSE 80 443
