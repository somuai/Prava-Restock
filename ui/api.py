"""Authenticated Restock API with explicit runtime capability disclosure."""

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from common import notification_store
from channels import whatsapp
from merchant import zepto_checkout
from storage import Database, RestockRepository
from workflow import WorkflowService


ROOT = Path(__file__).resolve().parents[1]
AUDIT_LOG_PATH = ROOT / "logs" / "audit_log.json"
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"
LOCAL_DEMO_TOKEN = "restock-local-demo-token"
REPOSITORY: RestockRepository | None = None
_REQUESTS: dict[str, deque[datetime]] = defaultdict(deque)

app = FastAPI(
    title="Restock API",
    version="0.3.0",
    description="Resumable Restock workflows with explicit real/simulated labels.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv("RESTOCK_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Restock-User"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response


def get_repository() -> RestockRepository:
    global REPOSITORY
    if REPOSITORY is None:
        REPOSITORY = RestockRepository(Database())
        REPOSITORY.create_schema()
    return REPOSITORY


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
        "slack_configured": bool(os.getenv("SLACK_BOT_TOKEN") and os.getenv("SLACK_APP_TOKEN")),
        "whatsapp_configured": bool(
            os.getenv("WHATSAPP_ACCESS_TOKEN") and os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        ),
        "demo_mode": os.getenv("RESTOCK_DEMO_MODE", "1") == "1",
    }


def require_user(
    authorization: str | None = Header(default=None),
    x_restock_user: str = Header(default=DEFAULT_USER_ID),
) -> str:
    configured = os.getenv("RESTOCK_API_TOKEN")
    if not configured and os.getenv("RESTOCK_ENV") == "production":
        raise HTTPException(status_code=503, detail="RESTOCK_API_TOKEN is not configured")
    expected = configured or LOCAL_DEMO_TOKEN
    if not authorization or authorization != f"Bearer {expected}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API token")
    now = datetime.now(timezone.utc)
    window = _REQUESTS[x_restock_user]
    cutoff = now - timedelta(minutes=1)
    while window and window[0] < cutoff:
        window.popleft()
    limit = int(os.getenv("RESTOCK_RATE_LIMIT_PER_MINUTE", "120"))
    if len(window) >= limit:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit exceeded")
    window.append(now)
    return x_restock_user


class WorkflowActionRequest(BaseModel):
    action: str
    adjusted_amount: Decimal | None = Field(default=None, gt=Decimal("0"))


def _read_audit_log() -> list[dict[str, Any]]:
    if not AUDIT_LOG_PATH.exists():
        return []
    data = json.loads(AUDIT_LOG_PATH.read_text())
    if not isinstance(data, list):
        raise ValueError("audit log must contain a JSON array")
    return data


@app.get("/")
def root() -> dict[str, Any]:
    return {"service": "Restock", "status": "ok", "mode": "mixed", "capabilities": runtime_modes()}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/ready")
def readiness() -> dict[str, Any]:
    try:
        get_repository().create_schema()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ready", "capabilities": runtime_modes()}


@app.get("/capabilities")
def capabilities() -> dict[str, str | bool]:
    return runtime_modes()


@app.get("/audit-log")
def legacy_audit_log(_: str = Depends(require_user)) -> list[dict[str, Any]]:
    return _read_audit_log()


@app.get("/notifications/pending")
def legacy_pending_notifications(_: str = Depends(require_user)) -> list[dict[str, Any]]:
    return notification_store.get_pending()


@app.get("/api/v1/me")
def me(
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    value = repository.get_user(user_id)
    if value is None:
        raise HTTPException(status_code=404, detail="user not found")
    return value


@app.get("/api/v1/items")
def items(
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> list[dict[str, Any]]:
    return repository.list_items(user_id)


@app.get("/api/v1/workflows")
def workflows(
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> list[dict[str, Any]]:
    return repository.list_workflows(user_id)


@app.get("/api/v1/notifications/pending")
def pending_notifications(
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> list[dict[str, Any]]:
    return repository.pending_notifications(user_id)


@app.get("/api/v1/audit")
def audit(
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> list[dict[str, Any]]:
    return repository.list_audit(user_id)


@app.post("/api/v1/workflows/{run_id}/actions")
def workflow_action(
    run_id: str,
    body: WorkflowActionRequest,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    try:
        return WorkflowService(repository).act(
            run_id,
            user_id=user_id,
            action=body.action,
            adjusted_amount=body.adjusted_amount,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/workflows/{run_id}/approval-url")
def approval_url(
    run_id: str,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, str]:
    run = repository.get_workflow(run_id)
    if run["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="workflow belongs to a different user")
    try:
        return {"approval_url": WorkflowService(repository).approval_url(run_id)}
    except RuntimeError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc


@app.post("/api/v1/workflows/{run_id}/resume")
def resume_workflow(
    run_id: str,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    run = repository.get_workflow(run_id)
    if run["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="workflow belongs to a different user")
    try:
        return WorkflowService(repository).resume_after_passkey(run_id)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/webhooks/whatsapp")
def verify_whatsapp_webhook(
    mode: str = Query(alias="hub.mode"),
    verify_token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
) -> str:
    expected = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    if mode != "subscribe" or not expected or verify_token != expected:
        raise HTTPException(status_code=403, detail="WhatsApp verification failed")
    return challenge


@app.post("/webhooks/whatsapp")
async def whatsapp_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    raw = await request.body()
    if not whatsapp.verify_signature(raw, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="invalid WhatsApp signature")
    payload = json.loads(raw)
    processed = []
    for action in whatsapp.extract_actions(payload):
        if action["action"] == "adjust":
            processed.append({"run_id": action["run_id"], "status": "open_adjust_ui"})
            continue
        run = repository.get_workflow(action["run_id"])
        WorkflowService(repository).act(
            action["run_id"],
            user_id=run["user_id"],
            action=action["action"],
        )
        processed.append({"run_id": action["run_id"], "status": "accepted"})
    return {"processed": processed}


WEB_DIST = ROOT / "ui" / "web" / "dist"
if WEB_DIST.exists():
    app.mount("/app", StaticFiles(directory=WEB_DIST, html=True), name="web")
