"""Server-side Prava client using the documented Session REST API.

Prava does not publish a Python SDK. The browser-only ``@prava-sdk/core``
package owns card entry and passkey approval; this module implements the
server-side session calls that Prava documents for Python applications.
"""

import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

from dotenv import load_dotenv


STUB_MODE = False


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


def create_intent(merchant, amount, item_description, constraints):
    """Create a Prava session in the explicitly configured environment."""
    parsed_amount = Decimal(str(amount))
    if parsed_amount <= 0:
        raise ValueError("amount must be positive")

    constraints = dict(constraints)
    api_key, base_url = _load_prava_config()

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

    payload = {
        "user_id": constraints.get("user_id", "restock-sandbox-user"),
        "user_email": constraints.get(
            "user_email", "restock-sandbox@example.com"
        ),
        "total_amount": amount_string,
        "currency": str(currency).upper(),
        "external_order_ref": constraints.get(
            "external_order_ref", f"restock-{uuid4().hex}"
        ),
        "description": str(item_description),
        "integration_type": constraints.get("integration_type", "full_checkout"),
        "purchase_context": [
            {
                "merchant_details": {
                    "name": merchant_name,
                    "url": merchant_url,
                    "country_code_iso2": str(merchant_country).upper(),
                    "category_code": constraints.get("category_code", "5411"),
                    "category": constraints.get("category", "General merchandise"),
                },
                "product_details": [
                    {
                        "description": str(item_description),
                        "unit_price": amount_string,
                        "product_id": constraints.get("product_id"),
                        "quantity": int(constraints.get("quantity", 1)),
                    }
                ],
                "effective_until_minutes": effective_until_minutes,
            }
        ],
    }
    if payload["purchase_context"][0]["product_details"][0]["product_id"] is None:
        del payload["purchase_context"][0]["product_details"][0]["product_id"]
    callback_url = constraints.get("callback_url")
    if callback_url:
        payload["callback_url"] = callback_url

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
        with urlopen(
            request,
            timeout=float(constraints.get("request_timeout_seconds", 20)),
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            error = json.loads(exc.read().decode("utf-8")).get("error", {})
        except (json.JSONDecodeError, UnicodeDecodeError):
            error = {}
        code = error.get("code", "HTTP_ERROR")
        message = error.get("message", "Prava session creation failed")
        raise RuntimeError(f"Prava API {exc.code} {code}: {message}") from exc
    except TimeoutError as exc:
        raise RuntimeError("Prava session creation timed out") from exc
    except URLError as exc:
        raise RuntimeError("Prava session creation could not reach the configured API") from exc

    required = {"session_id", "iframe_url", "expires_at"}
    missing = required.difference(result)
    if missing:
        raise RuntimeError(
            f"Prava session response missing required fields: {sorted(missing)}"
        )

    intent_ref = str(result["session_id"])
    _INTENTS[intent_ref] = {
        "merchant": merchant_name,
        "amount": amount_string,
        "item_description": str(item_description),
        "constraints": constraints,
        "iframe_url": result["iframe_url"],
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
            "merchant": str(merchant),
            "amount": str(amount),
            "item_description": "Restock checkout",
            "constraints": dict(constraints or {}),
            "expires_at": None,
            "restored": True,
        },
    )


def await_mandate(intent_ref):
    """Poll a real Prava session until approved, rejected, expired, or timed out."""
    try:
        intent = _INTENTS[intent_ref]
    except KeyError as exc:
        raise ValueError(f"unknown intent_ref: {intent_ref}") from exc

    if "outcome" in intent:
        return dict(intent["outcome"])

    api_key, base_url = _load_prava_config()

    constraints = intent["constraints"]
    poll_timeout = float(constraints.get("poll_timeout_seconds", 90))
    poll_interval = float(constraints.get("poll_interval_seconds", 3))
    if poll_timeout <= 0:
        raise ValueError("poll_timeout_seconds must be positive")
    if poll_interval < 0:
        raise ValueError("poll_interval_seconds cannot be negative")
    deadline = time.monotonic() + poll_timeout

    while True:
        request = Request(
            f"{base_url}/v1/sessions/{quote(str(intent_ref), safe='')}/payment-result",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        try:
            with urlopen(
                request,
                timeout=float(constraints.get("request_timeout_seconds", 20)),
            ) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                error = json.loads(exc.read().decode("utf-8")).get("error", {})
            except (json.JSONDecodeError, UnicodeDecodeError):
                error = {}
            code = error.get("code", "HTTP_ERROR")
            message = error.get("message", "Prava payment-result polling failed")
            raise RuntimeError(f"Prava API {exc.code} {code}: {message}") from exc
        except (TimeoutError, URLError) as exc:
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

        if status == "awaiting_result":
            token = line_item.get("token")
            dynamic_cvv = line_item.get("dynamic_cvv")
            if token and dynamic_cvv:
                credential_reference = f"prava_credential_{uuid4().hex}"
                _CREDENTIALS[credential_reference] = {
                    "token": token,
                    "dynamic_cvv": dynamic_cvv,
                    "expiry_month": line_item.get("expiry_month"),
                    "expiry_year": line_item.get("expiry_year"),
                    "session_id": str(intent_ref),
                    "txn_ref_id": line_item.get("txn_ref_id"),
                    "created_at": datetime.now(timezone.utc),
                    "consumed_at": None,
                }
                outcome = {
                    "status": "approved",
                    "mandate_id": (
                        line_item.get("txn_ref_id")
                        or transaction.get("txn_id")
                        or str(intent_ref)
                    ),
                    "credential_reference": credential_reference,
                    "scope": {
                        "merchant": intent["merchant"],
                        "max_amount": intent["amount"],
                    },
                    "approved_at": datetime.now(timezone.utc).isoformat(),
                }
                intent["outcome"] = outcome
                return dict(outcome)

        if status == "completed":
            raise RuntimeError(
                "Prava session is already completed; no reusable checkout credential exists"
            )

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


def report_checkout_outcome(
    session_id: str,
    txn_ref_id: str,
    transaction_status: str,
    amount_paid: Decimal | str | int | float | None = None,
) -> dict:
    """Report a known merchant outcome using non-secret Prava references."""

    normalized_status = str(transaction_status).upper()
    if normalized_status not in {"APPROVED", "DECLINED"}:
        raise ValueError("transaction_status must be APPROVED or DECLINED")
    if not session_id or not txn_ref_id:
        raise ValueError("session_id and txn_ref_id are required")

    api_key, base_url = _load_prava_config()
    payload = {
        "txn_ref_id": str(txn_ref_id),
        "txn_status": normalized_status,
    }
    if amount_paid is not None:
        normalized_amount = Decimal(str(amount_paid)).quantize(Decimal("0.01"))
        if normalized_amount <= 0:
            raise ValueError("amount_paid must be positive")
        payload["amount_paid"] = float(normalized_amount)
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
        response_id = exc.headers.get("X-Response-ID") if exc.headers is not None else None
        suffix = f" (X-Response-ID: {response_id})" if response_id else ""
        raise RuntimeError(
            f"Prava report-status failed with HTTP {exc.code}{suffix}"
        ) from exc
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


def get_payment_result_status(session_id: str) -> str:
    """Read one Prava session status for crash-safe report reconciliation."""

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
        response_id = exc.headers.get("X-Response-ID") if exc.headers else None
        suffix = f" (X-Response-ID: {response_id})" if response_id else ""
        raise RuntimeError(
            f"Prava payment-result failed with HTTP {exc.code}{suffix}"
        ) from exc
    except (TimeoutError, URLError) as exc:
        raise RuntimeError("Prava payment-result could not reach the configured API") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Prava payment-result returned an invalid response") from exc
    status = str(result.get("status", "")).lower()
    if status not in {"pending", "awaiting_result", "completed", "failed"}:
        raise RuntimeError("Prava payment-result returned an unknown status")
    return status


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
