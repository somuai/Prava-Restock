# Phase 7 sandbox evidence

Phase 7 replaced the offline Prava client bodies with the documented Prava Session REST API while preserving the Phase 3 public function signatures.

## Verified locally

- Prava environment: official `https://sandbox.api.prava.space` host with an `sk_test_*` credential loaded only from `.env`.
- Interactive session creation is verified: Restock creates a real hosted Prava sandbox session using the assigned test credential, without recording the short-lived approval URL or any payment credential.
- Credential-free suite: `59 passed, 6 deselected` on 19 July 2026.
- GitHub Actions: run `29656703976` passed on commit `b2ba971`.

The short-lived approval URL and any generated one-time token/CVV are not
recorded in this document or committed anywhere.

## Current interactive sandbox status — 2 August 2026

With the team-assigned Axiom test card, the hosted page accepted the card and
then showed **Security Check Failed**. Retrying displayed the saved card as
**No Passkey**, leaving card selection disabled. The session therefore did
**not** reach mandate approval and `await_mandate(...)` did not return a
credential reference. No merchant checkout or real-money operation occurred.

This is an active Prava sandbox/passkey-provisioning blocker and must not be
presented as a completed end-to-end sandbox proof. The provider has been asked
to check or reset passkey eligibility for the assigned card and to clarify any
required enrollment or OTP step.

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
