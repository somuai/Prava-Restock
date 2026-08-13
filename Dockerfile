FROM node:24-alpine AS web

WORKDIR /web
COPY ui/web/package.json ui/web/package-lock.json ./
RUN npm ci
COPY ui/web/ ./
RUN npm run build

FROM node:24-alpine AS waitlist

WORKDIR /waitlist
COPY ui/waitlist/package.json ui/waitlist/package-lock.json ./
RUN npm ci
COPY ui/waitlist/ ./
RUN npm run build

FROM node:24-slim AS node-runtime

WORKDIR /opt/zepto-mcp
COPY merchant/mcp-runtime/package.json merchant/mcp-runtime/package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts

# Keep the browser runtime aligned with the pinned Python Playwright package.
# The upstream Playwright image already contains Chromium and its native OS
# dependencies. Installing them at build time from a moving Debian slim image
# caused builds to fail when distro package names changed.
FROM mcr.microsoft.com/playwright/python:v1.52.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/restock \
    MCP_REMOTE_CONFIG_DIR=/home/restock/.mcp-auth \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PORT=8000

WORKDIR /app

COPY . .
COPY --from=web /web/dist /app/ui/web/dist
COPY --from=waitlist /waitlist/dist /app/ui/waitlist/dist
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /opt/zepto-mcp /opt/zepto-mcp
RUN python -m pip install --no-cache-dir -e .

# Runtime data is the only application-owned writable path. Keeping the source
# tree read-only and dropping root privileges limits the impact of a compromise.
RUN groupadd --system --gid 10001 restock \
    && useradd --system --uid 10001 --gid restock --home-dir /home/restock --create-home restock \
    && mkdir -p /app/logs /home/restock/.mcp-auth \
    && chown -R restock:restock /app/logs /home/restock \
    && node --version \
    && test -x /opt/zepto-mcp/node_modules/.bin/mcp-remote

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=3)"]

# Production validates the complete API contract before touching schema or
# accepting traffic. Development keeps the zero-configuration local path.
CMD ["sh", "-c", "python scripts/materialize_zepto_oauth_cache.py && unset ZEPTO_MCP_AUTH_CACHE_B64 && if [ \"${RESTOCK_ENV:-development}\" = \"production\" ] && [ \"${RESTOCK_STRICT_VALIDATE:-0}\" = \"1\" ]; then python scripts/validate_service_env.py api; fi && (alembic upgrade head || (echo 'Alembic upgrade failed, stamping head and retrying...' && alembic stamp head && alembic upgrade head)) && if [ -n \"${RESTOCK_REVIEWER_USER_ID:-}\" ]; then if [ \"${RESTOCK_REVIEWER_RESET_ON_DEPLOY:-0}\" = \"1\" ]; then python scripts/provision_reviewer.py --reset-history; else python scripts/provision_reviewer.py; fi; fi && exec env PYTHONPATH=/app uvicorn ui.api:app --host 0.0.0.0 --port ${PORT}"]
