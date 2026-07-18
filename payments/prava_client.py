"""Server-side Prava sandbox client using the documented Session REST API.

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

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SANDBOX_URL = "https://sandbox.api.prava.space"
_INTENTS: dict[str, dict] = {}
# One-time token/CVV values are held only in process memory and are never
# returned, logged, or persisted. Downstream code receives an opaque reference.
_CREDENTIALS: dict[str, dict] = {}
_CREDENTIAL_TTL_SECONDS = 15 * 60


def _load_sandbox_config() -> tuple[str, str]:
    load_dotenv(_PROJECT_ROOT / ".env", override=False)
    api_key = os.getenv("PRAVA_API_KEY", "").strip()
    base_url = os.getenv("PRAVA_SANDBOX_URL", "").strip().rstrip("/")
    if not api_key:
        raise RuntimeError("PRAVA_API_KEY is not configured in .env")
    if not base_url:
        raise RuntimeError("PRAVA_SANDBOX_URL is not configured in .env")
    if not api_key.startswith("sk_test_"):
        raise RuntimeError("Phase 7 accepts only a Prava sandbox sk_test_* key")
    if base_url != _SANDBOX_URL:
        raise RuntimeError(
            f"Phase 7 accepts only the official Prava sandbox host: {_SANDBOX_URL}"
        )
    return api_key, base_url


def create_intent(merchant, amount, item_description, constraints):
    """Create a real Prava sandbox session and return its session identifier."""
    parsed_amount = Decimal(str(amount))
    if parsed_amount <= 0:
        raise ValueError("amount must be positive")

    constraints = dict(constraints)
    api_key, base_url = _load_sandbox_config()

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
        raise RuntimeError("Prava session creation could not reach the sandbox") from exc

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


def await_mandate(intent_ref):
    """Poll a real Prava session until approved, rejected, expired, or timed out."""
    try:
        intent = _INTENTS[intent_ref]
    except KeyError as exc:
        raise ValueError(f"unknown intent_ref: {intent_ref}") from exc

    if "outcome" in intent:
        return dict(intent["outcome"])

    api_key, base_url = _load_sandbox_config()

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

        if status in {"awaiting_result", "completed"}:
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

        if status == "failed":
            error = transaction.get("error") or result.get("error") or {}
            code = str(error.get("code", "")).upper()
            outcome_status = "expired" if "EXPIRED" in code else "rejected"
            outcome = {"status": outcome_status, "intent_ref": str(intent_ref)}
            intent["outcome"] = outcome
            return dict(outcome)

        try:
            expires_at = datetime.fromisoformat(
                str(intent["expires_at"]).replace("Z", "+00:00")
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
    """Return one-time checkout fields exactly once, then delete them from memory."""
    record = dict(_credential_record(credential_reference))
    _CREDENTIALS.pop(credential_reference, None)
    record.pop("created_at", None)
    return record


def purge_expired_credentials() -> int:
    """Remove expired one-time material and return the number of records purged."""
    purged = 0
    for reference in list(_CREDENTIALS):
        try:
            _credential_record(reference)
        except ValueError:
            purged += 1
    return purged


def finalize_credential(credential_reference: str, transaction_status: str) -> None:
    """Report the merchant outcome to Prava and retire the one-time credential."""
    normalized_status = str(transaction_status).upper()
    if normalized_status not in {"APPROVED", "DECLINED"}:
        raise ValueError("transaction_status must be APPROVED or DECLINED")
    record = _credential_record(credential_reference)
    session_id = record.get("session_id")
    txn_ref_id = record.get("txn_ref_id")
    if not session_id or not txn_ref_id:
        raise ValueError("credential is missing Prava session reporting references")

    api_key, base_url = _load_sandbox_config()
    payload = {
        "txn_ref_id": str(txn_ref_id),
        "txn_status": normalized_status,
    }
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
            response.read()
    except HTTPError as exc:
        raise RuntimeError(
            f"Prava report-status failed with HTTP {exc.code}"
        ) from exc
    except (TimeoutError, URLError) as exc:
        raise RuntimeError("Prava report-status could not reach the sandbox") from exc
    _CREDENTIALS.pop(credential_reference, None)
