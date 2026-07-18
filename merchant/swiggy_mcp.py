"""Generic client for Prava's published Swiggy MCP endpoints.

The official skill documents distinct Instamart, Food, and Dineout servers.
This adapter defaults to Instamart and deliberately exposes only catalog/cart
operations; online card checkout remains an interactive browser boundary.
"""

import asyncio
import json
from collections.abc import Mapping
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


SWIGGY_ENDPOINTS = {
    "instamart": "https://mcp.swiggy.com/im",
    "food": "https://mcp.swiggy.com/food",
    "dineout": "https://mcp.swiggy.com/dineout",
}


def _payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, Mapping):
        return dict(structured)
    text = "\n".join(
        block.text for block in getattr(result, "content", [])
        if getattr(block, "type", None) == "text" and hasattr(block, "text")
    )
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"text": text}
    return parsed if isinstance(parsed, dict) else {"data": parsed}


class SwiggyMCPClient:
    def __init__(self, surface: str = "instamart", timeout_seconds: float = 45) -> None:
        if surface not in SWIGGY_ENDPOINTS:
            raise ValueError("unknown Swiggy surface")
        self.url = SWIGGY_ENDPOINTS[surface]
        self.timeout_seconds = timeout_seconds

    async def _call_async(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        server = StdioServerParameters(command="npx", args=["--yes", "mcp-remote", self.url])
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
        if getattr(result, "isError", False):
            raise RuntimeError(f"Swiggy tool {name} failed: {_payload(result)}")
        return _payload(result)

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(asyncio.wait_for(
                self._call_async(name, arguments or {}),
                timeout=self.timeout_seconds,
            ))
        raise RuntimeError("synchronous Swiggy calls must run outside an event loop")

    def get_addresses(self) -> dict[str, Any]:
        return self.call("get_addresses")

    def search(self, query: str) -> dict[str, Any]:
        return self.call("search", {"query": query})

    def view_cart(self) -> dict[str, Any]:
        return self.call("view_cart")
