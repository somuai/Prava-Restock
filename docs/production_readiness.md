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
- Zepto and Swiggy catalog/cart/quote adapters, plus one-time Teams invoice support;
  real merchant payment remains independently gated.
- Slack Socket Mode and WhatsApp Cloud API adapters. The private Slack app is
  installed; bot authentication, a real Socket Mode handshake, and live notification
  delivery are verified. The workflow-action callback still needs a persistent
  deployed listener and a real pending workflow.

## External launch gates

- Provision managed Postgres and a separate worker service. This may require paid
  hosting and therefore is not activated automatically.
- Configure permanent high-entropy session/API secrets in platform secret storage.
- Run a restore drill against a disposable managed Postgres database.
- Run the Slack listener as a persistent deployed process and verify one button
  callback against a real pending workflow. Live notification delivery is complete.
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
