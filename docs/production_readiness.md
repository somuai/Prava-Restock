# Production readiness status

## Verified in code and CI

- Durable versioned migrations through `20260722_04`; the latest revision adds
  the unique Slack delivery outbox.
- Separate web, leased worker, and optional Slack processes.
- Tenant isolation, RBAC, signed expiring sessions, bearer-only API semantics,
  security headers, CORS allow-listing, and rate limiting.
- Code-owned caps, mandate gating, price-deviation reapproval, no substitution,
  consume-once credentials, checkout idempotency, and restart recovery.
- Sanitized audit, correlation IDs, structured request logs, and aggregate metrics.
- Configurable retention plus SQLite and Postgres backup/restore tooling.
- Local PostgreSQL production-mode proof completed against a disposable database:
  migrations through `20260719_03`, repository writes, `/ready`, custom-format
  backup, restore into a fresh database, and restored-row verification all pass.
  See [PostgreSQL evidence](postgres_evidence.md).
- React PWA and simulator-buildable Android/iOS wrappers.
- Zepto and Swiggy catalog/cart/quote adapters, plus one-time Teams invoice support;
  real merchant payment remains independently gated.
- Slack Socket Mode and WhatsApp Cloud API adapters. The private Slack app is
  installed; bot authentication, a real Socket Mode handshake, and live notification
  delivery are verified. A real Skip callback changed exactly one persisted workflow,
  and the handler removes resolved buttons to prevent repeated actions. New Teams
  notifications now enqueue one durable Slack delivery, callbacks use a dedicated
  action-limited service token, and positive decisions link only to the authenticated
  Restock PWA rather than exposing Prava approval URLs in Slack.

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
