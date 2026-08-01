# Phase 8 merchant evidence

The Restock Home merchant boundary uses Zepto's official remote MCP server through `mcp-remote`. The final live-money step remains deliberately disabled and disclosed because Zepto does not publish a merchant payment sandbox.

## Verified against live Zepto MCP on 19 July 2026

- OAuth/mobile-OTP authorization completed successfully.
- The published tool schemas were retrieved and matched the adapter for saved addresses, search, cart, payment methods, preview/order creation, payment status, and order history.
- A saved Kolkata delivery area was selected.
- `search_products` returned live coffee results.
- The production price-trigger path resolved an exact Zepto product-variant ID and normalized its live minor-unit price to INR 90; it does not accept a similar result when the tracked SKU is absent.
- One available result was added to the cart for the smoke test.
- `view_cart` confirmed the cart was non-empty.
- `get_payment_methods` succeeded.
- `create_online_payment_order(confirmOrder=false)` returned a deliverable final-price preview.
- A `finally` cleanup removed the smoke-test product from the cart.

No order was confirmed, no payment link was created, no one-time credential was entered into Zepto, and no real money was spent.

## Provider-health recheck — 2 August 2026

A new read-only `list_saved_addresses` call completed through Zepto's official
MCP OAuth bridge and returned two saved addresses. The provider-side HTTP 429
reported during an earlier check was no longer present. Restock retries a
rate-limited read-only MCP operation at most once with a bounded delay. It never
automatically retries address/store selection, cart mutation, order preview, or
payment-order creation, because those operations can have side effects.

## Disclosure boundary

- Real: Prava sandbox approval and Zepto OAuth/catalog/address/exact-SKU price/cart/quote operations.
- Disclosed simulation: final Zepto payment execution unless an operator explicitly enables the compatible-card live path.
- Restock's API exposes this distinction through `/capabilities`.
