# Prava meeting follow-up template

**Subject:** Restock × Prava review — agreed sandbox and production-access actions

Hi [name],

Thank you for reviewing Restock today. My understanding of the agreed outcome is:

## Confirmed

- [Confirmed platform/API fact]
- [Confirmed sandbox/passkey requirement]
- [Confirmed production-access status and effective date]
- [Confirmed merchant or recurring-mandate boundary]

## Actions

| Action | Owner | Target time | Evidence/response needed |
| --- | --- | --- | --- |
| Check/reset passkey eligibility for the assigned sandbox card | Prava — [name] | [time] | Confirmation or corrected enrollment steps |
| Retry one controlled sandbox Session | Soumyajit | After Prava confirmation | Session ID and terminal status only; no secrets |
| Complete production-access activation | Prava — [name] | [time] | Dashboard status and official activation instructions |
| Run production readiness checks without a merchant charge | Soumyajit | After access | `/capabilities`, auth, Session creation, and status-report checks |
| Authorize one low-value live merchant proof | Soumyajit + Prava | Separate explicit approval | Budget, compatible card, merchant/SKU, rollback plan |

## Current sandbox evidence

Restock creates the hosted sandbox Session. The currently assigned card reaches
**Security Check Failed** and then appears as **No Passkey** on retry, so Restock
does not claim mandate approval, a one-time credential, merchant checkout, or a
real-money transaction.

Public review links:

- App: <https://restock-offline-stub-production.up.railway.app/app/>
- Runtime capabilities: <https://restock-offline-stub-production.up.railway.app/capabilities>
- Repository: <https://github.com/somuai/Prava-Restock>
- NANDA draft PR: <https://github.com/projnanda/nandatown/pull/208>

The temporary reviewer credential and any provider identifiers will be shared
only through the existing private channel, never in the repository or a public
issue.

Please reply if any item above differs from your understanding.

Best,

Soumyajit
