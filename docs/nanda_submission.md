# NANDA Town utility and Prava-track submission boundary

The standalone **Restock Trigger Math** service is hosted at
<https://restock-trigger-math-production.up.railway.app>. Its agent-facing
instructions are served at
<https://restock-trigger-math-production.up.railway.app/skill.md> and tracked
in [nanda_trigger_service/SKILL.md](../nanda_trigger_service/SKILL.md).

This utility is not the submission required for the current **Best Prava
Adapter for NANDA Town** track. The track submission is now implemented as the
standalone package in
[nanda_prava_adapter](../nanda_prava_adapter/README.md). It provides NANDA's
`quote`, `pay`, `verify_payment`, and `refund` interface over Prava's current
Session API, plus deterministic success/failure tests, an interactive sandbox
test, a scenario manifest, reuse documentation, and an installable
`nest.plugins.payments` entry point.

A draft upstream pull request is open at
<https://github.com/projnanda/nandatown/pull/208>. The NANDA repository's full
local gate passed: lint, format, strict type checking, and 1,318 tests. The
fresh interactive sandbox proof is intentionally still pending. It requires a
human to open Prava's short-lived card/passkey URL and will be run before the
pull request is marked ready. The test is marked `live`, so normal CI never
attempts an external transaction.

The adapter accurately preserves the refund boundary: Prava's official FAQ
says it exposes no separate refund endpoint, so `refund` delegates to the
destination merchant and fails closed if no merchant refund handler is
configured. The disclosed sandbox executor confirms a Prava sandbox outcome;
it must not be represented as a real merchant charge.

Authoritative requirements:
<https://nandatown.projectnanda.org/pravahack>
