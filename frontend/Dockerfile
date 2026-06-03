# --- Build stage ---
FROM node:20-bookworm-slim AS build

WORKDIR /app

# Install deps with yarn (lockfile present)
COPY package.json yarn.lock ./
RUN corepack enable && yarn install --frozen-lockfile

# Copy source and build
COPY . .

# Backend URL injected at build time (CRA bakes env into the bundle)
ARG REACT_APP_BACKEND_URL=http://localhost:8001
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

RUN yarn build

# --- Serve stage (nginx) ---
FROM nginx:1.27-alpine

# SPA-friendly nginx config (fallback to index.html)
RUN printf 'server {\n\
  listen 80;\n\
  server_name _;\n\
  root /usr/share/nginx/html;\n\
  index index.html;\n\
  location / {\n\
    try_files $uri $uri/ /index.html;\n\
  }\n\
  location ~* \\.(?:js|css|woff2?|ttf|eot|svg|png|jpg|jpeg|gif|ico|webp)$ {\n\
    expires 30d;\n\
    access_log off;\n\
    add_header Cache-Control "public, max-age=2592000, immutable";\n\
  }\n\
}\n' > /etc/nginx/conf.d/default.conf

COPY --from=build /app/build /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
