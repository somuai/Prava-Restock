"""Authenticated Restock API with explicit runtime capability disclosure."""

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import os
import logging
from pathlib import Path
import time
from typing import Any
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from common import notification_store
from common import password_auth
from common import session_auth
from channels import whatsapp
from channels.slack_routes import router as slack_service_router
from workflow.service_routes import router as worker_service_router
from merchant import swiggy_checkout, zepto_checkout
from storage import Database, RestockRepository
from workflow import WorkflowService
from scripts.validate_service_env import validate as validate_service_environment


ROOT = Path(__file__).resolve().parents[1]
AUDIT_LOG_PATH = ROOT / "logs" / "audit_log.json"
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"
LOCAL_DEMO_TOKEN = "restock-local-demo-token"
REPOSITORY: RestockRepository | None = None
_REQUESTS: dict[str, deque[datetime]] = defaultdict(deque)
_AUTH_REQUESTS: dict[str, deque[datetime]] = defaultdict(deque)
_METRICS: dict[str, float] = defaultdict(float)
LOGGER = logging.getLogger("restock.api")

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
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Restock-User"],
)
app.include_router(slack_service_router)
app.include_router(worker_service_router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid4())
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        _METRICS["http_errors_total"] += 1
        LOGGER.exception(json.dumps({
            "event": "request_failed",
            "correlation_id": correlation_id,
            "method": request.method,
            "path": request.url.path,
        }))
        raise
    elapsed_ms = (time.perf_counter() - started) * 1000
    _METRICS["http_requests_total"] += 1
    _METRICS["http_latency_ms_sum"] += elapsed_ms
    if response.status_code >= 500:
        _METRICS["http_errors_total"] += 1
    LOGGER.info(json.dumps({
        "event": "request_completed",
        "correlation_id": correlation_id,
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "latency_ms": round(elapsed_ms, 2),
    }))
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response


def get_repository() -> RestockRepository:
    global REPOSITORY
    if REPOSITORY is None:
        REPOSITORY = RestockRepository(Database())
        if os.getenv("RESTOCK_ENV", "development") != "production":
            REPOSITORY.create_schema()
    return REPOSITORY


def runtime_modes() -> dict[str, str | bool]:
    prava_key = os.getenv("PRAVA_API_KEY", "").strip()
    prava_url = (
        os.getenv("PRAVA_API_URL", "").strip()
        or os.getenv("PRAVA_SANDBOX_URL", "").strip()
    ).rstrip("/")
    if prava_key.startswith("sk_live_") and prava_url == "https://api.prava.space":
        prava_mode = (
            "production_configured"
            if os.getenv("PRAVA_PRODUCTION_ENABLED") == "1"
            else "production_disabled"
        )
    elif (
        prava_key.startswith("sk_test_")
        and prava_url == "https://sandbox.api.prava.space"
    ):
        prava_mode = "sandbox_configured"
    else:
        prava_mode = "sandbox_unconfigured"
    slack_configured = all(
        os.getenv(name, "").strip()
        for name in (
            "SLACK_BOT_TOKEN",
            "SLACK_APP_TOKEN",
            "SLACK_SIGNING_SECRET",
            "SLACK_CHANNEL_ID",
            "RESTOCK_SLACK_SERVICE_TOKEN",
            "RESTOCK_PUBLIC_API_URL",
            "RESTOCK_PUBLIC_APP_URL",
        )
    )
    runtime_ready_check = getattr(zepto_checkout, "real_payment_runtime_ready", None)
    zepto_runtime_ready = bool(
        callable(runtime_ready_check) and runtime_ready_check()
    )
    return {
        "prava_mode": prava_mode,
        "home_merchant_mode": zepto_checkout.merchant_mode().value,
        "swiggy_payment_mode": swiggy_checkout.payment_mode().value,
        "teams_billing_mode": "disclosed_mock",
        "real_money_enabled": (
            zepto_checkout.merchant_mode().value == "real"
            and os.getenv("ZEPTO_REAL_PAYMENT_ENABLED") == "1"
            and prava_mode == "production_configured"
            and zepto_runtime_ready
        ),
        "home_checkout_runtime_configured": zepto_runtime_ready,
        "slack_configured": slack_configured,
        "whatsapp_configured": all(
            os.getenv(name, "").strip()
            for name in (
                "WHATSAPP_ACCESS_TOKEN",
                "WHATSAPP_PHONE_NUMBER_ID",
                "WHATSAPP_APP_SECRET",
                "WHATSAPP_VERIFY_TOKEN",
            )
        ),
        "demo_mode": os.getenv("RESTOCK_DEMO_MODE", "1") == "1",
    }


def production_configuration_issues() -> list[str]:
    """Reuse the production API startup contract and return names only."""
    if os.getenv("RESTOCK_ENV", "development") != "production":
        return []
    issues = validate_service_environment("api", os.environ)
    if (
        zepto_checkout.merchant_mode().value == "real"
        and os.getenv("ZEPTO_REAL_PAYMENT_ENABLED") == "1"
    ):
        runtime_ready_check = getattr(zepto_checkout, "real_payment_runtime_ready", None)
        if not callable(runtime_ready_check) or not runtime_ready_check():
            issues.append("ZEPTO_REAL_CHECKOUT_RUNTIME_UNAVAILABLE")
    return sorted(set(issues))


def require_user(
    authorization: str | None = Header(default=None),
    x_restock_user: str = Header(default=DEFAULT_USER_ID),
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API token")
    token = authorization.removeprefix("Bearer ")
    environment = os.getenv("RESTOCK_ENV", "development")
    configured = os.getenv("RESTOCK_API_TOKEN")
    legacy_expected = configured or LOCAL_DEMO_TOKEN
    if environment != "production" and token == legacy_expected:
        user_id = x_restock_user
    else:
        secret = os.getenv("RESTOCK_SESSION_SECRET", "")
        if not secret:
            raise HTTPException(status_code=503, detail="RESTOCK_SESSION_SECRET is not configured")
        try:
            user_id = session_auth.verify(token, secret)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    now = datetime.now(timezone.utc)
    window = _REQUESTS[user_id]
    cutoff = now - timedelta(minutes=1)
    while window and window[0] < cutoff:
        window.popleft()
    limit = int(os.getenv("RESTOCK_RATE_LIMIT_PER_MINUTE", "120"))
    if len(window) >= limit:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit exceeded")
    window.append(now)
    return user_id


class WorkflowActionRequest(BaseModel):
    action: str
    adjusted_amount: Decimal | None = Field(default=None, gt=Decimal("0"))


class SoloLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


def _enforce_login_rate_limit(
    request: Request,
    repository: RestockRepository,
    session_secret: str,
) -> None:
    source = request.client.host if request.client else "unknown"
    limit = max(1, int(os.getenv("RESTOCK_AUTH_RATE_LIMIT_PER_MINUTE", "5")))
    if os.getenv("RESTOCK_ENV", "development") == "production":
        if repository.database.engine.dialect.name != "postgresql":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="authentication unavailable",
            )
        source_hash = hmac.new(
            session_secret.encode("utf-8"),
            source.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        try:
            allowed = repository.consume_login_attempt(
                source_hash=source_hash,
                limit=limit,
                window_seconds=60,
            )
        except Exception as exc:
            LOGGER.error(json.dumps({"event": "auth_rate_limit_unavailable"}))
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="authentication unavailable",
            ) from exc
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="too many login attempts",
            )
        return

    now = datetime.now(timezone.utc)
    window = _AUTH_REQUESTS[source]
    cutoff = now - timedelta(minutes=1)
    while window and window[0] < cutoff:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many login attempts",
        )
    window.append(now)


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str


class InvitationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: str


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=20)


class ConsentRequest(BaseModel):
    kind: str = Field(min_length=1, max_length=40)
    granted: bool


class ApprovalPolicyRequest(BaseModel):
    max_amount: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(min_length=3, max_length=3)
    required_approvals: int = Field(ge=1, le=20)


class ApprovalDecisionRequest(BaseModel):
    decision: str
    required_approvals: int = Field(default=1, ge=1, le=20)


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
    issues = production_configuration_issues()
    if issues:
        LOGGER.error(json.dumps({"event": "production_configuration_invalid", "issues": issues}))
        raise HTTPException(status_code=503, detail="production configuration incomplete")
    try:
        repository = get_repository()
        if os.getenv("RESTOCK_ENV", "development") == "production":
            with repository.database.engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
        else:
            repository.create_schema()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ready", "capabilities": runtime_modes()}


@app.get("/capabilities")
def capabilities() -> dict[str, str | bool]:
    return runtime_modes()


@app.post("/api/v1/auth/login")
def solo_login(payload: SoloLoginRequest, request: Request) -> dict[str, str | int]:
    password_hash = os.getenv("RESTOCK_SOLO_PASSWORD_HASH", "").strip()
    user_id = os.getenv("RESTOCK_SOLO_USER_ID", "").strip()
    session_secret = os.getenv("RESTOCK_SESSION_SECRET", "")
    if (
        not password_auth.is_supported_hash(password_hash)
        or not user_id
        or len(session_secret) < 32
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication unavailable",
        )
    try:
        UUID(user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication unavailable",
        ) from exc
    try:
        repository = get_repository()
    except Exception as exc:
        LOGGER.error(json.dumps({"event": "authentication_store_unavailable"}))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication unavailable",
        ) from exc
    _enforce_login_rate_limit(request, repository, session_secret)
    if not password_auth.verify_password(payload.password, password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )
    try:
        owner = repository.get_user(user_id)
    except Exception as exc:
        LOGGER.error(json.dumps({"event": "authentication_store_unavailable"}))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication unavailable",
        ) from exc
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication unavailable",
        )
    ttl_seconds = int(os.getenv("RESTOCK_SESSION_TTL_SECONDS", "3600"))
    ttl_seconds = min(max(ttl_seconds, 300), 86400)
    return {
        "access_token": session_auth.mint(user_id, session_secret, ttl_seconds),
        "token_type": "bearer",
        "expires_in": ttl_seconds,
    }


@app.get("/metrics")
def metrics() -> dict[str, float]:
    count = _METRICS["http_requests_total"]
    return {
        "http_requests_total": count,
        "http_errors_total": _METRICS["http_errors_total"],
        "http_latency_ms_average": _METRICS["http_latency_ms_sum"] / count if count else 0.0,
    }


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
    x_restock_tenant: str | None = Header(default=None),
    repository: RestockRepository = Depends(get_repository),
) -> list[dict[str, Any]]:
    try:
        return repository.list_items(user_id, x_restock_tenant)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.get("/api/v1/tenants")
def tenants(
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> list[dict[str, Any]]:
    return repository.list_tenants(user_id)


@app.post("/api/v1/tenants", status_code=201)
def create_tenant(
    body: TenantCreateRequest,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    try:
        return repository.create_tenant(name=body.name, kind=body.kind, owner_user_id=user_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/tenants/{tenant_id}/members")
def tenant_members(
    tenant_id: str,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> list[dict[str, Any]]:
    try:
        return repository.list_members(tenant_id, user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.post("/api/v1/tenants/{tenant_id}/invitations", status_code=201)
def invite_member(
    tenant_id: str,
    body: InvitationRequest,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    try:
        return repository.invite_member(
            tenant_id=tenant_id,
            actor_user_id=user_id,
            email=body.email,
            role=body.role,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/invitations/accept")
def accept_invitation(
    body: InvitationAcceptRequest,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    try:
        return repository.accept_invitation(token=body.token, user_id=user_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/v1/tenants/{tenant_id}/consents/me")
def update_consent(
    tenant_id: str,
    body: ConsentRequest,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    try:
        return repository.set_consent(
            tenant_id=tenant_id,
            user_id=user_id,
            kind=body.kind,
            granted=body.granted,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.post("/api/v1/tenants/{tenant_id}/approval-policies", status_code=201)
def create_approval_policy(
    tenant_id: str,
    body: ApprovalPolicyRequest,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    try:
        return repository.create_approval_policy(
            tenant_id=tenant_id,
            actor_user_id=user_id,
            max_amount=body.max_amount,
            currency=body.currency,
            required_approvals=body.required_approvals,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.post("/api/v1/tenants/{tenant_id}/workflows/{run_id}/decisions")
def decide_workflow(
    tenant_id: str,
    run_id: str,
    body: ApprovalDecisionRequest,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    try:
        return repository.record_approval_decision(
            tenant_id=tenant_id,
            run_id=run_id,
            user_id=user_id,
            decision=body.decision,
            required_approvals=body.required_approvals,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/privacy/export")
def privacy_export(
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    return repository.privacy_export(user_id)


@app.delete("/api/v1/privacy/me", status_code=204)
def privacy_delete(
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> None:
    repository.delete_user_data(user_id)


@app.get("/api/v1/tenants/{tenant_id}/forecasting/observations")
def forecast_observations(
    tenant_id: str,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> list[dict[str, Any]]:
    try:
        return repository.list_forecast_observations(tenant_id=tenant_id, user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.delete("/api/v1/tenants/{tenant_id}/forecasting/observations")
def delete_forecast_observations(
    tenant_id: str,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, int]:
    try:
        return {"deleted": repository.delete_forecast_observations(tenant_id=tenant_id, user_id=user_id)}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


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


@app.post("/api/v1/workflows/{run_id}/reconcile-checkout")
def reconcile_checkout(
    run_id: str,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    run = repository.get_workflow(run_id)
    if run["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="workflow belongs to a different user")
    try:
        return WorkflowService(repository).reconcile_checkout(run_id)
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
