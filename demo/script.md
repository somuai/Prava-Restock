# Restock five-minute demo script

Target length: 4 minutes 30 seconds. Keep the PWA, terminal trace, Prava approval page, and audit panel pre-opened. Never show `.env`, tokens, payment credentials, or personal Zepto address details.

## 0:00–0:35 — Hook

“Most shopping agents wait for you to remember what you need. Restock notices first. It predicts a household item running out or sees a team renewal approaching, proposes a bounded purchase, and cannot charge until the user approves a scoped Prava mandate.”

Show the Home/Teams tabs and point out the current sandbox and disclosed-mock badges.

## 0:35–2:15 — Restock Home

1. Reset the demo and show the coffee trigger: depletion in two days and price below threshold, combined into one proactive message.
2. Open the real Zepto evidence: OAuth, product search, reversible cart, exact `confirmOrder=false` quote. State clearly that no Zepto merchant payment sandbox exists.
3. Tap Approve. Open the real Prava sandbox page and complete the documented test-card/passkey flow.
4. Return to the PWA. Show `completed`, with the final Zepto live-money step labeled `disclosed_mock`.
5. Briefly show that any price increase, or a decrease greater than 15%, requires reapproval; then show the out-of-stock path creating no transaction.

## 2:15–3:25 — Restock Teams

1. Switch to Teams. Show the renewal notification in the Slack-style surface or real private Slack workspace when configured.
2. Explain that the cheaper plan is proposed but never selected automatically.
3. Tap the explicit Switch plan action and show the same Prava approval boundary.
4. State that Prava documents recurring mandate charging, but Restock has not integrated or sandbox-proved that separate boundary. The demo therefore uses the real hosted-link/manual-required decision workflow and labels vendor fulfillment as disclosed simulation.

## 3:25–4:10 — Safety proof

Show the automated tests and name the invariants:

- Spend-cap rejection before Prava.
- No checkout without an approved mandate.
- Rejected/expired mandates create zero transactions.
- Idempotency prevents double checkout.
- Duplicate active workflows are suppressed.
- Payment secrets and approval URLs are rejected from durable audit storage.

## 4:10–4:30 — Close

Open the audit panel: “Every state says whether it was real, sandbox, or simulated. Restock is not a shopping chatbot. It is a proactive, cross-merchant approval system that is honest about every payment boundary.”

End on the architecture/real-versus-simulated README matrix and hosted URL.
