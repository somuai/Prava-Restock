# Phase 7 sandbox evidence

Phase 7 replaced the offline Prava client bodies with the documented Prava Session REST API while preserving the Phase 3 public function signatures.

## Verified locally

- Prava environment: official `https://sandbox.api.prava.space` host with an `sk_test_*` credential loaded only from `.env`.
- Interactive path: a real sandbox session was created, Prava's hosted test-card UI completed successfully, passkey approval succeeded, and `await_mandate(...)` returned an opaque credential reference.
- Recorded test result: `1 passed, 64 deselected` for the explicitly enabled interactive case.
- Credential-free suite: `59 passed, 6 deselected` on 19 July 2026.
- GitHub Actions: run `29656703976` passed on commit `b2ba971`.

The short-lived approval URL and generated one-time token/CVV were not recorded in this document or committed anywhere.

## Documented sandbox limitations

Prava currently publishes no deterministic fixtures for a rejected passkey, an expired session under clock control, or webhook delivery. Those integration cases remain explicit skips rather than simulated claims. Unit tests cover their downstream handling without calling the live sandbox.
