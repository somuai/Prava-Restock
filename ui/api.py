"""Read-only status API used until Phase 9 adds resumable actions."""

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from common import notification_store
from merchant import zepto_checkout


ROOT = Path(__file__).resolve().parents[1]
AUDIT_LOG_PATH = ROOT / "logs" / "audit_log.json"

app = FastAPI(
    title="Restock API",
    version="0.1.0",
    description="Restock status surface with explicit real/simulated capability labels.",
)


def runtime_modes() -> dict[str, str | bool]:
    prava_configured = os.getenv("PRAVA_API_KEY", "").startswith("sk_test_")
    return {
        "prava_mode": "sandbox_configured" if prava_configured else "sandbox_unconfigured",
        "home_merchant_mode": zepto_checkout.merchant_mode().value,
        "teams_billing_mode": "disclosed_mock",
        "real_money_enabled": (
            zepto_checkout.merchant_mode().value == "real"
            and os.getenv("ZEPTO_REAL_PAYMENT_ENABLED") == "1"
        ),
    }


def _read_audit_log() -> list[dict[str, Any]]:
    if not AUDIT_LOG_PATH.exists():
        return []
    data = json.loads(AUDIT_LOG_PATH.read_text())
    if not isinstance(data, list):
        raise ValueError("audit log must contain a JSON array")
    return data


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "Restock",
        "status": "ok",
        "mode": "mixed",
        "capabilities": runtime_modes(),
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/capabilities")
def capabilities() -> dict[str, str | bool]:
    return runtime_modes()


@app.get("/audit-log")
def audit_log() -> list[dict[str, Any]]:
    return _read_audit_log()


@app.get("/notifications/pending")
def pending_notifications() -> list[dict[str, Any]]:
    return notification_store.get_pending()
