"""Authenticated Restock API with explicit runtime capability disclosure."""

from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import os
import logging
from pathlib import Path
import re
import secrets
import time
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError

from common import audit_store, notification_store
from common import password_auth
from common import session_auth
from common.secret_encryption import (
    SecretDecryptionError,
    SecretEncryptionConfigurationError,
    decrypt_secret,
    encrypt_secret,
)
from common.starter_items import (
    STARTER_TEMPLATE_SUMMARIES,
    StarterTemplateId,
    build_starter_item,
    starter_template_sku,
)
from common.google_identity import (
    GoogleIdentityConfigurationError,
    GoogleIdentityError,
    verify_google_identity,
)
from channels import whatsapp
from channels.slack_routes import router as slack_service_router
from workflow.service_routes import router as worker_service_router
from merchant import saas_invoice_checkout, swiggy_checkout, zepto_checkout
from merchant.zepto_mcp import (
    ZeptoMCPClient,
    ZeptoMCPError,
    ZeptoRateLimitError,
    ZeptoTransientError,
    mcp_authorization_verified_recently,
    mcp_remote_runtime_ready,
)
from merchant.zepto_oauth import (
    ZeptoOAuthConfigurationError,
    ZeptoOAuthError,
    ZeptoOAuthToken,
    begin_authorization as begin_zepto_authorization,
    exchange_authorization_code,
    oauth_is_configured as zepto_oauth_is_configured,
    refresh_access_token,
)
from storage import Database, RestockRepository
from workflow import WorkflowService
from workflow.factory import (
    build_workflow_service,
    configure_merchant_runtime,
    configure_teams_runtime,
)
from scripts.validate_service_env import validate as validate_service_environment


ROOT = Path(__file__).resolve().parents[1]
WAITLIST_DIST = ROOT / "ui" / "waitlist" / "dist"
AUDIT_LOG_PATH = audit_store.AUDIT_STORE_PATH
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"
LOCAL_DEMO_TOKEN = "restock-local-demo-token"
SESSION_COOKIE_NAME = "restock_session"
AUTH_MODES = {"solo", "hybrid", "google"}
REPOSITORY: RestockRepository | None = None
_REQUESTS: dict[str, deque[datetime]] = defaultdict(deque)
_AUTH_REQUESTS: dict[str, deque[datetime]] = defaultdict(deque)
_WAITLIST_REQUESTS: dict[str, deque[datetime]] = defaultdict(deque)
_WAITLIST_RATE_SECRET = secrets.token_bytes(32)
_METRICS: dict[str, float] = defaultdict(float)
LOGGER = logging.getLogger("restock.api")
UNSAFE_HTTP_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
NON_PRODUCTION_BROWSER_ORIGINS = frozenset(
    {
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://testserver",
    }
)

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
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Restock-User"],
)
app.include_router(slack_service_router)
app.include_router(worker_service_router)


def _trusted_cookie_origin(request: Request) -> bool:
    """Require an exact trusted Origin for browser cookie mutations."""

    origin = request.headers.get("Origin", "").strip().rstrip("/")
    if not origin:
        return False
    allowed = {
        configured.strip().rstrip("/")
        for configured in os.getenv(
            "RESTOCK_ALLOWED_ORIGINS", "http://localhost:5173"
        ).split(",")
        if configured.strip()
    }
    if os.getenv("RESTOCK_ENV", "development") != "production":
        allowed.update(NON_PRODUCTION_BROWSER_ORIGINS)
    return origin in allowed


def _authorization_token(authorization: str) -> str | None:
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme != "Bearer" or not token.strip():
        return None
    return token.strip()


def _resolve_api_token(token: str, x_restock_user: str) -> str:
    environment = os.getenv("RESTOCK_ENV", "development")
    configured = os.getenv("RESTOCK_API_TOKEN")
    legacy_expected = configured or LOCAL_DEMO_TOKEN
    if environment != "production" and token == legacy_expected:
        return x_restock_user
    secret = os.getenv("RESTOCK_SESSION_SECRET", "")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="RESTOCK_SESSION_SECRET is not configured",
        )
    try:
        return session_auth.verify(token, secret)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


def _has_valid_authorization(request: Request) -> bool:
    authorization = request.headers.get("Authorization")
    if authorization is None:
        return False
    token = _authorization_token(authorization)
    if token is None:
        return False
    try:
        _resolve_api_token(
            token,
            request.headers.get("X-Restock-User", DEFAULT_USER_ID),
        )
    except HTTPException:
        return False
    return True


def _requires_cookie_origin_check(request: Request) -> bool:
    if request.method.upper() not in UNSAFE_HTTP_METHODS:
        return False
    if not request.cookies.get(SESSION_COOKIE_NAME):
        return False
    return not _has_valid_authorization(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid4())
    started = time.perf_counter()
    if _requires_cookie_origin_check(request) and not _trusted_cookie_origin(request):
        response = JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "untrusted request origin"},
        )
    else:
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
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "object-src 'none'; "
        "script-src 'self' https://accounts.google.com/gsi/client; "
        "frame-src https://accounts.google.com/gsi/; "
        "connect-src 'self' https://accounts.google.com/gsi/; "
        "style-src 'self' 'unsafe-inline' https://accounts.google.com/gsi/style"
    )
    return response


def _auth_mode() -> str:
    return os.getenv("RESTOCK_AUTH_MODE", "solo").strip().lower()


def _auth_method_enabled(method: str) -> bool:
    mode = _auth_mode()
    return mode in AUTH_MODES and (mode == "hybrid" or mode == method)


def get_repository() -> RestockRepository:
    global REPOSITORY
    if REPOSITORY is None:
        REPOSITORY = RestockRepository(Database())
        if os.getenv("RESTOCK_ENV", "development") != "production":
            REPOSITORY.create_schema()
    return REPOSITORY


def _merchant_runtime_status() -> tuple[bool, str]:
    """Compose local dependencies without leaking paths or provider details."""

    executable = os.getenv("ZEPTO_PAYMENT_EXECUTOR_PATH", "").strip()
    if executable:
        path = Path(executable)
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            zepto_checkout.configure_real_checkout_runtime(None)
            return False, "invalid_configuration"
    try:
        configure_merchant_runtime(get_repository())
    except (OSError, RuntimeError, ValueError):
        zepto_checkout.configure_real_checkout_runtime(None)
        return False, "invalid_configuration"
    ready_check = getattr(zepto_checkout, "real_payment_runtime_ready", None)
    ready = bool(callable(ready_check) and ready_check())
    return ready, "configured" if ready else "unavailable"


def _teams_runtime_status() -> tuple[bool, str]:
    executable = os.getenv("TEAMS_PAYMENT_EXECUTOR_PATH", "").strip()
    if executable:
        path = Path(executable)
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            saas_invoice_checkout.configure_runtime(None)
            return False, "invalid_configuration"
    try:
        configure_teams_runtime(get_repository())
    except (OSError, RuntimeError, ValueError):
        saas_invoice_checkout.configure_runtime(None)
        return False, "invalid_configuration"
    ready = saas_invoice_checkout.real_payment_runtime_ready()
    return ready, "configured" if ready else "unavailable"


def _zepto_oauth_status() -> str:
    """Report cache presence only; cached authorization is never claimed verified."""

    if mcp_authorization_verified_recently():
        return "verified_recently"
    config_dir = Path(
        os.getenv("MCP_REMOTE_CONFIG_DIR", str(Path.home() / ".mcp-auth"))
    ).expanduser()
    try:
        configured = False
        for version_dir in config_dir.glob("mcp-remote-*"):
            token_files = list(version_dir.glob("*_tokens.json"))
            for token_file in token_files:
                prefix = token_file.name.removesuffix("_tokens.json")
                required = (
                    version_dir / f"{prefix}_client_info.json",
                    version_dir / f"{prefix}_code_verifier.txt",
                    token_file,
                )
                if all(path.is_file() for path in required):
                    configured = True
                    break
            if configured:
                break
    except OSError:
        configured = False
    return "configured_unverified" if configured else "unknown"


def runtime_modes() -> dict[str, str | bool]:
    # Composition is local and side-effect-free: it does not contact Zepto.
    # This makes readiness truthful before the first workflow request.
    zepto_runtime_ready, zepto_runtime_status = _merchant_runtime_status()
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
    oauth_status = _zepto_oauth_status()
    user_oauth_configured = zepto_oauth_is_configured()
    mcp_runtime_ready = mcp_remote_runtime_ready()
    teams_runtime_ready, teams_runtime_status = _teams_runtime_status()
    production = os.getenv("RESTOCK_ENV", "development") == "production"
    demo_disabled = os.getenv("RESTOCK_DEMO_MODE", "1") == "0"
    cart_ready = (
        os.getenv("ZEPTO_CART_PREPARATION_ENABLED") == "1"
        and bool(os.getenv("ZEPTO_DEVICE_ID", "").strip())
    )
    home_catalog_real = zepto_checkout.merchant_mode().value == "real"
    home_catalog_operational = home_catalog_real and user_oauth_configured
    return {
        "auth_mode": _auth_mode(),
        "google_auth_configured": bool(os.getenv("GOOGLE_CLIENT_ID", "").strip()),
        "reviewer_access_configured": all(
            os.getenv(name, "").strip()
            for name in (
                "RESTOCK_REVIEWER_PASSWORD_HASH",
                "RESTOCK_REVIEWER_USER_ID",
                "RESTOCK_REVIEWER_EXPIRES_AT",
            )
        ),
        # OAuth client IDs are public identifiers. Returning this at runtime
        # avoids baking environment-specific IDs into the Vite bundle.
        "google_client_id": (
            os.getenv("GOOGLE_CLIENT_ID", "").strip()
            if _auth_method_enabled("google")
            else ""
        ),
        "prava_mode": prava_mode,
        "home_merchant_mode": zepto_checkout.merchant_mode().value,
        "home_catalog_operational": home_catalog_operational,
        # Live catalog access is user-owned: OAuth is configured globally, but
        # each signed-in person must complete Zepto's consent flow before
        # addresses, history suggestions, or catalog results are available.
        "zepto_user_oauth_mode": "per_user_pkce",
        "zepto_user_oauth_configured": user_oauth_configured,
        "home_onboarding_mode": (
            "live_zepto"
            if home_catalog_real
            else "local_fixtures"
            if not production
            else "unavailable"
        ),
        "home_payment_mode": zepto_checkout.payment_mode().value,
        "swiggy_catalog_mode": os.getenv("SWIGGY_CATALOG_MODE", "unavailable"),
        "swiggy_payment_mode": swiggy_checkout.payment_mode().value,
        "teams_billing_mode": saas_invoice_checkout.billing_mode().value,
        "teams_checkout_runtime_configured": (
            teams_runtime_ready
        ),
        "teams_checkout_runtime_status": teams_runtime_status,
        "teams_real_money_enabled": (
            saas_invoice_checkout.billing_mode().value == "real"
            and os.getenv("TEAMS_REAL_PAYMENT_ENABLED") == "1"
            and prava_mode == "production_configured"
            and teams_runtime_ready
            and production
            and demo_disabled
        ),
        "real_money_enabled": (
            zepto_checkout.merchant_mode().value == "real"
            and zepto_checkout.payment_mode().value == "real"
            and os.getenv("ZEPTO_REAL_PAYMENT_ENABLED") == "1"
            and prava_mode == "production_configured"
            and zepto_runtime_ready
            and mcp_runtime_ready
            and cart_ready
            and production
            and demo_disabled
            and oauth_status == "verified_recently"
        ),
        "home_checkout_runtime_configured": zepto_runtime_ready,
        "home_checkout_runtime_status": zepto_runtime_status,
        "zepto_mcp_runtime_configured": mcp_runtime_ready,
        "zepto_oauth_status": oauth_status,
        "slack_configured": slack_configured,
        "waitlist_email_configured": all(
            os.getenv(name, "").strip()
            for name in ("RESEND_API_KEY", "RESTOCK_WAITLIST_FROM_EMAIL")
        ),
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
    zepto_runtime_ready, zepto_runtime_status = _merchant_runtime_status()
    if (
        zepto_checkout.payment_mode().value == "real"
        and os.getenv("ZEPTO_REAL_PAYMENT_ENABLED") == "1"
    ):
        if not zepto_runtime_ready:
            issues.append("ZEPTO_REAL_CHECKOUT_RUNTIME_UNAVAILABLE")
        if zepto_runtime_status == "invalid_configuration":
            issues.append("ZEPTO_PAYMENT_EXECUTOR_INVALID")
        if not mcp_remote_runtime_ready():
            issues.append("ZEPTO_MCP_RUNTIME_UNAVAILABLE")
        oauth_status = _zepto_oauth_status()
        if oauth_status == "unknown":
            issues.append("ZEPTO_OAUTH_NOT_CONFIGURED")
        # A configured cache is sufficient for process readiness. Actual money
        # remains disabled until this API process completes a successful MCP
        # call and upgrades the capability to ``verified_recently``. Treating
        # that runtime verification as a startup error would deadlock the first
        # quote behind Railway's readiness gate.
    teams_runtime_ready, teams_runtime_status = _teams_runtime_status()
    if (
        saas_invoice_checkout.billing_mode().value == "real"
        and os.getenv("TEAMS_REAL_PAYMENT_ENABLED") == "1"
    ):
        if not teams_runtime_ready:
            issues.append("TEAMS_REAL_CHECKOUT_RUNTIME_UNAVAILABLE")
        if teams_runtime_status == "invalid_configuration":
            issues.append("TEAMS_PAYMENT_EXECUTOR_INVALID")
    return sorted(set(issues))


def require_user(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    x_restock_user: str = Header(default=DEFAULT_USER_ID),
) -> str:
    token: str | None = None
    if authorization is not None:
        token = _authorization_token(authorization)
        if token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid API token",
            )
    elif session_cookie:
        token = session_cookie
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API token")
    user_id = _resolve_api_token(token, x_restock_user)
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


class ReviewerSandboxApprovalRequest(BaseModel):
    """A safe reviewer decision that may open only the Prava sandbox."""

    model_config = ConfigDict(extra="forbid")

    track: Literal["home", "teams"]
    action: Literal["approve", "renew_as_is", "switch_plan"]


class SoloLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=1, max_length=16_384)


class StarterOnboardingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_ids: list[StarterTemplateId] = Field(min_length=1, max_length=4)


class HomeCatalogItemRequest(BaseModel):
    """Create a Home item only after resolving it against Zepto's live catalog."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=2, max_length=120)
    merchant_sku_id: str = Field(min_length=1, max_length=255)
    merchant_address_ref: str = Field(min_length=1, max_length=255)
    category: Literal["grocery", "stationery", "health", "other"] = "grocery"
    quantity: int = Field(default=1, ge=1, le=20, strict=True)
    typical_cadence_days: float | None = Field(default=None, gt=0, le=730)
    price_threshold: Decimal | None = Field(default=None, gt=Decimal("0"))


class TeamsSubscriptionRequest(BaseModel):
    """A hosted invoice is a payment surface, never a vendor login."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    vendor_name: str = Field(min_length=1, max_length=200)
    invoice_id: str = Field(min_length=1, max_length=255)
    hosted_payment_reference: str = Field(
        min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._:-]+$"
    )
    alternate_hosted_payment_reference: str | None = Field(
        default=None, min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._:-]+$"
    )
    currency: str = Field(min_length=3, max_length=3)
    renewal_date: date
    current_plan_amount: Decimal = Field(gt=Decimal("0"))
    alternate_plan_amount: Decimal | None = Field(default=None, gt=Decimal("0"))
    alternate_plan_label: str | None = Field(default=None, max_length=120)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class WaitlistRequest(BaseModel):
    """Public pilot interest only; this never provisions an app account."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=320)
    client_started_at: datetime
    company: str = Field(default="", max_length=200)
    display_name: str | None = Field(default=None, max_length=200)
    track_interest: Literal["home", "teams", "both", "exploring"] | None = None
    first_use_category: str | None = Field(default=None, max_length=80)
    preferred_channel: Literal["email", "slack", "in_app", "none"] | None = None
    research_opt_in: bool = False
    landing_variant: str | None = Field(default=None, max_length=80)
    entry_demo_track: Literal["home", "teams"] | None = None
    utm_source: str | None = Field(default=None, max_length=100)
    utm_medium: str | None = Field(default=None, max_length=100)
    utm_campaign: str | None = Field(default=None, max_length=100)
    referrer_host: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if (
            not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,253}", normalized)
            or normalized.startswith(".")
            or ".." in normalized
            or normalized.endswith(".")
            or "." not in normalized.rsplit("@", 1)[1]
        ):
            raise ValueError("enter a valid email address")
        return normalized

    @field_validator("referrer_host")
    @classmethod
    def validate_referrer_host(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not re.fullmatch(r"[A-Za-z0-9.-]+(?::\d{1,5})?", value):
            raise ValueError("referrer_host must be a hostname")
        return value.casefold()


def _waitlist_success() -> dict[str, str]:
    # Kept identical for a first join, duplicate, honeypot, or too-fast form.
    return {"status": "joined", "message": "You're on the list."}


def _enforce_waitlist_rate_limit(request: Request) -> None:
    source = request.client.host if request.client else "unknown"
    source_hash = hmac.new(
        _WAITLIST_RATE_SECRET,
        source.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    try:
        limit = max(
            1, int(os.getenv("RESTOCK_WAITLIST_RATE_LIMIT_PER_10_MINUTES", "12"))
        )
    except ValueError:
        limit = 12
    now = datetime.now(timezone.utc)
    window = _WAITLIST_REQUESTS[source_hash]
    cutoff = now - timedelta(minutes=10)
    while window and window[0] < cutoff:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="please try again later",
        )
    window.append(now)


def _waitlist_submission_is_human(
    payload: WaitlistRequest,
    *,
    now: datetime | None = None,
) -> bool:
    if payload.company:
        return False
    try:
        minimum_seconds = max(
            0.0,
            float(os.getenv("RESTOCK_WAITLIST_MIN_SUBMIT_SECONDS", "1.2")),
        )
    except ValueError:
        minimum_seconds = 1.2
    started_at = payload.client_started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    elapsed = ((now or datetime.now(timezone.utc)) - started_at).total_seconds()
    return minimum_seconds <= elapsed <= 86_400


def _default_google_caps() -> tuple[Decimal, Decimal, Decimal]:
    names_and_defaults = (
        ("RESTOCK_DEFAULT_MONTHLY_CAP", "5000"),
        ("RESTOCK_DEFAULT_PER_ITEM_CAP", "1000"),
        ("RESTOCK_DEFAULT_PER_TRANSACTION_CAP", "1000"),
    )
    try:
        values = tuple(
            Decimal(os.getenv(name, default).strip())
            for name, default in names_and_defaults
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication unavailable",
        ) from exc
    if any(not value.is_finite() or value <= 0 for value in values):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication unavailable",
        )
    return values  # type: ignore[return-value]


def _issue_session(
    response: Response,
    user_id: str,
    *,
    max_ttl_seconds: int | None = None,
) -> dict[str, str | int]:
    session_secret = os.getenv("RESTOCK_SESSION_SECRET", "")
    if len(session_secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication unavailable",
        )
    try:
        ttl_seconds = int(os.getenv("RESTOCK_SESSION_TTL_SECONDS", "3600"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication unavailable",
        ) from exc
    ttl_seconds = min(max(ttl_seconds, 300), 86400)
    if max_ttl_seconds is not None:
        if max_ttl_seconds < 60:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid credentials",
            )
        ttl_seconds = min(ttl_seconds, max_ttl_seconds)
    access_token = session_auth.mint(user_id, session_secret, ttl_seconds)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=access_token,
        max_age=ttl_seconds,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ttl_seconds,
    }


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
    return audit_store.get_all(AUDIT_LOG_PATH)


@app.get("/", response_model=None)
def root() -> FileResponse | dict[str, Any]:
    waitlist_index = WAITLIST_DIST / "index.html"
    serve_waitlist_default = (
        "1" if os.getenv("RESTOCK_ENV", "development") == "production" else "0"
    )
    if (
        waitlist_index.exists()
        and os.getenv("RESTOCK_SERVE_WAITLIST", serve_waitlist_default) == "1"
    ):
        return FileResponse(waitlist_index)
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


@app.post("/api/v1/waitlist", status_code=status.HTTP_202_ACCEPTED)
def join_waitlist(
    payload: WaitlistRequest,
    request: Request,
) -> dict[str, str]:
    """Record pilot interest without creating auth or payment state."""

    _enforce_waitlist_rate_limit(request)
    if not _waitlist_submission_is_human(payload):
        return _waitlist_success()
    consented_at = datetime.now(timezone.utc)
    privacy_version = os.getenv(
        "RESTOCK_WAITLIST_PRIVACY_NOTICE_VERSION", "2026-07-30"
    ).strip()
    if not privacy_version or len(privacy_version) > 40:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="waitlist unavailable",
        )
    try:
        get_repository().join_waitlist(
            email_normalized=payload.email,
            display_name=payload.display_name or None,
            track_interest=payload.track_interest,
            first_use_category=payload.first_use_category or None,
            preferred_channel=payload.preferred_channel,
            research_opt_in=payload.research_opt_in,
            privacy_notice_version=privacy_version,
            pilot_email_consent_at=consented_at,
            landing_variant=payload.landing_variant or None,
            entry_demo_track=payload.entry_demo_track,
            utm_source=payload.utm_source or None,
            utm_medium=payload.utm_medium or None,
            utm_campaign=payload.utm_campaign or None,
            referrer_host=payload.referrer_host,
        )
    except (OSError, RuntimeError, SQLAlchemyError, ValueError) as exc:
        LOGGER.error(json.dumps({"event": "waitlist_store_unavailable"}))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="waitlist unavailable",
        ) from exc
    return _waitlist_success()


@app.post("/api/v1/auth/login")
def solo_login(
    payload: SoloLoginRequest,
    request: Request,
    response: Response,
) -> dict[str, str | int]:
    if not _auth_method_enabled("solo"):
        raise HTTPException(status_code=404, detail="sign-in method unavailable")
    password_hash = os.getenv("RESTOCK_SOLO_PASSWORD_HASH", "").strip()
    owner_user_id = os.getenv("RESTOCK_SOLO_USER_ID", "").strip()
    reviewer_hash = os.getenv("RESTOCK_REVIEWER_PASSWORD_HASH", "").strip()
    reviewer_user_id = os.getenv("RESTOCK_REVIEWER_USER_ID", "").strip()
    reviewer_expires_raw = os.getenv("RESTOCK_REVIEWER_EXPIRES_AT", "").strip()
    session_secret = os.getenv("RESTOCK_SESSION_SECRET", "")
    owner_configured = password_auth.is_supported_hash(password_hash) and bool(
        owner_user_id
    )
    reviewer_configured = (
        password_auth.is_supported_hash(reviewer_hash)
        and bool(reviewer_user_id)
        and bool(reviewer_expires_raw)
    )
    if not (owner_configured or reviewer_configured) or len(session_secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication unavailable",
        )
    try:
        if owner_configured:
            UUID(owner_user_id)
        if reviewer_configured:
            UUID(reviewer_user_id)
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
    authenticated_user_id: str | None = None
    reviewer_max_ttl: int | None = None
    if reviewer_configured and password_auth.verify_password(
        payload.password, reviewer_hash
    ):
        try:
            reviewer_expires_at = datetime.fromisoformat(
                reviewer_expires_raw.replace("Z", "+00:00")
            )
            if reviewer_expires_at.tzinfo is None:
                raise ValueError("timezone required")
            reviewer_max_ttl = int(
                (reviewer_expires_at - datetime.now(timezone.utc)).total_seconds()
            )
        except ValueError:
            reviewer_max_ttl = 0
        if reviewer_max_ttl >= 60:
            authenticated_user_id = reviewer_user_id
    elif owner_configured and password_auth.verify_password(payload.password, password_hash):
        authenticated_user_id = owner_user_id
    if authenticated_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )
    try:
        owner = repository.get_user(authenticated_user_id)
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
    return _issue_session(
        response,
        authenticated_user_id,
        max_ttl_seconds=reviewer_max_ttl,
    )


@app.post("/api/v1/auth/google")
def google_login(
    payload: GoogleLoginRequest,
    request: Request,
    response: Response,
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, str | int]:
    if not _auth_method_enabled("google"):
        raise HTTPException(status_code=404, detail="sign-in method unavailable")
    session_secret = os.getenv("RESTOCK_SESSION_SECRET", "")
    if len(session_secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication unavailable",
        )
    _enforce_login_rate_limit(request, repository, session_secret)
    try:
        claims = verify_google_identity(payload.credential)
    except GoogleIdentityConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication unavailable",
        ) from exc
    except GoogleIdentityError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid Google credential",
        ) from exc
    monthly_cap, per_item_cap, per_transaction_cap = _default_google_caps()
    try:
        user, _created = repository.provision_auth_identity(
            provider="google",
            subject=claims.subject,
            email=claims.email,
            display_name=claims.display_name,
            monthly_cap=monthly_cap,
            per_item_cap=per_item_cap,
            per_transaction_cap=per_transaction_cap,
        )
    except Exception as exc:
        LOGGER.error(json.dumps({"event": "google_auth_provisioning_failed"}))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication unavailable",
        ) from exc
    return _issue_session(response, str(user["user_id"]))


@app.post("/api/v1/auth/google/link")
def google_link(
    payload: GoogleLoginRequest,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, str]:
    if not _auth_method_enabled("google"):
        raise HTTPException(status_code=404, detail="sign-in method unavailable")
    try:
        claims = verify_google_identity(payload.credential)
    except GoogleIdentityConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication unavailable",
        ) from exc
    except GoogleIdentityError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid Google credential",
        ) from exc
    try:
        repository.link_auth_identity(
            user_id=user_id,
            provider="google",
            subject=claims.subject,
            email=claims.email,
            display_name=claims.display_name,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="user not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "linked", "provider": "google"}


@app.post("/api/v1/auth/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return {"status": "signed_out"}


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
    if os.getenv("RESTOCK_ENV", "development") == "production":
        # This compatibility table predates tenant-scoped workflow storage.
        # Production callers must use the user-scoped /api/v1/audit endpoint.
        raise HTTPException(status_code=404, detail="not found")
    return _read_audit_log()


@app.get("/notifications/pending")
def legacy_pending_notifications(_: str = Depends(require_user)) -> list[dict[str, Any]]:
    if os.getenv("RESTOCK_ENV", "development") == "production":
        # This compatibility table has no user/tenant ownership column.
        # Production callers must use /api/v1/notifications/pending.
        raise HTTPException(status_code=404, detail="not found")
    return notification_store.get_pending()


@app.get("/api/v1/me")
def me(
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    value = repository.get_user(user_id)
    if value is None:
        raise HTTPException(status_code=404, detail="user not found")
    value["auth_providers"] = repository.list_auth_providers(user_id)
    # The expiring reviewer account intentionally receives the curated
    # presentation fixtures used in the Prava walkthrough.  This flag is
    # identity-bound on the server rather than inferred from a display name,
    # so a normal user can never accidentally see another user's showcase.
    value["reviewer_fixture"] = secrets.compare_digest(
        user_id,
        os.getenv("RESTOCK_REVIEWER_USER_ID", "").strip(),
    )
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


@app.get("/api/v1/onboarding/starter-items")
def starter_items(
    _: str = Depends(require_user),
) -> dict[str, Any]:
    return {"items": STARTER_TEMPLATE_SUMMARIES}


def _require_real_zepto_catalog() -> None:
    if zepto_checkout.merchant_mode().value != "real":
        raise HTTPException(
            status_code=503,
            detail="live Zepto catalog is not enabled",
        )


def _zepto_state_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _zepto_callback_redirect(outcome: str) -> RedirectResponse:
    """Return only to the configured public app, never a caller-supplied URL."""

    base = os.getenv("RESTOCK_PUBLIC_APP_URL", "").strip().rstrip("/")
    if not base:
        base = "/app"
    separator = "&" if "?" in base else "?"
    return RedirectResponse(f"{base}{separator}zepto={outcome}", status_code=303)


def _user_zepto_client(
    *, user_id: str, repository: RestockRepository
) -> ZeptoMCPClient:
    """Resolve one user's encrypted OAuth connection into a short-lived client."""

    if not zepto_oauth_is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Zepto connection is not configured yet",
        )
    connection = repository.get_merchant_connection(user_id=user_id, provider="zepto")
    if connection is None or connection["status"] != "connected":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="connect your Zepto account before using the live catalog",
        )
    try:
        token = ZeptoOAuthToken.from_encrypted_payload(
            decrypt_secret(str(connection["encrypted_tokens"] or ""))
        )
        if token.is_expiring():
            token = refresh_access_token(token)
            repository.refresh_merchant_connection_tokens(
                user_id=user_id,
                provider="zepto",
                encrypted_tokens=encrypt_secret(token.to_encrypted_payload()),
                token_expires_at=token.expires_at,
            )
    except (SecretDecryptionError, ZeptoOAuthError, SecretEncryptionConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="your Zepto connection needs to be reconnected",
        ) from exc
    return ZeptoMCPClient(access_token=token.access_token)


def _raise_zepto_http(exc: Exception) -> None:
    if isinstance(exc, ZeptoRateLimitError):
        raise HTTPException(
            status_code=429,
            detail="Zepto is rate-limiting catalog requests; try again shortly",
            headers={"Retry-After": str(max(1, int(exc.retry_after_seconds or 30)))},
        ) from exc
    if isinstance(exc, ZeptoTransientError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Zepto is temporarily unavailable; try again shortly",
            headers={"Retry-After": str(max(1, int(exc.retry_after_seconds or 10)))},
        ) from exc
    raise HTTPException(
        status_code=503,
        detail="Zepto connection is unavailable; reconnect the provider and retry",
    ) from exc


@app.get("/api/v1/integrations/zepto/connection")
def zepto_connection_status(
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Return only the signed-in user's non-sensitive Zepto connection state."""

    return {
        **repository.merchant_connection_summary(user_id=user_id, provider="zepto"),
        "oauth_configured": zepto_oauth_is_configured(),
        "history_import": "suggestions_only",
    }


@app.post("/api/v1/integrations/zepto/connect")
def zepto_begin_connection(
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, str]:
    """Start one user's PKCE OAuth consent flow; no tokens reach the browser."""

    _require_real_zepto_catalog()
    try:
        state, verifier, authorization_url, expires_at = begin_zepto_authorization()
        repository.begin_merchant_connection(
            user_id=user_id,
            provider="zepto",
            state_hash=_zepto_state_hash(state),
            encrypted_code_verifier=encrypt_secret(verifier),
            expires_at=expires_at,
        )
    except (ZeptoOAuthConfigurationError, SecretEncryptionConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Zepto connection is not configured yet",
        ) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid user") from exc
    return {"authorization_url": authorization_url}


@app.get("/api/v1/integrations/zepto/callback", include_in_schema=False)
def zepto_connection_callback(
    state: str = Query(min_length=16, max_length=512),
    code: str | None = Query(default=None, min_length=1, max_length=4096),
    error: str | None = Query(default=None, max_length=128),
    repository: RestockRepository = Depends(get_repository),
) -> RedirectResponse:
    """Finish a PKCE flow without exposing the user session or token material."""

    state_hash = _zepto_state_hash(state)
    pending = repository.get_pending_merchant_connection_by_state(
        state_hash=state_hash, provider="zepto"
    )
    if pending is None:
        return _zepto_callback_redirect("expired")
    if error or not code:
        repository.fail_merchant_connection(
            state_hash=state_hash,
            provider="zepto",
            error_code="authorization_denied" if error else "authorization_incomplete",
        )
        return _zepto_callback_redirect("cancelled")
    try:
        verifier = decrypt_secret(str(pending["encrypted_code_verifier"] or ""))
        token = exchange_authorization_code(code=code, verifier=verifier)
        user_id = repository.complete_merchant_connection(
            state_hash=state_hash,
            provider="zepto",
            encrypted_tokens=encrypt_secret(token.to_encrypted_payload()),
            token_expires_at=token.expires_at,
        )
    except (ZeptoOAuthError, SecretDecryptionError, SecretEncryptionConfigurationError):
        repository.fail_merchant_connection(
            state_hash=state_hash,
            provider="zepto",
            error_code="token_exchange_failed",
        )
        return _zepto_callback_redirect("failed")
    if user_id is None:
        return _zepto_callback_redirect("expired")
    return _zepto_callback_redirect("connected")


@app.delete("/api/v1/integrations/zepto/connection")
def zepto_disconnect(
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, bool]:
    """Revoke Restock's local access record; Zepto account data stays at Zepto."""

    return {"disconnected": repository.revoke_merchant_connection(user_id=user_id, provider="zepto")}


@app.get("/api/v1/integrations/zepto/addresses")
def zepto_saved_addresses(
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Return labels and opaque IDs only; street addresses stay at Zepto."""

    _require_real_zepto_catalog()
    try:
        addresses = zepto_checkout.list_saved_address_summaries(
            client=_user_zepto_client(user_id=user_id, repository=repository)
        )
        repository.mark_merchant_connection_verified(user_id=user_id, provider="zepto")
    except (ZeptoMCPError, RuntimeError, OSError) as exc:
        _raise_zepto_http(exc)
    return {"addresses": [address.model_dump(mode="json") for address in addresses]}


@app.get("/api/v1/integrations/zepto/products")
def zepto_products(
    query: str = Query(min_length=2, max_length=120),
    address_ref: str = Query(min_length=1, max_length=255),
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Search the current Zepto catalog for one authenticated saved address."""

    _require_real_zepto_catalog()
    try:
        products = zepto_checkout.search_catalog(
            query,
            address_ref=address_ref,
            client=_user_zepto_client(user_id=user_id, repository=repository),
        )
        repository.mark_merchant_connection_verified(user_id=user_id, provider="zepto")
    except (ZeptoMCPError, RuntimeError, OSError) as exc:
        _raise_zepto_http(exc)
    return {"products": [product.model_dump(mode="json") for product in products]}


def _history_suggestions(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Reduce provider history to opt-in product suggestions without order PII."""

    values: Any = payload.get("items") or payload.get("pastOrderItems") or payload.get("products")
    if values is None and isinstance(payload.get("data"), dict):
        nested = payload["data"]
        values = nested.get("items") or nested.get("pastOrderItems") or nested.get("products")
    if not isinstance(values, list):
        return []
    suggestions: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, dict):
            continue
        name = value.get("name") or value.get("productName") or value.get("title")
        sku = value.get("productVariantId") or value.get("variantId") or value.get("id")
        if not isinstance(name, str) or not name.strip() or not sku:
            continue
        key = str(sku)
        if key in seen:
            continue
        seen.add(key)
        suggestions.append(
            {
                "merchant_sku_id": key[:255],
                "name": name.strip()[:200],
                "search_query": name.strip()[:120],
            }
        )
        if len(suggestions) >= 20:
            break
    return suggestions


@app.get("/api/v1/integrations/zepto/history/suggestions")
def zepto_history_suggestions(
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Return consented suggestions only; history never silently creates items."""

    _require_real_zepto_catalog()
    try:
        payload = _user_zepto_client(user_id=user_id, repository=repository).get_past_order_items()
        repository.mark_merchant_connection_verified(user_id=user_id, provider="zepto")
    except (ZeptoMCPError, RuntimeError, OSError) as exc:
        _raise_zepto_http(exc)
    return {"suggestions": _history_suggestions(payload)}


@app.post("/api/v1/items/home", status_code=201)
def create_home_catalog_item(
    body: HomeCatalogItemRequest,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Persist only a fresh exact-SKU result selected from Zepto."""

    from payments.models import TrackedItem

    _require_real_zepto_catalog()
    try:
        products = zepto_checkout.search_catalog(
            body.query,
            address_ref=body.merchant_address_ref,
            client=_user_zepto_client(user_id=user_id, repository=repository),
        )
        repository.mark_merchant_connection_verified(user_id=user_id, provider="zepto")
    except (ZeptoMCPError, RuntimeError, OSError) as exc:
        _raise_zepto_http(exc)
    selected = next(
        (
            product
            for product in products
            if product.merchant_sku_id == body.merchant_sku_id
        ),
        None,
    )
    if selected is None:
        raise HTTPException(
            status_code=409,
            detail="selected Zepto SKU is no longer present; search again",
        )
    if selected.stock_status.value != "in_stock":
        raise HTTPException(status_code=409, detail="selected Zepto SKU is out of stock")
    item = TrackedItem(
        item_id=uuid4(),
        user_id=UUID(user_id),
        name=selected.name,
        track="home",
        trigger_type="predicted",
        category=body.category,
        sensitive_flag=False,
        preferred_merchant="zepto",
        merchant_sku_id=selected.merchant_sku_id,
        merchant_address_ref=body.merchant_address_ref,
        quantity=body.quantity,
        currency=selected.currency,
        status="active",
        typical_cadence_days=body.typical_cadence_days,
        last_observed_price=selected.amount,
        price_threshold=body.price_threshold,
    )
    repository.upsert_item(item)
    return item.model_dump(mode="json")


@app.post("/api/v1/onboarding/starter-items")
def create_starter_items(
    body: StarterOnboardingRequest,
    response: Response,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    if os.getenv("RESTOCK_ENV", "development") == "production":
        raise HTTPException(
            status_code=409,
            detail="starter estimates are disabled in production; choose a live Zepto product",
        )
    selected = list(dict.fromkeys(body.template_ids))
    existing_skus = {
        str(item.get("merchant_sku_id", ""))
        for item in repository.list_items(user_id)
    }
    created = 0
    for template_id in selected:
        if starter_template_sku(template_id) in existing_skus:
            continue
        repository.upsert_item(build_starter_item(template_id, user_id=user_id))
        created += 1
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return {
        "user_id": user_id,
        "created": created,
        "existing": len(selected) - created,
        "items": repository.list_items(user_id),
    }


@app.post("/api/v1/items/teams", status_code=201)
def create_teams_subscription(
    body: TeamsSubscriptionRequest,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Track one hosted invoice without accepting dashboard credentials."""

    from payments.models import TrackedItem

    alternate_amount = body.alternate_plan_amount or body.current_plan_amount
    alternate_label = body.alternate_plan_label or "renew current plan"
    try:
        item = TrackedItem(
            item_id=uuid4(),
            user_id=UUID(user_id),
            name=body.vendor_name,
            track="teams",
            trigger_type="known_date",
            category="saas_subscription",
            sensitive_flag=False,
            preferred_merchant="hosted_invoice",
            merchant_sku_id=body.invoice_id,
            currency=body.currency,
            status="active",
            renewal_date=body.renewal_date,
            current_plan_amount=body.current_plan_amount,
            alternate_plan_amount=alternate_amount,
            alternate_plan_label=alternate_label,
            renewal_method="hosted_link",
            hosted_payment_reference=body.hosted_payment_reference,
            alternate_hosted_payment_reference=body.alternate_hosted_payment_reference,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    repository.upsert_item(item)
    return item.model_dump(mode="json")


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


@app.post("/api/v1/reviewer/sandbox-approval")
def reviewer_sandbox_approval(
    body: ReviewerSandboxApprovalRequest,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, str]:
    """Create one authenticated, non-charging Prava sandbox handoff.

    The catalog quote is an explicitly disclosed fixture. The endpoint is
    unavailable for production Prava credentials and never enables a merchant
    payment boundary.
    """

    from merchant.models import ExecutionMode, MerchantQuote, StockStatus
    from payments import prava_client
    from payments.models import (
        Category,
        ItemStatus,
        PreferredMerchant,
        RenewalMethod,
        Track,
        TrackedItem,
        TriggerType,
        User,
    )

    if prava_client.configured_mode() != "sandbox" or runtime_modes()["real_money_enabled"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prava sandbox approval is unavailable",
        )
    user_data = repository.get_user(user_id)
    if user_data is None:
        raise HTTPException(status_code=404, detail="user not found")
    user = User.model_validate(user_data)
    if body.track == "home":
        if body.action != "approve":
            raise HTTPException(status_code=422, detail="Home sandbox review supports approve only")
        sku = starter_template_sku("coffee")
        item = next(
            (
                TrackedItem.model_validate(candidate)
                for candidate in repository.list_items(user_id)
                if candidate["merchant_sku_id"] == sku
            ),
            None,
        ) or build_starter_item("coffee", user_id=user_id)
    else:
        if body.action not in {"renew_as_is", "switch_plan"}:
            raise HTTPException(
                status_code=422,
                detail="Teams sandbox review requires an explicit renew or switch decision",
            )
        sku = f"reviewer-github-copilot-{body.action}"
        item = next(
            (
                TrackedItem.model_validate(candidate)
                for candidate in repository.list_items(user_id)
                if candidate["merchant_sku_id"] == sku
            ),
            None,
        )
        if item is None:
            switching = body.action == "switch_plan"
            item = TrackedItem(
                item_id=uuid5(NAMESPACE_URL, f"restock:{user_id}:{sku}"),
                user_id=UUID(user_id),
                name="GitHub Copilot Business",
                track=Track.TEAMS,
                trigger_type=TriggerType.KNOWN_DATE,
                category=Category.SAAS_SUBSCRIPTION,
                sensitive_flag=False,
                preferred_merchant=PreferredMerchant.HOSTED_INVOICE,
                merchant_sku_id=sku,
                currency="USD",
                status=ItemStatus.ACTIVE,
                renewal_date=date.today() + timedelta(days=2),
                current_plan_amount=Decimal("39.00"),
                alternate_plan_amount=Decimal("32.00" if switching else "45.00"),
                alternate_plan_label="Copilot Team alternative",
                renewal_method=RenewalMethod.HOSTED_LINK,
                hosted_payment_reference=f"reviewer-{body.action}-invoice",
                alternate_hosted_payment_reference=(
                    "reviewer-switch-alternate" if switching else None
                ),
            )
    existing_item_ids = {
        candidate["item_id"] for candidate in repository.list_items(user_id)
    }
    if str(item.item_id) not in existing_item_ids:
        repository.upsert_item(item)

    service = WorkflowService(repository)
    active = repository.latest_workflow_for_item(str(item.item_id))
    if active is not None and active.get("active_item_key"):
        repository.transition(
            active["run_id"],
            expected={active["state"]},
            state="expired",
            error_code="SANDBOX_RECREATED",
        )
        active = None

    if body.track == "home":
        amount = item.last_observed_price or item.last_purchase_amount or Decimal("380.00")
    elif body.action == "switch_plan":
        amount = item.alternate_plan_amount or Decimal("32.00")
    else:
        amount = item.current_plan_amount or Decimal("39.00")
    quote = MerchantQuote(
        merchant=item.preferred_merchant.value,
        merchant_sku_id=item.merchant_sku_id,
        product_name=item.name,
        amount=amount,
        currency=item.currency,
        stock_status=StockStatus.IN_STOCK,
        quote_reference=f"sandbox-review:{uuid4().hex}",
        observed_at=datetime.now(timezone.utc),
        execution_mode=ExecutionMode.DISCLOSED_MOCK,
    )
    try:
        run = service.begin(user, item, quote=quote)
        run = service.act(run["run_id"], user_id=user_id, action=body.action)
        approval_url_value = service.approval_url(run["run_id"])
    except (OSError, RuntimeError, ValueError) as exc:
        LOGGER.error(json.dumps({"event": "sandbox_approval_handoff_failed"}))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Prava sandbox session could not be created",
        ) from exc
    return {
        "run_id": str(run["run_id"]),
        "state": str(run["state"]),
        "approval_url": approval_url_value,
        "sandbox_otp": "456789",
        "track": body.track,
        "action": body.action,
    }


@app.get("/api/v1/workflows/{run_id}/payment-status")
def workflow_payment_status(
    run_id: str,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Return only the provider state needed to resume; never payment secrets."""

    from payments import prava_client

    try:
        run = repository.get_workflow(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="workflow not found") from exc
    if run["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="workflow belongs to a different user")
    if run["state"] != "passkey_pending":
        return {
            "run_id": run_id,
            "workflow_state": str(run["state"]),
            "provider_status": "not_applicable",
            "resumable": False,
        }
    intent_ref = run.get("prava_intent_ref")
    if not intent_ref:
        raise HTTPException(status_code=409, detail="workflow has no Prava session")
    try:
        provider_result = prava_client.get_payment_result(str(intent_ref))
    except Exception as exc:
        LOGGER.warning(json.dumps({"event": "prava_payment_status_unavailable", "run_id": run_id}))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Prava payment status is temporarily unavailable",
        ) from exc
    provider_status = str(provider_result.get("status", "")).lower()
    return {
        "run_id": run_id,
        "workflow_state": str(run["state"]),
        "provider_status": provider_status,
        "resumable": provider_status in {"awaiting_result", "failed"},
    }


@app.post("/api/v1/workflows/{run_id}/actions")
def workflow_action(
    run_id: str,
    body: WorkflowActionRequest,
    user_id: str = Depends(require_user),
    repository: RestockRepository = Depends(get_repository),
) -> dict[str, Any]:
    try:
        return build_workflow_service(repository).act(
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
        return {"approval_url": build_workflow_service(repository).approval_url(run_id)}
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
        return build_workflow_service(repository).resume_after_passkey(run_id)
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
        return build_workflow_service(repository).reconcile_checkout(run_id)
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
        build_workflow_service(repository).act(
            action["run_id"],
            user_id=run["user_id"],
            action=action["action"],
        )
        processed.append({"run_id": action["run_id"], "status": "accepted"})
    return {"processed": processed}


WEB_DIST = ROOT / "ui" / "web" / "dist"
WAITLIST_ASSETS = WAITLIST_DIST / "assets"
WAITLIST_MEDIA = WAITLIST_DIST / "media"
if WAITLIST_ASSETS.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=WAITLIST_ASSETS),
        name="waitlist-assets",
    )
if WAITLIST_MEDIA.exists():
    app.mount(
        "/media",
        StaticFiles(directory=WAITLIST_MEDIA),
        name="waitlist-media",
    )
if WEB_DIST.exists():
    app.mount("/app", StaticFiles(directory=WEB_DIST, html=True), name="web")
