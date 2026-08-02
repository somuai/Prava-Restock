"""Minimal typed client for Zepto's published remote MCP server.

OAuth and mobile OTP are owned by ``mcp-remote``. This module deliberately
contains no Zepto credentials and never creates a payment link unless its
explicit method is called.
"""

import asyncio
import json
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client


ZEPTO_MCP_URL = "https://mcp.zepto.co.in/mcp"
MCP_REMOTE_VERSION = "0.1.38"
MCP_REMOTE_PACKAGE = f"mcp-remote@{MCP_REMOTE_VERSION}"
MCP_REMOTE_BINARY = "/opt/zepto-mcp/node_modules/.bin/mcp-remote"
MCP_REMOTE_REPO_BINARY = (
    Path(__file__).resolve().parent / "mcp-runtime" / "node_modules" / ".bin" / "mcp-remote"
)
MCP_AUTHORIZATION_VERIFICATION_TTL_SECONDS = 300
_MCP_AUTHORIZATION_VERIFIED_AT: float | None = None
_RATE_LIMITED_UNTIL: float = 0.0


class ZeptoMCPError(RuntimeError):
    pass


class ZeptoRateLimitError(ZeptoMCPError):
    """Zepto refused a call because its provider-side request budget is exhausted."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ZeptoTransientError(ZeptoMCPError):
    """A temporary provider failure such as HTTP 529 or 503."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


READ_ONLY_TOOLS = frozenset(
    {
        "list_saved_addresses",
        "get_location_serviceability",
        "get_past_order_items",
        "search_products",
        "view_cart",
        "get_payment_methods",
        "check_payment_status",
        "list_order_history",
    }
)


def _retry_after(payload: Any) -> float | None:
    """Extract a bounded Retry-After hint without trusting provider payload shape."""

    if isinstance(payload, Mapping):
        for key in ("retryAfter", "retry_after", "retryAfterSeconds", "retry_after_seconds"):
            if payload.get(key) is not None:
                try:
                    return max(0.0, min(float(payload[key]), 60.0))
                except (TypeError, ValueError):
                    pass
        for value in payload.values():
            found = _retry_after(value)
            if found is not None:
                return found
    if isinstance(payload, list):
        for value in payload:
            found = _retry_after(value)
            if found is not None:
                return found
    return None


def _is_rate_limited(value: Any) -> bool:
    text = str(value).lower()
    return "429" in text or "too many requests" in text or "rate limit" in text


def _is_transient_provider_failure(value: Any) -> bool:
    text = str(value).lower()
    return any(
        marker in text
        for marker in (
            "529",
            "502",
            "503",
            "504",
            "overloaded",
            "temporarily unavailable",
            "service unavailable",
            "gateway timeout",
        )
    )


def resolve_mcp_remote_binary() -> str:
    """Resolve only the locked bridge; production cannot replace the image binary."""

    image_binary = Path(MCP_REMOTE_BINARY)
    override = os.getenv("MCP_REMOTE_BINARY", "").strip()
    production = os.getenv("RESTOCK_ENV", "development") == "production"
    if production:
        if override and Path(override) != image_binary:
            raise ZeptoMCPError(
                "MCP_REMOTE_BINARY cannot override the immutable production bridge"
            )
        candidate = image_binary
    elif override:
        candidate = Path(override)
        if not candidate.is_absolute():
            raise ZeptoMCPError("development MCP_REMOTE_BINARY must be absolute")
    elif MCP_REMOTE_REPO_BINARY.is_file():
        candidate = MCP_REMOTE_REPO_BINARY
    else:
        candidate = image_binary

    if not candidate.is_absolute() or not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise ZeptoMCPError(
            "locked mcp-remote runtime is unavailable; run npm ci in merchant/mcp-runtime"
        )
    return str(candidate)


def mcp_remote_runtime_ready() -> bool:
    """Return local executable readiness without contacting npm, OAuth, or Zepto."""

    try:
        resolve_mcp_remote_binary()
    except ZeptoMCPError:
        return False
    return True


def record_mcp_authorization_success() -> None:
    """Record a successful initialized provider call for a short local TTL."""

    global _MCP_AUTHORIZATION_VERIFIED_AT
    _MCP_AUTHORIZATION_VERIFIED_AT = time.monotonic()


def clear_mcp_authorization_verification() -> None:
    """Fail closed after any bridge, authentication, or provider-call failure."""

    global _MCP_AUTHORIZATION_VERIFIED_AT
    _MCP_AUTHORIZATION_VERIFIED_AT = None


def mcp_authorization_verified_recently() -> bool:
    """Return true only after a recent successful call in this process."""

    if _MCP_AUTHORIZATION_VERIFIED_AT is None:
        return False
    raw_ttl = os.getenv(
        "MCP_AUTHORIZATION_VERIFICATION_TTL_SECONDS",
        str(MCP_AUTHORIZATION_VERIFICATION_TTL_SECONDS),
    )
    try:
        ttl = int(raw_ttl)
    except ValueError:
        return False
    return ttl > 0 and time.monotonic() - _MCP_AUTHORIZATION_VERIFIED_AT <= ttl


def _content_to_payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, Mapping):
        return dict(structured)

    texts = [
        block.text
        for block in getattr(result, "content", [])
        if getattr(block, "type", None) == "text" and hasattr(block, "text")
    ]
    if not texts:
        return {}
    combined = "\n".join(texts)
    try:
        parsed = json.loads(combined)
    except json.JSONDecodeError:
        return {"text": combined}
    return parsed if isinstance(parsed, dict) else {"data": parsed}


class ZeptoMCPClient:
    """Call Zepto tools through a user bearer token or legacy MCP bridge.

    A bearer token is the production web path: the authenticated Restock user
    owns it.  The mcp-remote path remains limited to local/reviewer fixtures
    because its localhost OAuth callback stores one process-level cache.
    """

    def __init__(self, *, timeout_seconds: float = 45, access_token: str | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self.access_token = access_token.strip() if access_token else None

    async def _call_direct_async(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        if not self.access_token:
            raise AssertionError("direct Zepto call requires an access token")
        try:
            async with httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=httpx.Timeout(self.timeout_seconds),
            ) as http_client:
                async with streamable_http_client(
                    ZEPTO_MCP_URL,
                    http_client=http_client,
                ) as (read_stream, write_stream, _):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        result = await session.call_tool(name, arguments)
        except Exception as exc:
            if _is_rate_limited(exc):
                raise ZeptoRateLimitError(
                    f"Zepto rate-limited {name}; wait before trying again"
                ) from exc
            if _is_transient_provider_failure(exc):
                raise ZeptoTransientError(
                    f"Zepto is temporarily unavailable for {name}; retry later"
                ) from exc
            raise ZeptoMCPError(f"Zepto MCP call failed: {name}") from exc
        if getattr(result, "isError", False):
            payload = _content_to_payload(result)
            if _is_rate_limited(payload):
                raise ZeptoRateLimitError(
                    f"Zepto rate-limited {name}; wait before trying again",
                    retry_after_seconds=_retry_after(payload),
                )
            if _is_transient_provider_failure(payload):
                raise ZeptoTransientError(
                    f"Zepto is temporarily unavailable for {name}; retry later",
                    retry_after_seconds=_retry_after(payload),
                )
            raise ZeptoMCPError(f"Zepto tool {name} returned an error: {payload}")
        return _content_to_payload(result)

    async def _call_once_async(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.access_token:
            payload = await self._call_direct_async(name, arguments)
            record_mcp_authorization_success()
            return payload
        try:
            server = StdioServerParameters(
                command=resolve_mcp_remote_binary(),
                args=[ZEPTO_MCP_URL],
            )
            async with stdio_client(server) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
        except Exception as exc:
            if _is_rate_limited(exc):
                raise ZeptoRateLimitError(
                    f"Zepto rate-limited {name}; wait before trying again"
                ) from exc
            if _is_transient_provider_failure(exc):
                raise ZeptoTransientError(
                    f"Zepto is temporarily unavailable for {name}; retry later"
                ) from exc
            clear_mcp_authorization_verification()
            raise ZeptoMCPError(f"Zepto MCP call failed: {name}") from exc
        if getattr(result, "isError", False):
            payload = _content_to_payload(result)
            if _is_rate_limited(payload):
                raise ZeptoRateLimitError(
                    f"Zepto rate-limited {name}; wait before trying again",
                    retry_after_seconds=_retry_after(payload),
                )
            if _is_transient_provider_failure(payload):
                raise ZeptoTransientError(
                    f"Zepto is temporarily unavailable for {name}; retry later",
                    retry_after_seconds=_retry_after(payload),
                )
            clear_mcp_authorization_verification()
            raise ZeptoMCPError(f"Zepto tool {name} returned an error: {payload}")
        payload = _content_to_payload(result)
        record_mcp_authorization_success()
        return payload

    async def _call_async(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Retry one provider-throttled read, but never retry a mutating tool."""

        global _RATE_LIMITED_UNTIL
        if name in READ_ONLY_TOOLS and time.monotonic() < _RATE_LIMITED_UNTIL:
            raise ZeptoRateLimitError(
                f"Zepto read cooldown is active for {name}",
                retry_after_seconds=max(1.0, _RATE_LIMITED_UNTIL - time.monotonic()),
            )
        attempts = 2 if name in READ_ONLY_TOOLS else 1
        for attempt in range(attempts):
            try:
                payload = await self._call_once_async(name, arguments)
                _RATE_LIMITED_UNTIL = 0.0
                return payload
            except (ZeptoRateLimitError, ZeptoTransientError) as exc:
                delay = exc.retry_after_seconds
                if delay is None:
                    try:
                        fallback = (
                            "ZEPTO_RATE_LIMIT_RETRY_SECONDS"
                            if isinstance(exc, ZeptoRateLimitError)
                            else "ZEPTO_TRANSIENT_RETRY_SECONDS"
                        )
                        default = "30" if isinstance(exc, ZeptoRateLimitError) else "10"
                        delay = float(os.getenv(fallback, default))
                    except ValueError:
                        delay = 30.0 if isinstance(exc, ZeptoRateLimitError) else 10.0
                delay = max(0.0, min(delay, 60.0))
                _RATE_LIMITED_UNTIL = time.monotonic() + delay
                if attempt + 1 >= attempts:
                    raise type(exc)(str(exc), retry_after_seconds=delay) from exc
                await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                asyncio.wait_for(
                    self._call_async(name, arguments or {}),
                    timeout=self.timeout_seconds,
                )
            )
        raise ZeptoMCPError("synchronous Zepto calls must run outside an event loop")

    def list_saved_addresses(self) -> dict[str, Any]:
        return self.call("list_saved_addresses")

    def select_saved_address(self, address_id: str) -> dict[str, Any]:
        return self.call("select_saved_address", {"addressId": address_id})

    def get_location_serviceability(
        self, latitude: float | str, longitude: float | str
    ) -> dict[str, Any]:
        return self.call(
            "get_location_serviceability",
            {"latitude": latitude, "longitude": longitude},
        )

    def select_store(
        self,
        store_id: str,
        latitude: float | str,
        longitude: float | str,
    ) -> dict[str, Any]:
        return self.call(
            "select_store",
            {"storeId": store_id, "latitude": latitude, "longitude": longitude},
        )

    def search_products(self, query: str) -> dict[str, Any]:
        return self.call("search_products", {"query": query, "pageNumber": 0})

    def get_past_order_items(self) -> dict[str, Any]:
        return self.call("get_past_order_items")

    def update_cart(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.call("update_cart", arguments)

    def view_cart(self) -> dict[str, Any]:
        return self.call("view_cart")

    def get_payment_methods(self) -> dict[str, Any]:
        return self.call("get_payment_methods")

    def preview_order(self, address_id: str) -> dict[str, Any]:
        return self.call(
            "create_online_payment_order",
            {
                "confirmOrder": False,
                "riderTip": 0,
                "userAddressId": address_id,
                "useZeptoCash": False,
            },
        )

    def create_payment_link(self, address_id: str) -> dict[str, Any]:
        return self.call(
            "create_online_payment_order",
            {
                "confirmOrder": True,
                "riderTip": 0,
                "userAddressId": address_id,
                "useZeptoCash": False,
            },
        )

    def check_payment_status(self, order_id: str, *, poll: bool = False) -> dict[str, Any]:
        return self.call("check_payment_status", {"orderId": order_id, "poll": poll})

    def list_order_history(self) -> dict[str, Any]:
        return self.call("list_order_history")
