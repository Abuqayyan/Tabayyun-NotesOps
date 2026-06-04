# syntax=docker/dockerfile:1

# =========================================================================
# Build stage — compile the CRA/CRACO SPA into static assets
# =========================================================================
FROM node:20-bookworm-slim AS build

WORKDIR /app

# Use the package manager pinned in package.json ("packageManager": "yarn@1.22.22").
# corepack ships with Node 20 and provisions that exact Yarn version automatically.
RUN corepack enable

# --- Dependency layer (cached independently of source changes) ---
# yarn.lock is copied via a glob so the image still builds before a lockfile is
# committed. When the lockfile IS present we install with --frozen-lockfile for a
# reproducible build; otherwise we resolve fresh against the registry.
# The BuildKit cache mount keeps Yarn's package cache warm across rebuilds.
COPY package.json yarn.lock* ./
RUN --mount=type=cache,target=/usr/local/share/.cache/yarn \
    if [ -f yarn.lock ]; then \
        echo "yarn.lock found — installing with --frozen-lockfile"; \
        yarn install --frozen-lockfile --network-timeout 600000 \
          || { echo "WARNING: lockfile drift — repairing lockfile"; yarn install --network-timeout 600000; }; \
    else \
        echo "WARNING: no yarn.lock — resolving a fresh tree (non-reproducible)"; \
        yarn install --network-timeout 600000; \
    fi

# --- Source + build ---
COPY . .

# CRA bakes env vars into the bundle at build time, so the backend URL is a build ARG.
ARG REACT_APP_BACKEND_URL=http://localhost:8001
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

RUN yarn build

# =========================================================================
# Serve stage — minimal nginx image serving the static build
# =========================================================================
FROM nginx:1.27-alpine

# SPA routing, gzip, asset caching, and a /healthz endpoint live in nginx.conf.
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=build /app/build /usr/share/nginx/html

EXPOSE 80

# Probe the dedicated health endpoint (cheap, never cached, no SPA fallback noise).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/healthz >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
