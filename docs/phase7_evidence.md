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

## Official-window API-contract recheck — 1 August 2026

The compatibility wrapper previously ignored its configured request timeout
after the Session transport was extracted. A regression test now proves that a
60-second timeout reaches the HTTP transport, while invalid, boolean, and
non-finite timeout values are rejected before a network call.

At `2026-08-01T05:09:36Z`, the isolated invalid-credential sandbox test reached
the official sandbox with a deliberately invalid test credential and waited the
full forwarded 60 seconds. The server did not return the documented HTTP 401
`AUTH_1001`/`AUTH_1002` response; the client received a socket read timeout.
This is recorded as a Prava sandbox contract failure or outage, not as a passing
authentication-rejection test. No card, passkey, merchant checkout, or real-money
operation was involved in this recheck.
