# Restock

Restock is a consumption-triggered replenishment agent that predicts when recurring household essentials will run out, or when team subscriptions will renew, and prepares a bounded Prava payment flow before the deadline.

The repository contains the deterministic trigger/orchestrator foundation and a real Prava sandbox client. The merchant checkout boundary remains disclosed simulation until Phase 8 completes; see [Phase 7 evidence](docs/phase7_evidence.md) and the real-versus-simulated notes below.

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

The currently hosted URL is the credential-free Phase 6 offline deployment. The repository's local Phase 7 integration can call the real Prava sandbox when credentials are supplied through `.env`; those credentials are not committed or baked into the image.

## What is real and what is simulated

- **Real:** deterministic trigger logic, code-owned spend caps, OpenAI Agents SDK tool surface, and Prava sandbox intent/passkey/mandate integration.
- **Real merchant boundary:** Zepto OAuth/MCP client, address selection, cart preview, exact-price quote normalization, stock handling, and payment-status reconciliation interface.
- **Disclosed simulation:** final Zepto live-money charge and Restock Teams billing-portal fulfillment. Zepto publishes no merchant payment sandbox, so the final charge stays disabled unless an operator explicitly enables a compatible-card checkout.
- **Hosted URL:** still the Phase 6 offline build until the later deployment phase publishes the resumable workflow and UI.

Runtime modes are returned by `/capabilities`. The default is `HOME_MERCHANT_MODE=disclosed_mock`; `ZEPTO_REAL_PAYMENT_ENABLED=1` is an additional operator gate and is never enabled in CI.

## Workflow and persistence

Phase 9 adds a resumable database-backed state machine, Postgres-compatible SQLAlchemy repositories, an initial Alembic migration, unique active-workflow and idempotency constraints, authenticated action/resume endpoints, scheduler leases, sanitized mode-tagged audit entries, and cadence recalibration after completed Home purchases. SQLite is the zero-cost local/demo default; set `DATABASE_URL` to Postgres for a durable deployment.

Run `.venv/bin/python demo/dry_run.py --mode offline` for all five deterministic seeded workflows. Use `--mode integration --item coffee` for the explicitly interactive Prava path; it opens the short-lived approval page and never makes the live Zepto payment path automatic.

## Demo PWA and channels

The React/TypeScript PWA lives in `ui/web` and is served from `/app` in the production Docker image. Run `npm ci && npm run dev` there for local frontend development, or `npm run build` for the deployable bundle. It presents a WhatsApp-style Home surface and Slack-style Teams surface with explicit preview/sandbox/simulation badges.

- **Slack:** `channels/slack_manifest.yaml` and the Bolt Socket Mode adapter are ready for one-workspace installation. Configure `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_SIGNING_SECRET`, and `SLACK_CHANNEL_ID`; no Marketplace submission is needed for the private demo workspace.
- **WhatsApp:** the Cloud API adapter sends the three-button proactive template only after recorded opt-in. The webhook verifies Meta's HMAC signature and maps Approve/Skip actions to workflows; Adjust opens the amount UI. Configure the `WHATSAPP_*` values only in local/platform secrets.
- **Guaranteed submission path:** the PWA remains functional and visibly disclosed if Slack or Meta setup is still awaiting external approval.

No paid channel, store enrollment, hosting upgrade, or real Zepto payment is activated by repository code.

## Project specifications

- [Product requirements](PRD.md)
- [Technical requirements](TECHNICAL_PRD.md)
- [Build skill and canonical structure](SKILL.md)
