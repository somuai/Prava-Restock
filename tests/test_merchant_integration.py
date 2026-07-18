"""Opt-in Zepto OAuth/quote checks; excluded from CI by default."""

import os

import pytest

from merchant import zepto_checkout
from merchant.zepto_mcp import ZeptoMCPClient


pytestmark = pytest.mark.integration


def test_real_zepto_saved_addresses_and_cart_preview() -> None:
    if os.getenv("ZEPTO_INTERACTIVE") != "1":
        pytest.skip("set ZEPTO_INTERACTIVE=1 to allow Zepto OAuth/OTP")
    address_id = os.getenv("ZEPTO_ADDRESS_ID", "").strip()
    if not address_id:
        pytest.skip("ZEPTO_ADDRESS_ID must name a saved Zepto address")

    client = ZeptoMCPClient(timeout_seconds=120)
    addresses = client.list_saved_addresses()
    assert addresses
    quote = zepto_checkout.fetch_real_quote(
        "prepared-cart",
        "Prepared Zepto cart",
        address_id,
        client=client,
    )
    assert quote.merchant == "zepto"
    assert quote.currency == "INR"
    assert quote.amount > 0
    assert quote.execution_mode.value == "real"
