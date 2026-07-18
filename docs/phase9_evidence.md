# Phase 9 workflow evidence

Phase 9 replaces the synchronous all-in-one demo path with a resumable, database-backed state machine while preserving the Agents SDK as the proposal/tool-selection layer.

## Implemented

- Postgres-compatible SQLAlchemy schema and initial Alembic migration.
- Durable users, tracked items, workflow runs, notifications/actions, transactions, audit entries, and scheduler leases.
- Unique active workflow per item and unique checkout idempotency key.
- Explicit currency on items, intents, workflow proposals, and transactions.
- Authenticated `/api/v1` item, workflow, notification, action, resume, and audit endpoints.
- Code-owned approval, explicit Teams switch, price-reapproval, no-substitution, idempotency, and terminal mandate behavior.
- Consume-once payment credentials remain outside durable storage.
- EWMA cadence update occurs only after a completed Home checkout.
- Separate web and worker process commands.

## Verification

- All five seeded items complete through the deterministic cross-component workflow test.
- A repository reopened against the same database retains all five workflows.
- Rejected and expired mandates create no transactions.
- Duplicate triggers are rejected while a workflow is active.
- A greater-than-15% price change reaches `reapproval_required` before checkout.
- Audit serialization contains mode tags and no credential, card, approval-URL, or dynamic-CVV fields.
- The initial migration upgrades a fresh SQLite database to revision `20260719_01`.

The one live interactive Prava approval and live Zepto quote proofs remain recorded separately in the Phase 7 and Phase 8 evidence files; CI does not repeat human passkey/OTP steps.
