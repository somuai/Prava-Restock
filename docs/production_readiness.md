# Production readiness status

This is a production-readiness inventory, not a claim that the public demo is
production-activated. The repository contains substantial pre-event work. Git
history must be used to distinguish that foundation from work completed during
the official hackathon window.

## Verified in code and CI

- Durable versioned migrations through `20260801_11`; the latest revisions add
  Google identity, waitlist leads, and the null-safe manual-renewal workflow
  boundary in addition to merchant checkout attempts, durable auth throttles,
  completion-effect recovery, and the Slack delivery outbox.
- Separate web, leased worker, and optional Slack processes.
- Tenant isolation, RBAC, signed expiring sessions, cookie-only browser
  sessions with native bearer support,
  security headers, CORS allow-listing, and rate limiting.
- Production-safe solo-owner and Google login using a short-lived signed
  session; the web PWA uses only the Secure, HttpOnly cookie while native
  wrappers may keep the bearer in device-secure storage.
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
  PostgreSQL 17 database: migrations through `20260801_11`, repository and
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

- Keep the current managed Postgres deployment migrated and provision a separate
  worker service before relying on continuous background scans. The worker may
  require paid hosting and therefore is not activated automatically.
- Configure permanent high-entropy session/API secrets in platform secret storage.
- Repeat the proven restore drill against the final disposable managed Postgres
  service before production cutover.
  Run `pg_dump`/`pg_restore` from a client whose major version is at least the
  managed server's major version; `PG_DUMP_BIN` and `PG_RESTORE_BIN` can select
  explicitly installed compatible binaries.
- Run the Slack listener as a persistent deployed process with rotated credentials.
  Live notification delivery and a persisted workflow callback are complete.
- Optional after launch: configure Meta's WhatsApp assets and complete a real
  template/webhook round trip. This is not a hackathon submission gate.
- Validate push/deep links on physical devices and enroll in stores only after approval.
- Execute any real Zepto/Swiggy payment only with an explicit operator confirmation
  and compatible real card. Default checkout remains disclosed simulation.

The public Railway service runs the current application with `demo_mode=false`
and Prava sandbox configuration present. Real money is disabled, Home and Teams
final execution remain disclosed simulation, and channel listeners are not
persistently deployed. Its live `/capabilities` response is authoritative; this
document records only the last verified snapshot.

## Truthful current matrix

| Boundary | Implemented | Public runtime |
| --- | --- | --- |
| Trigger/orchestrator/workflow | Real deterministic code and CI | Active; `demo_mode=false` |
| Prava | Real sandbox Session/passkey/polling/report-status client | Sandbox configured; no production money |
| Home catalog/cart/quote | Real-capable Zepto/Swiggy adapters | `disclosed_mock` |
| Home final payment | Operator-gated browser executor | `disclosed_mock`; real money disabled |
| Teams billing | One-time hosted-invoice adapter | Fulfillment `disclosed_mock`; recurring disabled |
| Slack | Adapter plus private-workspace delivery/callback evidence | Persistent deployed listener not activated |
| WhatsApp | Template sender and signed webhook adapter | Optional post-launch; not a submission gate |
| Native | Capacitor wrappers and simulator proof | Physical devices/stores pending |
| Persistence | SQLite local/demo; Postgres path through `20260801_11` | Public service uses durable Postgres state |
