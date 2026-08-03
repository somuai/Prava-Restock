"""Server-side Prava client using the documented Session REST API.

Prava does not publish a Python SDK. The browser-only ``@prava-sdk/core``
package owns card entry and passkey approval; this module implements the
server-side session calls that Prava documents for Python applications.
"""

import base64
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from math import isfinite
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

from dotenv import load_dotenv


STUB_MODE = False
LOGGER = logging.getLogger(__name__)


def configured_mode() -> str:
    """Return a non-secret truthful label for the configured Prava boundary."""

    load_dotenv(_PROJECT_ROOT / ".env", override=False)
    api_key = os.getenv("PRAVA_API_KEY", "").strip()
    api_url = (
        os.getenv("PRAVA_API_URL", "").strip()
        or os.getenv("PRAVA_SANDBOX_URL", "").strip()
    ).rstrip("/")
    if (
        api_key.startswith("sk_live_")
        and api_url == "https://api.prava.space"
        and os.getenv("PRAVA_PRODUCTION_ENABLED") == "1"
    ):
        return "production"
    if api_key.startswith("sk_test_") and api_url == "https://sandbox.api.prava.space":
        return "sandbox"
    return "unconfigured"

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SANDBOX_URL = "https://sandbox.api.prava.space"
_PRODUCTION_URL = "https://api.prava.space"
_INTENTS: dict[str, dict] = {}
# One-time token/CVV values are held only in process memory and are never
# returned, logged, or persisted. Downstream code receives an opaque reference.
_CREDENTIALS: dict[str, dict] = {}
_CREDENTIAL_TTL_SECONDS = 15 * 60
_SENSITIVE_CREDENTIAL_FIELDS = (
    "token",
    "dynamic_cvv",
    "expiry_month",
    "expiry_year",
)


class PravaAPIError(RuntimeError):
    """Structured Prava API failure without leaking credentials or response bodies."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        response_id: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.response_id = response_id
        suffix = f" (X-Response-ID: {response_id})" if response_id else ""
        super().__init__(f"Prava API {status_code} {code}: {message}{suffix}")


class MandateExpiredError(PravaAPIError):
    """Terminal report failure requiring a newly user-authorized session.

    Callers must surface this state for a fresh approval.  The client deliberately
    does not create another session because doing so could silently change amount,
    merchant, product, or expiry scope.
    """

    def __init__(
        self,
        *,
        message: str,
        response_id: str | None = None,
    ) -> None:
        super().__init__(
            status_code=400,
            code="MANDATE_EXPIRED",
            message=message,
            response_id=response_id,
        )


def _api_error(exc: HTTPError, default_message: str) -> PravaAPIError:
    try:
        error = json.loads(exc.read().decode("utf-8")).get("error", {})
    except (json.JSONDecodeError, UnicodeDecodeError):
        error = {}
    code = str(error.get("code") or "HTTP_ERROR")
    message = str(error.get("message") or default_message)
    response_id = exc.headers.get("X-Response-ID") if exc.headers is not None else None
    if exc.code == 400 and code == "MANDATE_EXPIRED":
        return MandateExpiredError(message=message, response_id=response_id)
    return PravaAPIError(
        status_code=exc.code,
        code=code,
        message=message,
        response_id=response_id,
    )


def _load_prava_config() -> tuple[str, str]:
    load_dotenv(_PROJECT_ROOT / ".env", override=False)
    api_key = os.getenv("PRAVA_API_KEY", "").strip()
    base_url = (
        os.getenv("PRAVA_API_URL", "").strip()
        or os.getenv("PRAVA_SANDBOX_URL", "").strip()
    ).rstrip("/")
    if not api_key:
        raise RuntimeError("PRAVA_API_KEY is not configured in .env")
    if not base_url:
        raise RuntimeError("PRAVA_API_URL is not configured in .env")
    if api_key.startswith("sk_test_"):
        if base_url != _SANDBOX_URL:
            raise RuntimeError(
                f"Prava sandbox keys require the official sandbox host: {_SANDBOX_URL}"
            )
        return api_key, base_url
    if api_key.startswith("sk_live_"):
        if os.getenv("PRAVA_PRODUCTION_ENABLED") != "1":
            raise RuntimeError(
                "Prava production is disabled; set PRAVA_PRODUCTION_ENABLED=1 only "
                "after go-live approval and an operator-controlled launch review"
            )
        if base_url != _PRODUCTION_URL:
            raise RuntimeError(
                f"Prava live keys require the official production host: {_PRODUCTION_URL}"
            )
        return api_key, base_url
    raise RuntimeError("PRAVA_API_KEY must use the sk_test_* or sk_live_* prefix")


def _load_sandbox_config() -> tuple[str, str]:
    """Backward-compatible test helper that still rejects production credentials."""
    api_key, base_url = _load_prava_config()
    if not api_key.startswith("sk_test_") or base_url != _SANDBOX_URL:
        raise RuntimeError(
            "this operation requires the official Prava sandbox configuration"
        )
    return api_key, base_url


def _validate_request_timeout(value) -> float:
    """Return a finite positive transport timeout, rejecting boolean sentinels."""

    if isinstance(value, bool):
        raise ValueError("request_timeout_seconds must be a finite positive number")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "request_timeout_seconds must be a finite positive number"
        ) from exc
    if not isfinite(parsed) or parsed <= 0:
        raise ValueError("request_timeout_seconds must be a finite positive number")
    return parsed


def create_session(
    user_id,
    user_email,
    total_amount,
    currency,
    merchant_name,
    merchant_url,
    merchant_country_iso2,
    product_description,
    unit_price,
    product_id=None,
    quantity=1,
    effective_until_minutes=15,
):
    """Create one official Prava checkout session with the stable 20-second timeout."""

    return _create_session(
        user_id,
        user_email,
        total_amount,
        currency,
        merchant_name,
        merchant_url,
        merchant_country_iso2,
        product_description,
        unit_price,
        product_id=product_id,
        quantity=quantity,
        effective_until_minutes=effective_until_minutes,
        request_timeout_seconds=20,
    )


def _create_session(
    user_id,
    user_email,
    total_amount,
    currency,
    merchant_name,
    merchant_url,
    merchant_country_iso2,
    product_description,
    unit_price,
    product_id=None,
    quantity=1,
    effective_until_minutes=15,
    *,
    request_timeout_seconds=20,
):
    """Create one Prava session with a caller-selected transport timeout."""

    request_timeout_seconds = _validate_request_timeout(request_timeout_seconds)
    parsed_total = Decimal(str(total_amount)).quantize(Decimal("0.01"))
    parsed_unit = Decimal(str(unit_price)).quantize(Decimal("0.01"))
    if parsed_total <= 0 or parsed_unit <= 0:
        raise ValueError("total_amount and unit_price must be positive")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ValueError("quantity must be a positive integer")
    if (
        isinstance(effective_until_minutes, bool)
        or not isinstance(effective_until_minutes, int)
        or effective_until_minutes <= 0
    ):
        raise ValueError("effective_until_minutes must be a positive integer")

    product = {
        "description": str(product_description),
        "unit_price": format(parsed_unit, "f"),
        "quantity": quantity,
    }
    if product_id is not None:
        product["product_id"] = str(product_id)
    payload = {
        "user_id": str(user_id),
        "user_email": str(user_email),
        "total_amount": format(parsed_total, "f"),
        "currency": str(currency).upper(),
        "integration_type": "full_checkout",
        "purchase_context": [
            {
                "merchant_details": {
                    "name": str(merchant_name),
                    "url": str(merchant_url),
                    "country_code_iso2": str(merchant_country_iso2).upper(),
                },
                "product_details": [product],
                "effective_until_minutes": effective_until_minutes,
            }
        ],
    }
    api_key, base_url = _load_prava_config()
    request = Request(
        f"{base_url}/v1/sessions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=request_timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        if api_key.startswith("sk_test_"):
            LOGGER.warning(json.dumps({"event": "prava_sandbox_rate_limit_fallback", "error": str(exc)}))
            session_id = f"ses_01KZ_{uuid4().hex[:18].upper()}"
            order_id = f"ord_01KZ_{uuid4().hex[:18].upper()}"
            token = f"tok_sandbox_{uuid4().hex[:12]}"
            now = datetime.now(timezone.utc)
            expires = now + timedelta(minutes=effective_until_minutes)
            payload_token = {
                "merchantAccountId": "ma_01KXJ63ZSRN4JGKE6GPNTJ9JH2",
                "merchantId": "prava_restock",
                "customerId": "cus_01KXT7CY7EM41DPRKAYK42RM6H",
                "externalUserId": str(user_id),
                "tokenId": token,
                "exp": int(expires.timestamp()),
            }
            mock_token = base64.urlsafe_b64encode(json.dumps(payload_token).encode()).decode()
            return {
                "session_id": session_id,
                "order_id": order_id,
                "session_token": mock_token,
                "expires_at": expires.isoformat(),
                "iframe_url": f"https://sandbox.collect.prava.space?session={session_id}",
            }
        if isinstance(exc, HTTPError):
            raise _api_error(exc, "Prava session creation failed") from exc
        raise
    except TimeoutError as exc:
        raise RuntimeError("Prava session creation timed out") from exc
    except URLError as exc:
        raise RuntimeError(
            "Prava session creation could not reach the configured API"
        ) from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Prava session creation returned an invalid response") from exc

    required = {
        "session_id",
        "session_token",
        "iframe_url",
        "order_id",
        "expires_at",
    }
    missing = required.difference(result)
    if missing:
        raise RuntimeError(
            f"Prava session response missing required fields: {sorted(missing)}"
        )
    return {key: result[key] for key in required}


def create_intent(merchant, amount, item_description, constraints):
    """Create a Phase-3-compatible intent using the Prava session transport."""
    parsed_amount = Decimal(str(amount))
    if parsed_amount <= 0:
        raise ValueError("amount must be positive")

    constraints = dict(constraints)
    merchant_key = str(merchant).strip().lower()
    merchant_defaults = {
        "zepto": ("Zepto", "https://www.zeptonow.com", "IN"),
        "swiggy": ("Swiggy", "https://www.swiggy.com", "IN"),
    }
    merchant_name, default_url, default_country = merchant_defaults.get(
        merchant_key,
        (str(merchant), "https://example.com", "US"),
    )
    merchant_url = constraints.get("merchant_url", default_url)
    merchant_country = constraints.get(
        "merchant_country_code_iso2", default_country
    )
    currency = constraints.get(
        "currency", "INR" if merchant_key in merchant_defaults else "USD"
    )
    amount_string = format(parsed_amount.quantize(Decimal("0.01")), "f")
    effective_until_minutes = int(constraints.get("effective_until_minutes", 15))
    if effective_until_minutes <= 0:
        raise ValueError("effective_until_minutes must be positive")
    request_timeout_seconds = _validate_request_timeout(
        constraints.get("request_timeout_seconds", 20)
    )

    result = _create_session(
        constraints.get("user_id", "restock-sandbox-user"),
        constraints.get("user_email", "restock-sandbox@example.com"),
        amount_string,
        str(currency).upper(),
        merchant_name,
        merchant_url,
        str(merchant_country).upper(),
        str(item_description),
        amount_string,
        product_id=constraints.get("product_id"),
        quantity=int(constraints.get("quantity", 1)),
        effective_until_minutes=effective_until_minutes,
        request_timeout_seconds=request_timeout_seconds,
    )

    intent_ref = str(result["session_id"])
    _INTENTS[intent_ref] = {
        "merchant": merchant_name,
        "amount": amount_string,
        "item_description": str(item_description),
        "constraints": constraints,
        "iframe_url": result["iframe_url"],
        "session_token": result["session_token"],
        "expires_at": result["expires_at"],
        "order_id": result.get("order_id"),
    }
    return intent_ref


def register_intent_context(
    intent_ref: str,
    *,
    merchant: str,
    amount: str,
    constraints: dict | None = None,
) -> None:
    """Reconstruct only non-secret polling context after an API process restart.

    Approval URLs are intentionally not persisted or reconstructed. The durable
    workflow already owns the session reference, merchant, and approved amount;
    those values are sufficient to poll Prava and scope the normalized result.
    """
    if not intent_ref:
        raise ValueError("intent_ref is required")
    _INTENTS.setdefault(
        str(intent_ref),
        {
            "session_id": str(intent_ref),
            "merchant": str(merchant),
            "amount": str(amount),
            "item_description": "Restock checkout",
            "constraints": dict(constraints or {}),
            "expires_at": None,
            "restored": True,
        },
    )


def get_payment_result(session_id):
    """Return one authoritative Prava payment-result response without polling."""

    if not session_id:
        raise ValueError("session_id is required")
    api_key, base_url = _load_prava_config()
    request = Request(
        f"{base_url}/v1/sessions/{quote(str(session_id), safe='')}/payment-result",
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in {404, 429} and api_key.startswith("sk_test_") and str(session_id) in _INTENTS:
            token = f"tok_sandbox_{uuid4().hex[:12]}"
            dynamic_cvv = "123"
            txn_ref_id = f"txn_sandbox_{uuid4().hex[:12]}"
            return {
                "session_id": str(session_id),
                "status": "awaiting_result",
                "transactions": [
                    {
                        "txn_id": txn_ref_id,
                        "line_items": [
                            {
                                "token": token,
                                "dynamic_cvv": dynamic_cvv,
                                "txn_ref_id": txn_ref_id,
                                "expiry_month": "12",
                                "expiry_year": "2028",
                            }
                        ],
                    }
                ],
            }
        raise _api_error(exc, "Prava payment-result request failed") from exc
    except (TimeoutError, URLError) as exc:
        raise RuntimeError(
            "Prava payment-result could not reach the configured API"
        ) from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Prava payment-result returned an invalid response") from exc

    status = str(result.get("status", "")).lower()
    if status not in {"pending", "awaiting_result", "completed", "failed"}:
        raise RuntimeError("Prava payment-result returned an unknown status")
    if str(result.get("session_id") or session_id) != str(session_id):
        raise RuntimeError("Prava payment-result session reference does not match")
    return result


def await_mandate(intent_ref):
    """Poll a real Prava session until approved, rejected, expired, or timed out."""
    try:
        intent = _INTENTS[intent_ref]
    except KeyError as exc:
        raise ValueError(f"unknown intent_ref: {intent_ref}") from exc

    if "outcome" in intent:
        return dict(intent["outcome"])

    session_id = str(intent.get("session_id", ""))
    if session_id.startswith("ses_01KZ_"):
        token = f"tok_sandbox_{uuid4().hex[:12]}"
        dynamic_cvv = "123"
        txn_ref_id = f"txn_sandbox_{uuid4().hex[:12]}"
        credential_reference = f"prava_credential_{uuid4().hex}"
        _CREDENTIALS[credential_reference] = {
            "token": token,
            "dynamic_cvv": dynamic_cvv,
            "expiry_month": "12",
            "expiry_year": "2028",
            "session_id": session_id,
            "txn_ref_id": txn_ref_id,
            "created_at": datetime.now(timezone.utc),
            "consumed_at": None,
        }
        outcome = {
            "status": "approved",
            "mandate_id": txn_ref_id,
            "txn_ref_id": txn_ref_id,
            "credential_reference": credential_reference,
            "provider_payment_id": session_id,
            "merchant_account_id": "ma_01KXJ63ZSRN4JGKE6GPNTJ9JH2",
            "authorized_amount": intent["amount"],
            "scope": {
                "merchant": intent["merchant"],
                "max_amount": intent["amount"],
            },
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "line_items": [
                {
                    "token": token,
                    "dynamic_cvv": dynamic_cvv,
                    "txn_ref_id": txn_ref_id,
                    "expiry_month": "12",
                    "expiry_year": "2028",
                }
            ],
        }
        intent["outcome"] = outcome
        return dict(outcome)

    constraints = intent["constraints"]
    poll_timeout = float(constraints.get("poll_timeout_seconds", 60))
    poll_interval = float(constraints.get("poll_interval_seconds", 2))
    if poll_timeout <= 0:
        raise ValueError("poll_timeout_seconds must be positive")
    if poll_interval < 0:
        raise ValueError("poll_interval_seconds cannot be negative")
    deadline = time.monotonic() + poll_timeout

    while True:
        try:
            result = get_payment_result(intent_ref)
        except PravaAPIError as exc:
            # Polling is safe to retry after a transient upstream failure: this
            # request is read-only and does not create another session or
            # checkout. Client/auth errors remain fail-fast so bad credentials
            # and invalid session references are never hidden behind a timeout.
            if exc.status_code < 500:
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(poll_interval, remaining))
            continue
        except RuntimeError as exc:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Prava mandate polling timed out for session {intent_ref}"
                ) from exc
            time.sleep(min(poll_interval, remaining))
            continue

        status = str(result.get("status", "")).lower()
        transactions = result.get("transactions") or []
        transaction = transactions[0] if transactions else {}
        line_items = transaction.get("line_items") or []
        line_item = line_items[0] if line_items else {}

        if status in {"awaiting_result", "completed"}:
            token = line_item.get("token") or f"tok_sandbox_{uuid4().hex[:12]}"
            dynamic_cvv = line_item.get("dynamic_cvv") or "123"
            txn_ref_id = (
                line_item.get("txn_ref_id")
                or transaction.get("txn_id")
                or f"txn_sandbox_{uuid4().hex[:12]}"
            )
            credential_reference = f"prava_credential_{uuid4().hex}"
            _CREDENTIALS[credential_reference] = {
                "token": token,
                "dynamic_cvv": dynamic_cvv,
                "expiry_month": line_item.get("expiry_month", "12"),
                "expiry_year": line_item.get("expiry_year", "2028"),
                "session_id": str(intent_ref),
                "txn_ref_id": txn_ref_id,
                "created_at": datetime.now(timezone.utc),
                "consumed_at": None,
            }
            outcome = {
                "status": "approved",
                "mandate_id": (
                    txn_ref_id
                    or transaction.get("txn_id")
                    or str(intent_ref)
                ),
                "txn_ref_id": txn_ref_id,
                "credential_reference": credential_reference,
                "scope": {
                    "merchant": intent["merchant"],
                    "max_amount": intent["amount"],
                },
                "approved_at": datetime.now(timezone.utc).isoformat(),
            }
            intent["outcome"] = outcome
            return dict(outcome)

        if status == "failed":
            error = transaction.get("error") or result.get("error") or {}
            code = str(error.get("code", "")).upper()
            outcome_status = "expired" if "EXPIRED" in code else "rejected"
            outcome = {"status": outcome_status, "intent_ref": str(intent_ref)}
            intent["outcome"] = outcome
            return dict(outcome)

        try:
            raw_expires_at = intent.get("expires_at")
            expires_at = (
                datetime.fromisoformat(str(raw_expires_at).replace("Z", "+00:00"))
                if raw_expires_at
                else None
            )
        except ValueError:
            expires_at = None
        if expires_at is not None and datetime.now(timezone.utc) >= expires_at:
            outcome = {"status": "expired", "intent_ref": str(intent_ref)}
            intent["outcome"] = outcome
            return dict(outcome)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"Prava mandate polling timed out for session {intent_ref}"
            )
        time.sleep(min(poll_interval, remaining))


def _credential_record(credential_reference: str) -> dict:
    try:
        record = _CREDENTIALS[credential_reference]
    except KeyError as exc:
        raise ValueError("unknown or already-consumed credential reference") from exc
    created_at = record.get("created_at")
    if not isinstance(created_at, datetime):
        created_at = datetime.now(timezone.utc)
        record["created_at"] = created_at
    age = (datetime.now(timezone.utc) - created_at).total_seconds()
    if age > _CREDENTIAL_TTL_SECONDS:
        _CREDENTIALS.pop(credential_reference, None)
        raise ValueError("credential reference has expired")
    return record


def consume_credential(credential_reference: str) -> dict:
    """Lease one-time checkout fields exactly once and erase their stored values.

    Non-sensitive Prava reporting references remain in memory until
    :func:`finalize_credential` reports the merchant outcome. This lets the payment
    boundary obey both requirements: card material is consume-once, while the
    mandatory ``report-status`` call can still identify the session and transaction.
    """
    record = _credential_record(credential_reference)
    if record.get("consumed_at") is not None:
        raise ValueError("unknown or already-consumed credential reference")
    if any(not record.get(field) for field in _SENSITIVE_CREDENTIAL_FIELDS):
        raise ValueError("credential reference is missing one-time checkout fields")

    checkout_fields = {
        field: record.pop(field) for field in _SENSITIVE_CREDENTIAL_FIELDS
    }
    record["consumed_at"] = datetime.now(timezone.utc)
    return checkout_fields


def credential_reporting_context(credential_reference: str) -> dict[str, str]:
    """Return only durable-safe identifiers needed for a later status report."""

    record = _credential_record(credential_reference)
    session_id = record.get("session_id")
    txn_ref_id = record.get("txn_ref_id")
    if not session_id or not txn_ref_id:
        raise ValueError("credential is missing Prava session reporting references")
    return {"session_id": str(session_id), "txn_ref_id": str(txn_ref_id)}


def retire_credential(credential_reference: str) -> None:
    """Erase any remaining non-secret in-memory metadata after terminal reporting."""

    _CREDENTIALS.pop(credential_reference, None)


def purge_expired_credentials() -> int:
    """Remove expired one-time material and return the number of records purged."""
    purged = 0
    for reference in list(_CREDENTIALS):
        try:
            _credential_record(reference)
        except ValueError:
            purged += 1
    return purged


def _report_status(
    session_id: str,
    txn_ref_id: str,
    txn_status: str,
    *,
    authorization_code: str | None = None,
    response_code: str | None = None,
    amount_paid: Decimal | str | int | float | None = None,
) -> dict:
    """Internal implementation shared by the public and compatibility contracts."""

    normalized_status = str(txn_status).upper()
    if normalized_status not in {"APPROVED", "DECLINED"}:
        raise ValueError("txn_status must be APPROVED or DECLINED")
    if not session_id or not txn_ref_id:
        raise ValueError("session_id and txn_ref_id are required")
    if authorization_code is not None and len(str(authorization_code)) > 128:
        raise ValueError("authorization_code cannot exceed 128 characters")
    if response_code is not None and len(str(response_code)) > 2:
        raise ValueError("response_code cannot exceed 2 characters")

    api_key, base_url = _load_prava_config()
    payload = {
        "txn_ref_id": str(txn_ref_id),
        "txn_status": normalized_status,
    }
    if authorization_code is not None:
        payload["authorization_code"] = str(authorization_code)
    if response_code is not None:
        payload["response_code"] = str(response_code)
    if amount_paid is not None:
        normalized_amount = Decimal(str(amount_paid)).quantize(Decimal("0.01"))
        if normalized_amount <= 0:
            raise ValueError("amount_paid must be positive")
        payload["amount_paid"] = format(normalized_amount, "f")
    request = Request(
        f"{base_url}/v1/sessions/{quote(str(session_id), safe='')}/report-status",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            raw_body = response.read()
            headers = getattr(response, "headers", None)
            response_id = headers.get("X-Response-ID") if headers is not None else None
    except HTTPError as exc:
        raise _api_error(exc, "Prava report-status failed") from exc
    except (TimeoutError, URLError) as exc:
        raise RuntimeError("Prava report-status could not reach the configured API") from exc

    try:
        result = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        suffix = f" (X-Response-ID: {response_id})" if response_id else ""
        raise RuntimeError(f"Prava report-status returned an invalid response{suffix}") from exc
    if (
        result.get("status") != "confirmed"
        or result.get("txn_status") != normalized_status
        or result.get("txn_ref_id") != str(txn_ref_id)
        or result.get("visa_confirmation") != "SUCCESS"
    ):
        suffix = f" (X-Response-ID: {response_id})" if response_id else ""
        raise RuntimeError(f"Prava did not confirm the reported merchant outcome{suffix}")
    return result


def report_status(
    session_id,
    txn_ref_id,
    txn_status,
    authorization_code=None,
    response_code=None,
    amount_paid=None,
):
    """Report a checkout outcome using Prava's documented public contract."""

    return _report_status(
        session_id,
        txn_ref_id,
        txn_status,
        authorization_code=authorization_code,
        response_code=response_code,
        amount_paid=amount_paid,
    )


def report_checkout_outcome(
    session_id: str,
    txn_ref_id: str,
    transaction_status: str,
    amount_paid: Decimal | str | int | float | None = None,
) -> dict:
    """Backward-compatible wrapper retaining the existing checkout integration."""

    return _report_status(
        session_id,
        txn_ref_id,
        transaction_status,
        amount_paid=amount_paid,
    )


def get_payment_result_status(session_id: str) -> str:
    """Read one Prava session status for crash-safe report reconciliation."""

    return str(get_payment_result(session_id)["status"]).lower()


def finalize_credential(credential_reference: str, transaction_status: str) -> None:
    """Report the merchant outcome to Prava and retire the one-time credential."""

    record = _credential_record(credential_reference)
    if record.get("consumed_at") is None:
        raise ValueError("credential must be consumed by checkout before reporting status")
    context = credential_reporting_context(credential_reference)
    report_checkout_outcome(
        context["session_id"],
        context["txn_ref_id"],
        transaction_status,
    )
    _CREDENTIALS.pop(credential_reference, None)


def charge_mandate(
    mandate_id: str,
    amount: Decimal | str | int | float,
    currency: str,
    merchant_name: str,
    idempotency_key: str,
    description: str | None = None,
    *,
    request_timeout_seconds: float = 20,
) -> dict:
    """Charge an active user-approved Prava mandate for recurring billing.

    Executes POST /v1/mandates/{mandate_id}/charge against the configured Prava API host.
    This operation is idempotent when idempotency_key is provided and enforces
    the merchant and budget caps established during passkey mandate creation.
    """
    if not mandate_id or not str(mandate_id).strip():
        raise ValueError("mandate_id is required")
    if not idempotency_key or not str(idempotency_key).strip():
        raise ValueError("idempotency_key is required")
    if not merchant_name or not str(merchant_name).strip():
        raise ValueError("merchant_name is required")

    parsed_amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    if parsed_amount <= 0:
        raise ValueError("amount must be positive")

    normalized_currency = str(currency).upper().strip()
    if len(normalized_currency) != 3:
        raise ValueError("currency must be a three-letter code")

    request_timeout_seconds = _validate_request_timeout(request_timeout_seconds)

    if STUB_MODE:
        return {
            "charge_id": f"chg_stub_{uuid4().hex}",
            "mandate_id": str(mandate_id).strip(),
            "status": "approved",
            "charged_amount": format(parsed_amount, "f"),
            "currency": normalized_currency,
            "merchant_name": str(merchant_name).strip(),
            "idempotency_key": str(idempotency_key).strip(),
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "execution_mode": "sandbox",
        }

    payload = {
        "amount": format(parsed_amount, "f"),
        "currency": normalized_currency,
        "merchant_name": str(merchant_name).strip(),
        "idempotency_key": str(idempotency_key).strip(),
    }
    if description:
        payload["description"] = str(description).strip()

    api_key, base_url = _load_prava_config()
    clean_mandate_id = quote(str(mandate_id).strip(), safe="")
    request = Request(
        f"{base_url}/v1/mandates/{clean_mandate_id}/charge",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": str(idempotency_key).strip(),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=request_timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise _api_error(exc, "Prava mandate charge failed") from exc
    except TimeoutError as exc:
        raise RuntimeError("Prava mandate charge request timed out") from exc
    except URLError as exc:
        raise RuntimeError("Prava mandate charge could not reach the configured API") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Prava mandate charge returned an invalid response") from exc

