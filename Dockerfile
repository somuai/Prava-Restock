FROM node:24-alpine AS web

WORKDIR /web
COPY ui/web/package.json ui/web/package-lock.json ./
RUN npm ci
COPY ui/web/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY . .
COPY --from=web /web/dist /app/ui/web/dist
RUN python -m pip install --no-cache-dir .

# Runtime data is the only application-owned writable path. Keeping the source
# tree read-only and dropping root privileges limits the impact of a compromise.
RUN groupadd --system --gid 10001 restock \
    && useradd --system --uid 10001 --gid restock --no-create-home restock \
    && mkdir -p /app/logs \
    && chown -R restock:restock /app/logs

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=3)"]

# Production validates the complete API contract before touching schema or
# accepting traffic. Development keeps the zero-configuration local path.
CMD ["sh", "-c", "if [ \"${RESTOCK_ENV:-development}\" = \"production\" ]; then python scripts/validate_service_env.py api; fi && alembic upgrade head && exec uvicorn ui.api:app --host 0.0.0.0 --port ${PORT}"]
