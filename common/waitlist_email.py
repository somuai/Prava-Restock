"""Optional, provider-backed welcome email for newly stored waitlist leads.

Delivery is disabled by default.  Copy is intentionally static and curated;
no model is invoked and no recipient or provider secret is ever logged here.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from collections.abc import Callable
from typing import Any
from uuid import uuid4


RESEND_EMAILS_URL = "https://api.resend.com/emails"
WELCOME_SUBJECT = "You’re on the Restock waitlist"
_WELCOME_COPY = (
    "Thanks for joining Restock. We’re building a calmer way to keep "
    "everyday essentials and recurring tools from becoming last-minute chores.\n\n"
    "You’ll hear from us when your place is ready. Until then, no daily "
    "drip campaign and no inbox clutter.\n\n"
    "— Soumyajit\nRestock"
)


class WaitlistEmailError(RuntimeError):
    """A sanitized welcome-email configuration or delivery failure."""


class WaitlistEmailLeaseLost(WaitlistEmailError):
    """The durable delivery lease changed before an outcome was recorded."""


def provider_timeout_seconds() -> float:
    """Return a strict, bounded provider timeout for worker budget planning."""

    try:
        configured = float(
            os.getenv("RESTOCK_WAITLIST_EMAIL_TIMEOUT_SECONDS", "5")
        )
    except ValueError:
        configured = 5.0
    return min(10.0, max(1.0, configured))


def bounded_delivery_settings(
    *,
    configured_batch: int,
    configured_lease_seconds: int,
) -> tuple[int, int]:
    """Cap batch size and guarantee a lease for its worst-case I/O budget."""

    batch_size = min(5, max(1, configured_batch))
    minimum_lease = int(provider_timeout_seconds() * batch_size) + 30
    return batch_size, max(minimum_lease, configured_lease_seconds)


def _welcome_text(display_name: str | None) -> str:
    name = (display_name or "").strip()
    greeting = f"Hi {name}," if name else "Hi there,"
    return f"{greeting}\n\n{_WELCOME_COPY}"


def _idempotency_key(email_normalized: str) -> str:
    digest = hashlib.sha256(
        f"restock-waitlist-welcome-v1:{email_normalized}".encode("utf-8")
    ).hexdigest()
    return f"restock-waitlist-welcome-{digest}"


def send_waitlist_welcome(
    email_normalized: str,
    display_name: str | None = None,
) -> bool:
    """Send one welcome email when enabled; return whether delivery was attempted.

    Resend's idempotency header makes repeated attempts for the same normalized
    address safe. Provider details are deliberately collapsed into a sanitized
    exception so callers cannot accidentally log response bodies or secrets.
    """

    mode = os.getenv("RESTOCK_WAITLIST_EMAIL_MODE", "disabled").strip().lower()
    if mode == "disabled":
        return False
    if mode != "resend":
        raise WaitlistEmailError("waitlist welcome email configuration invalid")

    api_key = os.getenv("RESEND_API_KEY", "").strip()
    from_address = os.getenv("RESTOCK_WAITLIST_FROM_EMAIL", "").strip()
    if not api_key or not from_address or any(
        character in from_address for character in "\r\n"
    ):
        raise WaitlistEmailError("waitlist welcome email configuration invalid")

    payload = json.dumps(
        {
            "from": from_address,
            "to": [email_normalized],
            "subject": WELCOME_SUBJECT,
            "text": _welcome_text(display_name),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        RESEND_EMAILS_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": _idempotency_key(email_normalized),
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=provider_timeout_seconds()
        ) as response:
            status_code = getattr(response, "status", None)
            if status_code is None:
                status_code = response.getcode()
            response.read()
        if not 200 <= status_code < 300:
            raise RuntimeError("non-success provider response")
    except Exception:
        raise WaitlistEmailError(
            "waitlist welcome email delivery failed"
        ) from None
    return True


def attempt_waitlist_welcome_email(
    repository: Any,
    delivery: dict[str, Any],
    *,
    owner_id: str,
    sender: Callable[[str, str | None], bool] | None = None,
) -> str:
    """Attempt one durable delivery and persist only a sanitized outcome."""

    try:
        attempted = (sender or send_waitlist_welcome)(
            delivery["email_normalized"], delivery.get("display_name")
        )
    except Exception:
        finalized = repository.finalize_waitlist_welcome_delivery(
            delivery_id=delivery["delivery_id"],
            owner_id=owner_id,
            status="failed",
            last_error="delivery_failed",
        )
        if not finalized:
            raise WaitlistEmailLeaseLost(
                "waitlist welcome email lease lost"
            ) from None
        raise WaitlistEmailError(
            "waitlist welcome email delivery failed"
        ) from None
    if not attempted:
        released = repository.release_waitlist_welcome_delivery(
            delivery_id=delivery["delivery_id"],
            owner_id=owner_id,
        )
        if not released:
            raise WaitlistEmailLeaseLost("waitlist welcome email lease lost")
        return "disabled"
    finalized = repository.finalize_waitlist_welcome_delivery(
        delivery_id=delivery["delivery_id"],
        owner_id=owner_id,
        status="sent",
    )
    if not finalized:
        raise WaitlistEmailLeaseLost("waitlist welcome email lease lost")
    return "sent"


def retry_waitlist_welcome_emails(
    repository: Any,
    *,
    max_attempts: int = 3,
    limit: int = 100,
    lease_seconds: int = 120,
    sender: Callable[[str, str | None], bool] | None = None,
) -> dict[str, int]:
    """Retry bounded pending/failed welcome deliveries without logging PII."""

    if sender is None and os.getenv(
        "RESTOCK_WAITLIST_EMAIL_MODE", "disabled"
    ).strip().lower() == "disabled":
        return {
            "eligible": 0,
            "sent": 0,
            "failed": 0,
            "disabled": 1,
            "lost_lease": 0,
        }
    owner_id = f"waitlist-email-{uuid4().hex}"
    deliveries = repository.claim_waitlist_welcome_deliveries(
        owner_id=owner_id,
        max_attempts=max_attempts,
        limit=limit,
        lease_seconds=lease_seconds,
    )
    summary = {
        "eligible": len(deliveries),
        "sent": 0,
        "failed": 0,
        "disabled": 0,
        "lost_lease": 0,
    }
    for delivery in deliveries:
        try:
            result = attempt_waitlist_welcome_email(
                repository,
                delivery,
                owner_id=owner_id,
                sender=sender,
            )
        except WaitlistEmailLeaseLost:
            summary["lost_lease"] += 1
        except WaitlistEmailError:
            summary["failed"] += 1
        else:
            summary[result] += 1
    return summary
