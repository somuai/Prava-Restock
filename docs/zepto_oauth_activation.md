# Zepto user OAuth activation

Restock uses a separate Zepto OAuth connection for every signed-in user. It
does not share a browser cache, a Zepto phone number, saved address, or order
history between users.

## Implemented flow

1. The user signs in to Restock with Google (or the configured local account).
2. They choose **Connect Zepto** during pantry onboarding.
3. Restock creates an OAuth 2.1 authorization-code request with PKCE, stores
   only a hash of its one-time state and an encrypted verifier, then redirects
   the user to Zepto.
4. Zepto owns phone verification and consent. Restock never handles the user's
   Zepto password or OTP.
5. The callback exchanges the code server-side. Access and refresh tokens are
   encrypted in `merchant_connections`; they are never returned by the API or
   written to an audit log.
6. A user may request past-order *suggestions*. This returns a bounded list of
   product names/opaque SKU references and never creates a tracked item.
   The user must select a product, after which Restock obtains a fresh price,
   stock state, and exact SKU from Zepto before tracking it.

## Current provider gate — 2 August 2026

Zepto's published authorization metadata advertises Dynamic Client Registration
at `https://auth.zepto.co.in/register`. A registration attempt for the public
Railway callback returned `400 invalid_redirect_uri`: the Railway callback
domain is not currently allowlisted by Zepto. This is a provider-side onboarding
gate, not a Restock code or account-password failure.

Use `scripts/register_zepto_oauth_client.py --public-api-url <public-api-url>
--configure-railway` only after Zepto has allowlisted the callback. The script
stores any returned client secret directly in Railway variables rather than
printing it. Railway already holds the independently generated
`RESTOCK_MERCHANT_TOKEN_ENCRYPTION_KEY`; never place it in source control or
chat.

## Provider request

> Please allowlist `https://restock-offline-stub-production.up.railway.app/api/v1/integrations/zepto/callback` as Restock's OAuth callback URI for the Zepto MCP OAuth authorization-code + PKCE flow. Dynamic registration currently returns `invalid_redirect_uri`. We need `tools:read tools:write`, authorization-code and refresh-token grants for user-owned catalog/address/history access. We do not need or collect users' Zepto passwords or OTPs.

## 429 and 529 policy

- HTTP 429 is a Zepto rate limit. Restock places all read calls behind a bounded
  cooldown, retries once only when safe, and returns `Retry-After` to the UI.
- HTTP 529/502/503/504 are treated as temporary provider failures, not OAuth
  failures. Restock returns a bounded retry instruction and does not create a
  cart, payment link, or transaction.
- Mutating checkout operations are never blindly retried.
