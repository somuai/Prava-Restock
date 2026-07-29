# Phase 14 evidence

- `MerchantAdapter` defines the common quote, checkout, and reconciliation contract.
- The Swiggy client uses Prava's published Instamart/Food/Dineout MCP endpoints.
- Real Swiggy cart totals become typed `MerchantQuote` values.
- Out-of-stock remains out-of-stock; no SKU substitution is performed.
- Swiggy MCP's possible COD path is never treated as Prava card success.
- Unattended Swiggy final payment defaults to a clearly tagged disclosed mock;
  interactive card checkout requires an explicitly confirmed browser session.
- Teams supports one-time HTTPS hosted-invoice quotes with idempotent disclosed
  payment execution.
- `TEAMS_RECURRING_ENABLED=1` still fails closed. Prava's server documentation
  was re-checked on 30 July 2026 and now publishes
  [active-mandate charging](https://docs.prava.space/api-reference/mandate-charge).
  Restock has not yet integrated or sandbox-proved that separate charge/report
  boundary, so Teams recurring charging remains disabled.
- The five-item offline run completes through merchant-specific adapters.
