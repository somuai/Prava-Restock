"""Operator-owned browser boundary for one-time Zepto payment credentials.

Restock deliberately does not guess provider DOM selectors.  A reviewed,
absolute executable receives the short-lived fields over stdin, drives the
operator-approved browser, and returns only sanitized navigation metadata.
No credential is placed in argv, the environment, logs, or durable storage.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any

from merchant.zepto_checkout import PaymentRedirectPolicy


class SubprocessBrowserPaymentExecutor:
    """Run a reviewed payment browser executable without invoking a shell."""

    def __init__(self, executable: str, *, timeout_seconds: int = 300) -> None:
        path = Path(executable)
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError("payment executor must be an absolute executable file")
        self.executable = str(path)
        self.timeout_seconds = min(max(int(timeout_seconds), 30), 600)

    def execute(
        self,
        *,
        payment_link: str,
        token: str,
        dynamic_cvv: str,
        expiry_month: str,
        expiry_year: str,
        redirect_policy: PaymentRedirectPolicy,
        expected_amount: str | None = None,
        currency: str | None = None,
    ) -> dict[str, Any]:
        redirect_policy.validate_url(payment_link)
        payload = json.dumps(
            {
                "payment_link": payment_link,
                "token": token,
                "dynamic_cvv": dynamic_cvv,
                "expiry_month": expiry_month,
                "expiry_year": expiry_year,
                "allowed_hosts": list(redirect_policy.allowed_hosts),
                "expected_amount": expected_amount,
                "currency": currency,
            }
        )
        completed = subprocess.run(
            [self.executable],
            input=payload,
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
            env={"PATH": os.environ.get("PATH", "")},
        )
        # Never include stdout, stderr, or input material in exceptions: an
        # operator executable could accidentally echo the one-time fields.
        if completed.returncode != 0:
            raise RuntimeError("payment browser executor failed")
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("payment browser executor returned invalid JSON") from exc
        if not isinstance(result, dict) or not isinstance(result.get("visited_urls"), list):
            raise RuntimeError("payment browser executor returned an invalid result")
        for url in result["visited_urls"]:
            redirect_policy.validate_url(str(url))
        sanitized = {
            "visited_urls": [str(url) for url in result["visited_urls"]],
            "credential_used": result.get("credential_used") is True,
        }
        # Provider-specific executors may return these non-secret reconciliation
        # fields.  Only a closed vocabulary crosses back into Restock; arbitrary
        # page text, HTML, stdout, and stderr are intentionally discarded.
        if "payment_status" in result:
            payment_status = str(result["payment_status"]).lower()
            if payment_status not in {"completed", "failed", "pending"}:
                raise RuntimeError("payment browser executor returned an invalid status")
            sanitized["payment_status"] = payment_status
        if result.get("merchant_order_id"):
            sanitized["merchant_order_id"] = str(result["merchant_order_id"])[:255]
        if result.get("observed_amount") is not None:
            sanitized["observed_amount"] = str(result["observed_amount"])
        if result.get("currency") is not None:
            sanitized["currency"] = str(result["currency"]).upper()[:3]
        return sanitized
