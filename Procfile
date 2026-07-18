web: alembic upgrade head && uvicorn ui.api:app --host 0.0.0.0 --port ${PORT:-8000}
worker: python -m workflow.worker
slack: python -m channels.slack_app
