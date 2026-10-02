# dev: usado pelo docker compose, com hot reload
FROM node:22-alpine AS dev

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

FROM dev AS build
ARG VITE_API_URL
ARG VITE_WS_URL
RUN npm run build

# producao (Railway): so os estaticos servidos pelo Caddy
FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
