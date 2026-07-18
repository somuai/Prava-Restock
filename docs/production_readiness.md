# Production readiness status

## Verified in code and CI

- Durable versioned migrations through `20260719_03`.
- Separate web, leased worker, and optional Slack processes.
- Tenant isolation, RBAC, signed expiring sessions, bearer-only API semantics,
  security headers, CORS allow-listing, and rate limiting.
- Code-owned caps, mandate gating, price-deviation reapproval, no substitution,
  consume-once credentials, checkout idempotency, and restart recovery.
- Sanitized audit, correlation IDs, structured request logs, and aggregate metrics.
- Configurable retention plus SQLite and Postgres backup/restore tooling.
- React PWA and simulator-buildable Android/iOS wrappers.

## External launch gates

- Provision managed Postgres and a separate worker service. This may require paid
  hosting and therefore is not activated automatically.
- Configure permanent high-entropy session/API secrets in platform secret storage.
- Run a restore drill against a disposable managed Postgres database.
- Install the Slack app and configure Meta's WhatsApp test/production assets.
- Validate push/deep links on physical devices and enroll in stores only after approval.
- Execute any real Zepto/Swiggy payment only with an explicit operator confirmation
  and compatible real card. Default checkout remains disclosed simulation.

The public Railway service is a credential-free demo deployment until those gates are
completed. Its `/capabilities` response is the authoritative runtime disclosure.
