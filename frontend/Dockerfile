FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
RUN apk add --no-cache openssl
# Modele de configuration : les variables ${KIKAN_*} sont substituees au demarrage.
COPY nginx.conf /etc/nginx/templates/default.conf.template
# Genere un certificat TLS auto-signe au premier demarrage (volume /etc/nginx/certs).
COPY gen-cert.sh /docker-entrypoint.d/40-kikan-cert.sh
RUN chmod +x /docker-entrypoint.d/40-kikan-cert.sh
COPY --from=build /app/dist /usr/share/nginx/html
ENV KIKAN_HTTPS_PORT=3443
EXPOSE 80 443
