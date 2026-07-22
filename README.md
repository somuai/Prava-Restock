# Restock

Restock is a consumption-triggered replenishment agent that predicts when recurring household essentials will run out, or when team subscriptions will renew, and prepares a bounded Prava payment flow before the deadline.

The repository contains the implementation through Phase 14: deterministic triggers, the Agents SDK orchestrator, a real Prava sandbox client, durable workflows, merchant adapters, user surfaces, tenant controls, native wrappers, and the forecasting foundation. Building an integration is distinct from activating it with provider credentials or real money; see [Phase 7 evidence](docs/phase7_evidence.md), [production readiness](docs/production_readiness.md), and the runtime disclosures below.

## Offline dry run

After installing the project, run `.venv/bin/python demo/dry_run.py` to exercise all five seeded items in deterministic demo mode. The Restock Teams billing checkout and final Home merchant charge are intentional, disclosed simulations.

## Local API

Run `.venv/bin/alembic upgrade head`, then `.venv/bin/uvicorn ui.api:app --reload`. Public liveness and capability endpoints are `/health`, `/ready`, and `/capabilities`; behavioral endpoints under `/api/v1` require `Authorization: Bearer $RESTOCK_API_TOKEN`. Development falls back to the documented local demo token, but production refuses behavioral requests until a real token is configured.

Run the scheduler as a separate process with `.venv/bin/python -m workflow.worker`. The `Procfile` keeps web and worker commands separate so multiple web replicas cannot duplicate trigger scans.

## Deployment

Hosted URL: [restock-offline-stub-production.up.railway.app](https://restock-offline-stub-production.up.railway.app)

After deployment, verify every public endpoint with:

```bash
./scripts/smoke_test.sh https://restock-offline-stub-production.up.railway.app
```

The hosted URL runs the current application in credential-free demo mode. Its public `/capabilities` response currently reports Prava as `sandbox_unconfigured`, all merchant/billing boundaries as `disclosed_mock`, channel integrations as unconfigured, real money disabled, and `demo_mode=true`. Local or platform-secret configuration can activate the implemented integrations; credentials are not committed or baked into the image.

## What is real and what is simulated

- **Real:** deterministic trigger logic, code-owned spend caps, OpenAI Agents SDK tool surface, and Prava sandbox intent/passkey/mandate integration.
- **Real merchant boundary:** Zepto OAuth/MCP client, address selection, live exact-SKU price lookup, cart preview, exact-price quote normalization, stock handling, and payment-status reconciliation interface. Similar search results are rejected rather than substituted.
- **Disclosed simulation:** final Zepto live-money charge and Restock Teams billing-portal fulfillment. Zepto publishes no merchant payment sandbox, so the final charge stays disabled unless an operator explicitly enables a compatible-card checkout.
- **Hosted runtime:** the current application is published, but the hosted environment remains deliberately unactivated: demo mode is on, provider credentials are absent, and real-money execution is disabled. `/capabilities` is authoritative for the running environment.

Runtime modes are returned by `/capabilities`. The default is `HOME_MERCHANT_MODE=disclosed_mock`; `ZEPTO_REAL_PAYMENT_ENABLED=1` is an additional operator gate and is never enabled in CI.

## Workflow and persistence

Phase 9 implemented a resumable database-backed state machine, Postgres-compatible SQLAlchemy repositories, an initial Alembic migration, unique active-workflow and idempotency constraints, authenticated action/resume endpoints, scheduler leases, sanitized mode-tagged audit entries, and cadence recalibration after completed Home purchases. SQLite is the zero-cost local/demo default; set `DATABASE_URL` to Postgres for a durable deployment.

Run `.venv/bin/python demo/dry_run.py --mode offline` for all five deterministic seeded workflows. Use `--mode integration --item coffee` for the explicitly interactive Prava path; it opens the short-lived approval page and never makes the live Zepto payment path automatic.

## Demo PWA and channels

The React/TypeScript PWA lives in `ui/web` and is served from `/app` in the production Docker image. Run `npm ci && npm run dev` there for local frontend development, or `npm run build` for the deployable bundle. Its Restock-owned decision inbox uses a conversational Home hierarchy and a denser Teams approval hierarchy, with explicit preview/sandbox/simulation disclosure at the affected step. Typography, color, logo usage, and interaction rules are documented in the [design system](docs/design-system.md).

- **Slack:** `channels/slack_manifest.yaml` and the Bolt Socket Mode adapter are implemented, the private workspace app is installed, bot authentication and a real Socket Mode handshake pass, and live notification delivery plus a persisted Skip callback are verified. Resolved messages remove their buttons to prevent repeated actions. A deployed persistent Slack process with rotated credentials remains the activation gate; see [Slack evidence](docs/slack_evidence.md). No Marketplace submission is needed for the private demo workspace.
- **WhatsApp:** the Cloud API adapter sends the three-button proactive template only after recorded opt-in. The webhook verifies Meta's HMAC signature and maps Approve/Skip actions to workflows; Adjust opens the amount UI. Configure the `WHATSAPP_*` values only in local/platform secrets.
- **Guaranteed submission path:** the PWA remains functional and visibly disclosed if Slack or Meta setup is still awaiting external approval.

No paid channel, store enrollment, hosting upgrade, or real Zepto payment is activated by repository code.

## Tenants and privacy

Phase 11 implemented Household and Organization tenants, owner/admin/approver/member roles, expiring one-use invitations, tenant-scoped items, multi-approver policies, consent records, privacy export, and deletion/pseudonymization. An explicit skip vetoes a pending multi-approver purchase; otherwise all positive decisions must agree and meet the configured threshold. Production rejects the development user header and requires an HMAC-signed, expiring bearer session using `RESTOCK_SESSION_SECRET`.

## Native wrappers

The same PWA is wrapped by Capacitor 8 under `ui/web/android` and `ui/web/ios`. Both native projects support the `restock://approval` callback, OS push registration, and device-bound secure session storage; payment credentials never enter local storage. Local Android and iOS Simulator builds are verified. Physical-device testing and store enrollment remain launch gates, and no store fee has been paid.

## Forecasting

EWMA remains the production baseline. Phase 13 implemented consent-gated forecast observations, category priors for cold start, export/deletion, and a dependency-free offline benchmark reporting MAE, trigger precision, missed-depletion rate, and action rate. `forecasting/datasets.json` blocks data whose training license is not authoritative; UCI Online Retail II is permitted only as a weak pipeline benchmark, not as a household-behavior model.

## Additional merchant adapters

Phase 14 implemented the official Swiggy MCP endpoints for catalog/cart work through the same quote/checkout/reconciliation contract. Swiggy's MCP can expose COD, but Restock never treats COD as a substitute for an approved Prava card payment; card checkout stays an explicit browser boundary and defaults to a disclosed simulation. Restock Teams also supports HTTPS hosted-invoice quotes and idempotent one-time disclosed checkout. Recurring Teams charging remains disabled pending Prava's standing-mandate answer.

## Operations and recovery

Every API response carries an `X-Correlation-ID`; `/metrics` reports aggregate request, error, and latency counters without user/payment fields. JSON request logs contain path/status/latency only. `scripts/retention_cleanup.py` applies `RESTOCK_RETENTION_DAYS` to old audit and resolved notification data while retaining transaction proof. `scripts/backup_restore.py` performs verified SQLite backups locally and uses `pg_dump`/`pg_restore` for operator-controlled Postgres recovery. CI runs Python tests, PWA tests/build, and a production-container build.

## Project specifications

- [Product requirements](PRD.md)
- [Technical requirements](TECHNICAL_PRD.md)
- [Build skill and canonical structure](SKILL.md)
- [Visual design system](docs/design-system.md)
