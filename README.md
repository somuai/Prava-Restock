# Restock

Restock is a consumption-triggered replenishment agent that predicts when recurring household essentials will run out, or when team subscriptions will renew, and prepares a bounded Prava payment flow before the deadline.

The repository contains the implementation through Phase 14: deterministic triggers, the Agents SDK orchestrator, a real Prava sandbox client, durable workflows, merchant adapters, user surfaces, tenant controls, native wrappers, and the forecasting foundation. Building an integration is distinct from activating it with provider credentials or real money; see [Phase 7 evidence](docs/phase7_evidence.md), [production readiness](docs/production_readiness.md), and the runtime disclosures below.

## Offline dry run

After installing the project, run `.venv/bin/python demo/dry_run.py` to exercise all five seeded items in deterministic demo mode. The Restock Teams billing checkout and final Home merchant charge are intentional, disclosed simulations.

## Local API

Run `.venv/bin/alembic upgrade head`, then `.venv/bin/uvicorn ui.api:app --reload`. Public liveness and capability endpoints are `/health`, `/ready`, and `/capabilities`. Production serves the public waitlist from `/`; set `RESTOCK_SERVE_WAITLIST=1` to exercise that production route locally. Development may use the documented local demo token. Production supports Google Identity Services, the existing solo-owner password, or both through `RESTOCK_AUTH_MODE=google|solo|hybrid`. The runtime `/capabilities` response supplies the public Google web-client ID to the PWA, so no environment-specific OAuth identifier is baked into the frontend bundle.

After cloning, run `.venv/bin/python scripts/install_git_hooks.py` once. It
configures Git to use the tracked `.githooks/pre-commit` hook, which blocks
staged OpenAI, Prava, Slack, Meta/WhatsApp, and generic credential assignments.
The legacy `/audit-log` and `/notifications/pending` compatibility endpoints are
development-only; production clients use the user-scoped `/api/v1` equivalents.

## Authentication

Google sign-in uses the free [Google Identity Services web
flow](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)
and requests only the default OpenID profile and email claims. Restock sends
Google's short-lived ID token to `POST /api/v1/auth/google`, follows Google's
[server-side verification
guidance](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)
for its signature, issuer, audience, expiry, and verified email, and keys the
account only by Google's stable `sub` claim. Matching email addresses never
silently merge accounts. An existing signed-in owner can explicitly add Google
from the profile in hybrid mode.

One Google Cloud configuration step remains operator-owned:

1. Create an OAuth client with application type **Web application**.
2. Add the exact application origins under **Authorized JavaScript origins**:
   `http://localhost:5173` for Vite development,
   `http://127.0.0.1:8765` when using the production-style local preview, and
   the production PWA origin (scheme and hostname only) for deployment.
3. Configure the OAuth branding screen with the production homepage, the
   published `/app/privacy.html`, and `/app/terms.html`. No sensitive scopes or
   paid Google service are required.
4. Put the public `*.apps.googleusercontent.com` value in `GOOGLE_CLIENT_ID` in
   platform secrets. Do not create, store, or supply a Google client secret for
   this browser ID-token flow.
5. Set `RESTOCK_AUTH_MODE=hybrid` to keep the owner password as collapsed
   recovery access, or `google` to offer Google only. Add the production PWA
   origin to `RESTOCK_ALLOWED_ORIGINS`, run `alembic upgrade head`, and redeploy.

For `solo` or `hybrid`, `RESTOCK_SOLO_USER_ID` must identify an existing user.
Configure only its scrypt hash in `RESTOCK_SOLO_PASSWORD_HASH`; plaintext
passwords are never stored. Generate a hash interactively with
`.venv/bin/python scripts/generate_solo_password_hash.py` and put the output
directly into platform secret storage.

For a time-boxed provider review, configure all three `RESTOCK_REVIEWER_*`
variables and run `.venv/bin/python scripts/provision_reviewer.py`. This creates
a separate low-cap demo user with the five safe fixtures; it never shares the
owner account. Reviewer sessions cannot outlive the configured expiration.
Remove the three variables when the review is complete.

Successful login returns a short-lived signed session, sets the same value in a
`Secure`, `HttpOnly`, `SameSite=Lax` cookie for the same-origin PWA. The browser
uses that cookie only and does not retain the bearer in JavaScript-accessible
storage; native wrappers may retain the short-lived bearer in device-secure
storage. The cookie is deleted on sign-out. Production login attempts are
rate-limited through shared Postgres state, and the API fails closed if that
shared throttle is unavailable.

Run the scheduler as a separate process with `.venv/bin/python -m workflow.worker`. The `Procfile` keeps web and worker commands separate so multiple web replicas cannot duplicate trigger scans. Railway now runs that worker as its own leased service; `.github/workflows/production-scheduler.yml` remains a credentialed fallback for a deployment that cannot keep an always-on worker running.

## Deployment

Hosted URL: [restock-offline-stub-production.up.railway.app](https://restock-offline-stub-production.up.railway.app)

After deployment, verify every public endpoint with:

```bash
./scripts/smoke_test.sh https://restock-offline-stub-production.up.railway.app
```

The hosted API is connected to a free Neon Postgres database and Prava's
sandbox, with `demo_mode=false`. Its public `/capabilities` response remains
authoritative: Prava is sandbox-configured, merchant payment and Teams billing
remain `disclosed_mock`, real money is disabled, and channel integrations are
reported configured only after their deployed process authenticates. Secrets
are held in platform secret storage, not committed or baked into the image.

## What is real and what is simulated

- **Real:** deterministic trigger logic, code-owned spend caps, OpenAI Agents SDK tool surface, and Prava sandbox intent/passkey/mandate integration.
- **Real merchant boundary:** Zepto OAuth/MCP client, address selection, live exact-SKU price lookup, cart preview, exact-price quote normalization, stock handling, and payment-status reconciliation interface. Similar search results are rejected rather than substituted.
- **Disclosed simulation:** final Zepto live-money charge and Restock Teams billing-portal fulfillment. Zepto publishes no merchant payment sandbox, so the final charge stays disabled unless an operator explicitly enables a compatible-card checkout.
- **Hosted runtime:** the current application is published with durable
  Postgres state, password authentication, and sandbox Prava configuration.
  Real-money execution remains disabled and every unavailable boundary remains
  mode-tagged. `/capabilities` is authoritative for the running environment.

Runtime modes are returned by `/capabilities`. `HOME_MERCHANT_MODE` controls catalog/cart quoting independently from `HOME_PAYMENT_MODE`, which controls the final charge. Both default to `disclosed_mock`, so production can truthfully expose a real Zepto quote with a disclosed simulated payment. A real charge additionally requires `ZEPTO_REAL_PAYMENT_ENABLED=1`, production Prava configuration, and an allowlisted payment-browser executor; it is never enabled in CI.

## Workflow and persistence

Phase 9 implemented a resumable database-backed state machine, Postgres-compatible SQLAlchemy repositories, Alembic migrations through `20260801_11`, unique active-workflow and idempotency constraints, authenticated action/resume endpoints, scheduler leases, sanitized mode-tagged audit entries, and cadence recalibration after completed Home purchases. SQLite is the zero-cost local/demo default. The public student deployment uses Neon's free Postgres tier, so no paid database plan is required at the current scale.

Run `.venv/bin/python demo/dry_run.py --mode offline` for all five deterministic seeded workflows. Use `--mode integration --item coffee` for the explicitly interactive Prava path; it opens the short-lived approval page and never makes the live Zepto payment path automatic.

## Demo PWA and channels

The React/TypeScript PWA lives in `ui/web` and is served from `/app` in the production Docker image. Run `npm ci && npm run dev` there for local frontend development, or `npm run build` for the deployable bundle. Its Restock-owned decision inbox uses a conversational Home hierarchy and a denser Teams approval hierarchy, with explicit preview/sandbox/simulation disclosure at the affected step. Typography, color, logo usage, and interaction rules are documented in the [design system](docs/design-system.md).

The public waitlist lives in `ui/waitlist` and is served from `/`. Its
right-hand feature film is rendered from code in `ui/waitlist-video` with
Remotion, using the real Restock coffee, parcel, logo, and local fonts. It is a
silent walkthrough of one restock from detection through approval. Waitlist
emails are normalized and deduplicated in the separate `waitlist_leads` table;
joining never creates a user, login identity, Prava mandate, or payment state.
The join request only commits the lead and a welcome-email outbox entry, then
returns; it never waits on an email provider. A separate service-authenticated
welcome-email endpoint is invoked by its own free GitHub Actions schedule;
trigger scans never perform email I/O. Each small batch claims outbox rows with
expiring leases and retries each delivery at most
`RESTOCK_WAITLIST_EMAIL_MAX_ATTEMPTS` times. Email remains off
by default. To prepare Resend, set `RESTOCK_WAITLIST_EMAIL_MODE=resend`,
`RESEND_API_KEY`, and `RESTOCK_WAITLIST_FROM_EMAIL` only in deployment secret
management. Resend offers a limited free tier, but its current limits remain a
provider policy rather than a Restock guarantee, and sending to arbitrary
recipients requires a [verified sending domain](https://resend.com/docs/dashboard/domains/introduction).
No provider account or paid plan is activated by this configuration.

- **Slack:** `channels/slack_manifest.yaml` and the Bolt Socket Mode adapter are implemented, the private workspace app is installed, bot authentication and a real Socket Mode handshake pass, and live notification delivery plus a persisted Skip callback are verified. Resolved messages remove their buttons to prevent repeated actions. A deployed persistent Slack process with rotated credentials remains the activation gate; see [Slack evidence](docs/slack_evidence.md). No Marketplace submission is needed for the private demo workspace.
- **WhatsApp (optional post-launch):** the Cloud API adapter remains available, but Meta number/template/webhook activation is deliberately outside the launch and hackathon submission path. If activated later, it requires recorded opt-in; the webhook verifies Meta's HMAC signature and maps Approve/Skip actions to workflows while Adjust opens the amount UI.
- **Submission path:** the real Restock PWA is the guaranteed Home and Teams surface. It is not a mocked channel; only provider/payment steps shown inside it carry sandbox or simulation labels. Slack may supplement Teams when its persistent listener is deployed.

No paid channel, store enrollment, hosting upgrade, or real Zepto payment is activated by repository code.

The production container carries Node.js 24 and an image-local
`mcp-remote@0.1.38` bridge installed from a committed integrity lockfile. Runtime
does not include npm/npx or download executable packages; CI checks the bridge with container
networking disabled, without starting OAuth or contacting Zepto. A Railway
deployment still needs an operator-completed
Zepto OAuth/mobile-OTP session and persistent storage for
`/home/restock/.mcp-auth`; the repository does not create or embed that external
authorization.

For local live-MCP development, run `npm ci` in `merchant/mcp-runtime`; Restock
then resolves that locked repository-local binary. `MCP_REMOTE_BINARY` may point
to another absolute executable in development only. Production rejects overrides
and always uses `/opt/zepto-mcp/node_modules/.bin/mcp-remote`. The capabilities
API reports Zepto OAuth only as `unknown` or `configured_unverified`; cache
presence is not proof that provider authorization remains valid. Real-money
readiness requires a successful MCP initialize/tool call in the current process
within the short verification TTL (300 seconds by default); a later bridge,
authorization, or provider-call failure clears that proof.

## Tenants and privacy

Phase 11 implemented Household and Organization tenants, owner/admin/approver/member roles, expiring one-use invitations, tenant-scoped items, multi-approver policies, consent records, privacy export, and deletion/pseudonymization. An explicit skip vetoes a pending multi-approver purchase; otherwise all positive decisions must agree and meet the configured threshold. Production rejects the development user header and requires an HMAC-signed, expiring session using `RESTOCK_SESSION_SECRET`, carried by an HttpOnly cookie in the browser or a bearer on native clients.

## Native wrappers

The same PWA is wrapped by Capacitor 8 under `ui/web/android` and `ui/web/ios`. Both native projects support the `restock://approval` callback, OS push registration, and device-bound secure session storage; payment credentials never enter local storage. Local Android and iOS Simulator builds are verified. Physical-device testing and store enrollment remain launch gates, and no store fee has been paid.

## Forecasting

EWMA remains the production baseline. Phase 13 implemented consent-gated forecast observations, category priors for cold start, export/deletion, and a dependency-free offline benchmark reporting MAE, trigger precision, missed-depletion rate, and action rate. `forecasting/datasets.json` blocks data whose training license is not authoritative; UCI Online Retail II is permitted only as a weak pipeline benchmark, not as a household-behavior model.

## Additional merchant adapters

Phase 14 implemented the official Swiggy MCP endpoints for catalog/cart work through the same quote/checkout/reconciliation contract. Swiggy's MCP can expose COD, but Restock never treats COD as a substitute for an approved Prava card payment; card checkout stays an explicit browser boundary and defaults to a disclosed simulation. Restock Teams also supports HTTPS hosted-invoice quotes and idempotent one-time disclosed checkout. Prava now documents an authenticated [Charge a Mandate](https://docs.prava.space/api-reference/mandate-charge) REST endpoint with idempotency and merchant/cap enforcement. Restock has not yet integrated or sandbox-proved that endpoint, so recurring Teams charging remains disabled until that separate boundary is implemented and tested.

## Operations and recovery

Every API response carries an `X-Correlation-ID`; `/metrics` reports aggregate request, error, and latency counters without user/payment fields. JSON request logs contain path/status/latency only. `scripts/retention_cleanup.py` applies `RESTOCK_RETENTION_DAYS` to old audit and resolved notification data while retaining transaction proof. `scripts/backup_restore.py` performs verified SQLite backups locally and uses `pg_dump`/`pg_restore` for operator-controlled Postgres recovery. CI runs Python tests, PWA tests/build, and a production-container build.

## Project specifications

- [Product requirements](PRD.md)
- [Technical requirements](TECHNICAL_PRD.md)
- [Build skill and canonical structure](SKILL.md)
- [Visual design system](docs/design-system.md)
