# Native release checklist

## Shared application

- Bundle ID: `space.prava.restock`
- Deep-link callback: `restock://approval?run_id=<opaque workflow id>`
- Session bearer tokens are stored in iOS Keychain or Android AES-GCM/Keystore.
- Payment credentials, CVV, approval URLs, and card data are never stored locally.
- Push registration requests permission at runtime; provider credentials remain external secrets.

## Store listing draft

**Name:** Restock — proactive replenishment

**Short description:** Restock notices likely depletion or renewal dates, asks for explicit approval, and records every step before a scoped purchase.

**Privacy disclosure:** account identity, tracked-item preferences, notification actions,
purchase/audit history, and optional forecasting signals are processed to provide the
service. Raw card data and CVV are never collected by Restock. Forecasting is opt-in
and export/deletion controls are available.

## External gates

- Test deep links and push notifications on one physical Android and one physical iOS device.
- Provide APNs/Firebase configuration through platform secret files (ignored by Git).
- Complete store privacy questionnaires and screenshots.
- Purchase Apple ($99/year) or Google Play ($25 once) enrollment only after explicit approval.
- No enrollment or store submission has been performed by this repository work.
