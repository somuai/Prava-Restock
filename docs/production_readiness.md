# Production readiness status

This is a production-readiness inventory, not a claim that the public demo is
production-activated. The repository contains substantial pre-event work. Git
history must be used to distinguish that foundation from work completed during
the official hackathon window.

## Verified in code and CI

- Durable versioned migrations through `20260722_07`; the latest revisions add
  merchant checkout attempts, durable auth throttles, and completion-effect
  recovery in addition to the Slack delivery outbox.
- Separate web, leased worker, and optional Slack processes.
- Tenant isolation, RBAC, signed expiring sessions, bearer-only API semantics,
  security headers, CORS allow-listing, and rate limiting.
- Production-safe solo-owner login using a configured scrypt password hash and
  short-lived signed session; the web PWA keeps the session in session storage only.
  Login-attempt windows are durable in PostgreSQL and serialized across replicas.
- The spend-cap policy is enforced by an Agents SDK tool-input Guardrail before
  Prava Session creation.
- Mandate gating, price-deviation reapproval, exact-SKU/no-substitution,
  consume-once credentials, checkout idempotency, and restart recovery have
  deterministic implementation and test coverage. They remain subject to the
  current Phase 8 live merchant-boundary proof and are not additional SDK
  Guardrails.
- Sanitized audit, correlation IDs, structured request logs, and aggregate metrics.
- Configurable retention plus SQLite and Postgres backup/restore tooling.
- Local PostgreSQL production-mode proof completed against a disposable
  PostgreSQL 17 database: migrations through `20260722_07`, repository and
  recovery behavior, `/ready`, lease fencing, custom-format backup, restore into
  a fresh database, and restored-row verification pass.
  See [PostgreSQL evidence](postgres_evidence.md).
- React PWA and simulator-built Android/iOS wrappers. Physical-device behavior
  and store publication are not verified.
- Zepto and Swiggy catalog/cart/quote adapters, plus one-time Teams invoice support;
  real merchant payment remains independently gated.
- Slack Socket Mode and WhatsApp Cloud API adapters. The private Slack app is
  installed; bot authentication, a real Socket Mode handshake, and live notification
  delivery are verified. A real Skip callback changed exactly one persisted workflow,
  and the handler removes resolved buttons to prevent repeated actions. New Teams
  notifications now enqueue one durable Slack delivery, callbacks use a dedicated
  action-limited service token, and positive decisions link only to the authenticated
  Restock PWA rather than exposing Prava approval URLs in Slack.

Meta does not provide a confirmed 1–2 week business-verification SLA. Its
published template-review guidance may take up to 24 hours; production
number/business approval remains provider-controlled.

## External launch gates

- Provision managed Postgres and a separate worker service. This may require paid
  hosting and therefore is not activated automatically.
- Configure permanent high-entropy session/API secrets in platform secret storage.
- Repeat the proven restore drill against the final disposable managed Postgres
  service before production cutover.
  Run `pg_dump`/`pg_restore` from a client whose major version is at least the
  managed server's major version; `PG_DUMP_BIN` and `PG_RESTORE_BIN` can select
  explicitly installed compatible binaries.
- Run the Slack listener as a persistent deployed process with rotated credentials.
  Live notification delivery and a persisted workflow callback are complete.
- Configure Meta's WhatsApp test/production assets and complete a real template/webhook
  round trip.
- Validate push/deep links on physical devices and enroll in stores only after approval.
- Execute any real Zepto/Swiggy payment only with an explicit operator confirmation
  and compatible real card. Default checkout remains disclosed simulation.

The public Railway service runs the current application, but it is a credential-free,
unactivated demo runtime until those gates are completed. Its `/capabilities` response
is the authoritative disclosure and currently reports `demo_mode=true`, real money
disabled, Prava sandbox unconfigured, channel integrations unconfigured, and merchant
and billing execution as disclosed simulation.

## Truthful current matrix

| Boundary | Implemented | Public runtime |
| --- | --- | --- |
| Trigger/orchestrator/workflow | Real deterministic code and CI | Demo mode |
| Prava | Real sandbox Session/passkey/polling/report-status client | `sandbox_unconfigured` |
| Home catalog/cart/quote | Real-capable Zepto/Swiggy adapters | `disclosed_mock` |
| Home final payment | Operator-gated browser executor | `disclosed_mock`; real money disabled |
| Teams billing | One-time hosted-invoice adapter | Fulfillment `disclosed_mock`; recurring disabled |
| Slack | Adapter plus private-workspace delivery/callback evidence | Persistent deployed listener not activated |
| WhatsApp | Template sender and signed webhook adapter | Meta assets and provider activation pending |
| Native | Capacitor wrappers and simulator proof | Physical devices/stores pending |
| Persistence | SQLite local/demo; Postgres path through `20260722_07` | Public service remains unactivated demo |
