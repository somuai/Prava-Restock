"""Narrow merchant-availability probe used only before browser checkout.

An application bug must never be relabeled as merchant downtime.  Consequently,
HTTP 4xx responses still prove that the merchant system is reachable; only
connection failures, timeouts, and HTTP 5xx responses are considered unavailable.
"""

from __future__ import annotations

from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def check_merchant_availability(merchant_url: str) -> bool:
    """Return False only for transport failure, timeout, or merchant HTTP 5xx."""

    if not merchant_url or not str(merchant_url).strip():
        raise ValueError("merchant_url is required")
    request = Request(
        str(merchant_url),
        headers={"User-Agent": "Restock-Merchant-Health/1.0"},
        method="HEAD",
    )
    try:
        with urlopen(request, timeout=5) as response:
            status = getattr(response, "status", 200)
            return not isinstance(status, int) or status < 500
    except HTTPError as exc:
        return exc.code < 500
    except (TimeoutError, URLError, OSError):
        return False
