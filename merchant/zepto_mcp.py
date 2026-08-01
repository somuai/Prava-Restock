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

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


ZEPTO_MCP_URL = "https://mcp.zepto.co.in/mcp"
MCP_REMOTE_VERSION = "0.1.38"
MCP_REMOTE_PACKAGE = f"mcp-remote@{MCP_REMOTE_VERSION}"
MCP_REMOTE_BINARY = "/opt/zepto-mcp/node_modules/.bin/mcp-remote"
MCP_REMOTE_REPO_BINARY = (
    Path(__file__).resolve().parent / "mcp-runtime" / "node_modules" / ".bin" / "mcp-remote"
)
MCP_AUTHORIZATION_VERIFICATION_TTL_SECONDS = 300
_MCP_AUTHORIZATION_VERIFIED_AT: float | None = None


class ZeptoMCPError(RuntimeError):
    pass


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
    """Call Zepto tools through the official ``mcp-remote`` OAuth bridge."""

    def __init__(self, *, timeout_seconds: float = 45) -> None:
        self.timeout_seconds = timeout_seconds

    async def _call_async(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
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
            clear_mcp_authorization_verification()
            raise ZeptoMCPError(f"Zepto MCP call failed: {name}") from exc
        if getattr(result, "isError", False):
            clear_mcp_authorization_verification()
            payload = _content_to_payload(result)
            raise ZeptoMCPError(f"Zepto tool {name} returned an error: {payload}")
        payload = _content_to_payload(result)
        record_mcp_authorization_success()
        return payload

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
