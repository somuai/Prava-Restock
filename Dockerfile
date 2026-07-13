FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY . .
RUN python -m pip install --no-cache-dir .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn ui.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
