FROM node:24-alpine AS web

WORKDIR /web
COPY ui/web/package.json ui/web/package-lock.json ./
RUN npm ci
COPY ui/web/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY . .
COPY --from=web /web/dist /app/ui/web/dist
RUN python -m pip install --no-cache-dir .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn ui.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
