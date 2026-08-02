# Restock × Prava review — one-page brief

**Meeting:** 3 August 2026, 9:30 a.m. IST — confirm the calendar invitation's
time zone before joining.

## Desired outcome

1. Show that Restock is a credible, production-oriented application whose core
   payment boundary depends on Prava rather than merely mentioning it.
2. Reproduce or explain the assigned sandbox card's **Security Check Failed / No
   Passkey** state and agree on the owner and resolution.
3. Confirm the production-access activation steps, allowed credentials/card,
   environment URL, and go-live test boundary.

## Product in twenty seconds

Restock notices before the user asks. It predicts that a household essential is
running out or sees that a team subscription is approaching renewal, obtains a
fresh exact-SKU or invoice quote, checks hard spend policy, and asks for an
explicit decision. Prava supplies the scoped user-approval and payment
credential boundary. Restock never stores raw card data and never silently
substitutes a product or switches a plan.

## What is verified today

| Boundary | Current evidence |
| --- | --- |
| Public product | PWA deployed with Google login, isolated reviewer access, first-run pantry onboarding, Home, Teams, Activity, and mode disclosures |
| Triggering | Deterministic depletion/date/price triggers, category cold-start priors, EWMA recalibration, duplicate suppression |
| Safety | Spend Guardrail before Prava; exact SKU; no silent substitution; price reapproval; mandate gate; idempotency; sanitized audit; restart recovery |
| Prava | Real sandbox Session creation and hosted handoff work; assigned card is provider-blocked before passkey approval |
| Zepto | Real OAuth and two saved delivery addresses verified. Product search is currently blocked by Zepto provider HTTP 429, so Restock does not claim a live search, cart, quote, or order proof yet. |
| Slack | Real private-workspace delivery and persisted Skip callback verified; persistent Railway listener active |
| Persistence | Managed Postgres, migrations, separate API/worker/Slack services, backup/restore proof |
| Quality | Latest CI green; 426 Python tests pass, one interactive case is skipped, seven integration cases are deselected by default |
| NANDA | Trigger utility is public; reusable Prava adapter PR is draft until interactive sandbox proof succeeds |

## Exact current blocker

Restock creates the hosted Prava sandbox Session. The assigned Axiom card is
accepted by the hosted page, which then shows **Security Check Failed**. On
retry, the saved card is labelled **No Passkey** and cannot be selected. No
mandate, one-time credential, merchant checkout, or real-money transaction is
claimed.

## Requests for Prava

1. Check/reset passkey eligibility for the assigned sandbox card and identify
   any enrollment, OTP, browser, or platform prerequisite.
2. Confirm the production-access decision and provide the exact activation
   checklist without exposing credentials during screen sharing.
3. Confirm whether the documented active-mandate charge endpoint is suitable
   for capped recurring Teams renewals and what terminal status reporting is
   required after each charge.

## Proof links

- App: <https://restock-offline-stub-production.up.railway.app/app/>
- Runtime truth: <https://restock-offline-stub-production.up.railway.app/capabilities>
- Repository: <https://github.com/somuai/Prava-Restock>
- NANDA utility: <https://restock-trigger-math-production.up.railway.app/skill.md>
- NANDA draft PR: <https://github.com/projnanda/nandatown/pull/208>

Never display `.env`, Railway variables, approval URLs, API keys, the complete
test card, dynamic CVV, OTP, or reviewer password during the meeting.
