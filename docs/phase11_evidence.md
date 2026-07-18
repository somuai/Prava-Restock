# Phase 11 evidence

- Household and Organization tenants persist independently of users.
- Memberships support owner, admin, approver, and member roles.
- Invitations are expiring, consume-once, and store only a token hash.
- Item reads require active tenant membership; cross-tenant denial is tested.
- Multi-approver conflict policy is deterministic: skip vetoes while pending;
  matching positive decisions must meet the configured threshold.
- Forecasting consent is separately recorded and revocable.
- Privacy export and deletion/pseudonymization paths are implemented.
- Production never trusts `X-Restock-User`; it requires a signed expiring session.
- Alembic revision `20260719_02` upgrades a frozen revision-one database.
