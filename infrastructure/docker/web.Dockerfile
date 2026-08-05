# syntax=docker/dockerfile:1
#
# React dashboard.
#
# Built with Node, served as static files by nginx. The runtime image contains
# no Node and no source — just the compiled bundle, which keeps it small and
# removes a whole class of runtime dependencies.

# ---------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /build

# `npm ci` needs both files and is cached until the lockfile changes.
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web/ ./
RUN npm run build

# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

COPY infrastructure/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

# 127.0.0.1, not `localhost`: inside the container `localhost` also resolves to
# ::1, busybox wget tries IPv6 first and does not fall back, and nginx listens
# on IPv4 only. Using the literal address avoids a container that serves fine
# being reported unhealthy — which would stall anything gated on
# `depends_on: condition: service_healthy`.
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
