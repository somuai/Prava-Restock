# Provider activation runbook — 2 August 2026

This runbook contains only the steps that require credentials or access that
Prava and Linq have said will arrive on 2 August. The application, managed
database, API, leased worker, Slack listener, NANDA adapter, and deterministic
safety gates are already prepared. Never paste provider credentials into chat,
source control, command history, screenshots, or CI logs.

## 1. Prava production access

1. Create or reveal the production key in Prava's dashboard and put it directly
   into Railway secret management as `PRAVA_API_KEY` on the API service only.
2. Set `PRAVA_API_URL=https://api.prava.space`. Remove the sandbox URL from the
   production API service so there is only one authoritative host.
3. Keep `PRAVA_PRODUCTION_ENABLED` unset while checking configuration. Confirm
   the key has the `sk_live_` prefix and that `/ready` fails closed with
   `PRAVA_PRODUCTION_GATE_REQUIRED` rather than making a request.
4. After the operator accepts a maximum test amount, set
   `PRAVA_PRODUCTION_ENABLED=1`, redeploy the API, and create one low-value
   production Session. Complete the hosted card/passkey step personally.
5. Use the exact, current merchant quote. Do not enable final Zepto payment
   until the compatible-card and controlled-purchase boundary is available.
6. On every terminal merchant outcome, call Prava report-status. On an ambiguous
   result, reconcile before retrying. Never create a replacement Session
   silently.
7. Confirm `/capabilities` changes from `sandbox_configured` to
   `production_configured` while `real_money_enabled` stays false until every
   merchant runtime gate is also deliberately enabled.

Rollback: unset `PRAVA_PRODUCTION_ENABLED`, restore the sandbox key/host only if
the demo needs sandbox mode, redeploy, and verify `/capabilities` before another
run.

## 2. Linq access

The repository currently contains no Linq adapter because no authoritative
SDK/API contract, endpoint, credential shape, or granted scope has been
provided. When access arrives:

1. Save the original documentation URL and granted scopes in the evidence log.
2. Identify whether Linq is read-only discovery, browser execution, merchant
   checkout, or another boundary. Do not infer this from its name.
3. Add a small adapter behind an existing Restock interface. Keep Linq-specific
   objects out of workflow state and do not bypass the quote, approval,
   idempotency, or mandate gates.
4. Put its secret directly in local/Railway secret management, register an
   opt-in integration marker, and add deterministic transport tests before the
   first live call.
5. Run one narrow live proof, record only non-secret request IDs and outcomes,
   and tag every audit entry with its real/sandbox/simulated execution mode.

If the supplied contract cannot preserve Restock's exact-SKU, explicit-
approval, and no-credential-storage rules, leave Linq disabled and disclose the
reason instead of weakening the workflow.

## 3. NANDA Town final proof

From `nanda_prava_adapter`, load the sandbox key directly from local secret
storage and run:

```bash
NANDA_PRAVA_INTERACTIVE=1 uv run pytest -m live -s
```

Open the printed short-lived Prava URL, enter the team-issued sandbox test card,
and complete passkey approval. The test must finish with one confirmed NANDA
receipt and a successful Prava status report. It proves a Prava sandbox flow,
not a real merchant charge.

After it passes:

1. Add the sanitized result and date to the draft pull request.
2. Mark <https://github.com/projnanda/nandatown/pull/208> ready for review.
3. Attach the pull request and the live trigger-math service to the Devfolio
   submission.

## 4. Zepto final activation

Zepto OAuth and saved-address discovery are healthy. The catalog/cart/quote
proof already exists. To move beyond it, bind each tracked item to the exact
location-specific product variant and a saved address; placeholder starter SKUs
must never reach checkout. Keep automatic 429 handling read-only. A real order
requires an explicit operator-set maximum amount and final confirmation.

## 5. Post-activation checks

Run, in order:

```bash
.venv/bin/python -m pytest -q
cd ui/web && npm test -- --run && npm run build
./scripts/smoke_test.sh https://restock-offline-stub-production.up.railway.app
gh run list --limit 3
```

Then inspect `/ready`, `/capabilities`, the Slack listener logs, the worker logs,
and one sanitized audit trail. A provider being configured is not proof that a
transaction occurred; the capability matrix and submission must preserve that
distinction.
