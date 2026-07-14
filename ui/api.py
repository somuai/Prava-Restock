"""Minimal read-only API for Restock's pre-hackathon deployment skeleton."""

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from common import notification_store


ROOT = Path(__file__).resolve().parents[1]
AUDIT_LOG_PATH = ROOT / "logs" / "audit_log.json"

app = FastAPI(
    title="Restock API",
    version="0.1.0",
    description="Offline-stub status surface; no live Prava credentials are required.",
)


def _read_audit_log() -> list[dict[str, Any]]:
    if not AUDIT_LOG_PATH.exists():
        return []
    data = json.loads(AUDIT_LOG_PATH.read_text())
    if not isinstance(data, list):
        raise ValueError("audit log must contain a JSON array")
    return data


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "Restock",
        "status": "ok",
        "mode": "offline-stubs",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/audit-log")
def audit_log() -> list[dict[str, Any]]:
    return _read_audit_log()


@app.get("/notifications/pending")
def pending_notifications() -> list[dict[str, Any]]:
    return notification_store.get_pending()
