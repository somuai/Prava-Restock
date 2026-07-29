---
name: restock-agent
description: >
  Build, scaffold, extend, fix, test, and deploy Restock — an autonomous,
  consumption-triggered replenishment agent built on Prava for the Prava
  Agentic Commerce Hackathon (Jul 31 - Aug 2, 2026). Use this skill whenever
  the user asks to build any part of Restock: the consumption tracker, the
  OpenAI Agents SDK orchestrator, the Prava intent/passkey/mandate flow, the
  Zepto/Swiggy MCP merchant checkout, the proactive notification UI, or the
  Restock Teams (B2B) variant. Also trigger for: "build the consumption
  tracker", "wire up Prava", "set up the Zepto MCP skill", "build the
  orchestrator agent", "write the depletion forecast", "build the passkey
  approval flow", "fix the mandate flow", "deploy the demo", or any task
  referencing Restock, Auto-Buy, depletion prediction, Prava intents/mandates,
  or this hackathon's judging criteria. ALWAYS use this skill before writing
  any code — do not build from memory or the PRD alone. This skill contains
  the canonical file structure, the payment-flow sequencing, the disclosed
  merchant-payment boundary, and the pre-submission
  checklist.
---

# Restock — Hackathon Build Skill

## What this skill is for

Use this whenever building, fixing, or extending any part of **Restock**: an agent
that predicts when a recurring consumable will run out and autonomously buys a
replacement through Prava before that happens — no chat request required.

**Read the companion `PRD.md` for product rationale.** This file is the *build spec* —
it tells you what to actually implement and in what order.

**Never invent Prava API names from memory.** Restock's implemented server flow
is Session → passkey → payment-result polling → one-time credential → report
status. `Intent` is Restock's internal proposal record, not a second Prava
object. Before changing payment integration code, fetch:

- `https://docs.prava.space/llms.txt` (documentation index)
- The `prava-sdk-integration` and `prava-pay` skill folders in
  `github.com/Prava-Payments/prava-skills` (session API reference and
  test/sandbox data; Prava does not publish a Python SDK for this server path)
- The `prava-merchants-checkout/zepto-prava-skill` or `swiggy-prava-skill`
  folder in the same repo for the exact merchant checkout wiring

Point your coding agent at that repo directly and ask it to "integrate Prava
payments using the SDK skill" — that repo is designed to be consumed this way.

---

## 1. Problem statement (exact)

Build a working product where an AI agent **discovers, decides, and completes a
transaction using Prava** — specifically, one that fires **without the user asking
in the moment**, triggered by a predicted depletion date for a recurring household
or office consumable.

### Hard requirements (hackathon rules)

- Must use Prava as a **real part of the product** — not just called once for show.
- Must demonstrate an **agent completing or enabling a transaction**.
- Meaningful work must be completed **during** the 48-hour window — disclose anything
  that pre-existed the event.
- Submission must show a working flow, explain the user and problem, and (per the
  rules) be a product that "could live beyond the hackathon."

### Submission window

**Jul 31 – Aug 2, 2026**, 48 hours, online. Apply on Devfolio (rolling review, 3-day
RSVP window after acceptance) — do this before anything else if not already done.

Restock has a substantial production-oriented pre-event foundation. Git history
is the disclosure record. Never present that foundation as official-window work;
identify exactly what is newly completed during the judged window and keep every
simulated or provider-unactivated boundary visible.

---

## 2. Judging breakdown → build priorities

| Judged on | Weight in your build time | What to actually do |
|---|---|---|
| Does it work | Highest | Re-prove one real Prava sandbox Session/passkey/credential flow and its truthfully disclosed merchant result before polishing |
| Meaningful agent action | High | The purchase must be agent-initiated on a predicted condition, not a user-typed "buy X" |
| Handles payment clearly | High | Spend caps and the approve/adjust/skip step must be visually obvious in the demo |
| Solves a clear problem | Medium | One clean, well-narrated user story beats five half-built features |
| Could become a real product | Medium | Keep the audit/savings log — it's your "this isn't a toy" signal |
| OpenAI usage | Medium | Use the **Agents SDK** (code-first). Do not build on Agent Builder — OpenAI deprecated it June 3, 2026, shutting down Nov 30, 2026 |
| Prava integration depth | Medium | Reuse Prava's own published merchant skills rather than reinventing checkout |
| Startup potential / consumer / B2B | Lower, but free | The Home/Teams dual-skin costs little extra and covers two award categories at once |

**Sequencing rule:** payment flow first, forecasting logic second, UI polish third,
B2B skin last (only if time remains). A solo builder who nails the Prava flow with a
dumb day-counter beats a team with a clever forecasting model and a broken checkout.

---

## 3. Canonical file structure

```
restock/
├── README.md                       ← what judges read first
├── PRD.md                          ← product rationale (already provided)
├── SKILL.md                        ← this file
├── .env.example
├── package.json / pyproject.toml   ← pick one stack, don't mix
├── agent/
│   ├── orchestrator.py             ← OpenAI Agents SDK loop, trigger-type-agnostic
│   ├── tools.py                    ← tool defs: check_trigger_status, request_prava_intent,
│   │                                  complete_merchant_checkout, log_transaction
│   └── system_prompt.md            ← orchestrator's instructions
├── triggers/
│   ├── consumption_model.py        ← predicted trigger, Restock Home (see §5)
│   ├── renewal_model.py            ← known-date trigger, Restock Teams (see §10)
│   └── seed_data.json              ← 3-5 Home SKUs + 1 Teams subscription, seeded
├── payments/
│   ├── prava_client.py             ← Session REST API, polling, report-status
│   └── mandate_flow.py             ← approval handoff and credential normalization
├── merchant/
│   ├── zepto_checkout.py           ← exact-SKU MCP quote/cart adapter
│   ├── swiggy_checkout.py          ← second merchant adapter
│   ├── browser_checkout.py         ← separate Playwright payment boundary
│   ├── payment_executor.py         ← consume-once credential executor
│   └── saas_invoice_checkout.py    ← one-time Teams invoice adapter
├── storage/
│   ├── schema.py                   ← production database schema
│   ├── repository.py               ← durable workflow repository
│   └── migrations/                 ← Alembic chain through 20260722_07
├── workflow/
│   ├── service.py                  ← resumable state machine
│   └── worker.py                   ← leased scheduler process
├── channels/
│   ├── slack_app.py                ← Bolt/Socket Mode adapter
│   └── whatsapp.py                 ← Cloud API template/webhook adapter
├── ui/
│   └── web/                        ← PWA plus Capacitor Android/iOS wrappers
├── logs/
│   └── restock.db                  ← ignored SQLite local/demo state
└── demo/
    ├── script.md                   ← the 5-minute submission video script
    └── seed_reset.py                ← resets demo state between run-throughs
```

---

## 4. Prava integration — implemented Session flow

Prava's implemented server flow is: **Session → Passkey → payment-result
polling → one-time credential → merchant attempt → report status.**

```
1. Merchant/session setup (server-side): create a session describing the order
   (merchant identity, amount, item description).
2. User enrollment (one-time, during onboarding): user connects a card/wallet
   and sets up a passkey via the Prava SDK/dashboard flow.
3. Restock creates its internal purchase Intent and a Prava SESSION specifying
   merchant, amount, and constraints.
4. User authenticates the Session via PASSKEY (Face ID / Touch ID / platform
   equivalent). In the hackathon demo, this is the approve/adjust/skip UI moment.
5. Restock polls Prava until the one-time credential is available, rejected,
   expired, or timed out. There is no mandate webhook.
6. Merchant MCP prepares and revalidates the exact cart. The short-lived token,
   dynamic CVV, and expiry temporarily enter only the consume-once server-side
   Playwright boundary; they are never logged or persisted.
7. Reconcile the merchant result and call Prava report-status on both success
   and failure.
```

**Implementation instructions for whoever builds this:**

- Keep API details isolated in `payments/prava_client.py` and re-check the
  current Prava Session docs before changing them.
- Use their **sandbox test cards / test data** (documented in that same skill
  folder under `test-data.md`) for all development — never use a real card
  until the flow is fully verified.
- Build the intent-creation call as a function the orchestrator agent can call
  as a tool (`request_prava_intent(merchant, amount, item, constraints)`), not
  as inline code in the orchestrator's prompt — keeps it testable in isolation.
- Re-prove this flow at the start of the official window before claiming any
  newly judged merchant or UI work.

---

## 5. Consumption tracker (keep this deliberately simple)

Do **not** build a real time-series forecasting model for the hackathon. A simple
countdown with a confirm-and-recalibrate loop is enough to demo the concept
convincingly and leaves your clock free for the payment flow.

```python
# tracker/consumption_model.py — sketch, not final code
from dataclasses import dataclass
from datetime import date, timedelta

@dataclass
class ConsumableItem:
    name: str
    merchant_sku_id: str
    merchant_address_ref: str  # opaque saved-address ID; never raw address/phone
    quantity: int              # positive exact cart quantity
    typical_cadence_days: float   # user-reported starting estimate
    last_purchased: date
    price_estimate: float

    def predicted_depletion_date(self) -> date:
        return self.last_purchased + timedelta(days=self.typical_cadence_days)

    def days_until_depletion(self, today: date) -> int:
        return (self.predicted_depletion_date() - today).days

    def recalibrate(self, actual_days_elapsed: int, smoothing: float = 0.3):
        # exponential smoothing toward the observed cadence — nothing fancier needed
        self.typical_cadence_days = (
            smoothing * actual_days_elapsed
            + (1 - smoothing) * self.typical_cadence_days
        )
```

For a real Home quote, resolve the exact SKU and quantity against the opaque
saved-address reference, then preview the exact cart. Supply the merchant device
ID from `ZEPTO_DEVICE_ID` at runtime only; never persist it on an item or include
it in logs. Keep the merchant client injected so the default test path remains
offline and deterministic.

Trigger rule for the orchestrator: when `days_until_depletion <= 2`, fire the
proactive-purchase flow. Recalibrate `typical_cadence_days` every time an item is
actually reordered (whether autonomously or manually).

**Stretch goal only if the payment flow and demo are both solid with time to spare:**
add a price-threshold trigger alongside the depletion trigger (buy on whichever
fires first) — this is the detail that lets you say, truthfully, that Restock does
more than Amazon's single-signal AutoBuy.

---

## 6. Orchestrator agent (OpenAI Agents SDK)

Build this as a small, tool-using loop — not a chatbot waiting for input. It runs
on a schedule (or a simulated clock tick for the demo) and checks every tracked
item's depletion status.

Use **`gpt-5.4-mini` as the single model for the entire loop**, including proactive
notification copy and the Restock Teams renew-vs-switch comparison. Do not add a
premium-model branch for those calls: the single verified model removes a live-demo
quota failure mode, while spend limits, substitution rules, and plan-switch approval
remain bounded by code-owned policies and human-in-the-loop controls. Spend
caps are the Agents SDK tool-input Guardrail; exact-SKU substitution refusal,
price-deviation reapproval, and plan-switch rules are deterministic workflow
checks whose live merchant-boundary proof remains Phase 8 work.

**Tools to define:**

- `check_depletion_status()` → returns items within the trigger window
- `request_prava_intent(merchant, amount, item, constraints)` → §4
- `await_passkey_approval(intent_id)` → returns approved / adjusted / skipped
- `complete_merchant_checkout(credential, merchant, item)` → §6 merchant call
- `log_transaction(item, amount, merchant, timestamp)` → append to audit log
- `notify_user(message, actions=["approve","adjust","skip"])` → the proactive
  push that's the whole point of the demo

**System prompt shape** (put the real one in `agent/system_prompt.md`, not inline
in code):
> You are Restock, an agent that watches recurring household or office essentials
> and reorders them before they run out. You never wait to be asked. Before every
> purchase, you must present the item, quantity, merchant, and amount, and get
> explicit approval through the passkey flow — you never spend outside the
> per-item or monthly caps the user set. If an item is out of stock or the price
> has moved meaningfully from the last purchase, ask before proceeding instead of
> substituting silently.

Do **not** build this on OpenAI's Agent Builder (deprecated June 2026, shuts down
Nov 30, 2026). Use the code-first Agents SDK so the submission isn't demoing
something OpenAI is actively winding down.

---

## 7. Merchant execution — MCP cart plus browser payment boundary

Prava publishes merchant skills at
`github.com/Prava-Payments/prava-skills/tree/main/prava-merchants-checkout/`,
including `swiggy-prava-skill` and (per their skill index) a Zepto MCP
configuration. Use them for catalog/cart/order operations. They do not replace
the separate Playwright card-form boundary.

**Audit log:** every transition writes a sanitized, mode-tagged domain event.
SQLite is the local/demo store; the production path uses Postgres-compatible
repositories and Alembic migrations through `20260722_07`. The user-facing
audit/savings feed is the receipt trail, not just a chat transcript.

---

## 8. Fallback plan if a real payment step fails during testing

Zepto/Swiggy sandbox merchant access is confirmed: Prava's Shubham Kukreti
stated via Discord on 17 July 2026, "Merchants aren't restricted, so you can
build flows for things like Zepto or Swiggy." Fall back to the disclosed mock
only if a real payment step fails during testing for a reason unrelated to this
confirmed merchant access, such as card constraints or an unexpected sandbox
error:

- Use the implemented `merchant/mock_checkout.py` boundary: a clearly labeled,
  durable and idempotent simulation for only the final live-money merchant step.
  Prava sandbox approval and Zepto catalog/cart/quote operations remain real.
- Configure and disclose catalog/quote mode independently from final-payment
  mode; a real Zepto quote must not be mislabeled because payment remains
  `disclosed_mock`.
- State this explicitly in the submission write-up. The hackathon rules ask you
  to disclose what's simulated — do this rather than let a judge discover it.
- This does not weaken the "meaningful agent action" or "handles payment
  clearly" criteria, since the Prava mandate flow itself is still real.

**Browser automation boundary:** Prava confirmed that no merchant has MCP
support for the payment-form step (entering card number, CVV, expiry, and
clicking Pay). This step is implemented as browser automation using Playwright
(`merchant/browser_checkout.py`). Because this depends on the merchant's real,
unversioned checkout DOM, automation failures (selector not found, page-
structure change) are caught distinctly from expected payment declines and
logged as automation failures, not payment failures. If browser automation
proves too fragile within the hackathon's time budget, the accepted fallback
is a clearly disclosed simulated/recorded version of this step — same
disclosure standard as every other mock in this project.

---

## 9. UI / demo surface

Build two disclosed mocked surfaces matching the primary channels defined in
`PRD.md` §10, "Distribution and surface":

- **Restock Home:** a WhatsApp-style conversation with a proactive message and
  interactive approve/adjust/skip controls.
- **Restock Teams:** a Slack-style billing notification and approval surface.

Keep both PWA surfaces available as the guaranteed demo path. The Slack
Bolt/Socket Mode adapter and WhatsApp Cloud API template/webhook adapter are
built, as are Capacitor wrappers. Provider credentials, persistent deployment,
Meta assets/approval, physical-device checks, and store publication remain
activation gates and must not be presented as active when `/capabilities` says
otherwise. Meta documents template review as taking up to 24 hours and does not
publish a guaranteed 1–2 week business-verification SLA. The implementation
must **push** a message to the user unprompted (the proactive notification is
the entire differentiator; if the demo looks like the user asked first, you've
built the thing you were trying not to build). Show, front and center:

1. The proactive message firing.
2. The approve/adjust/skip control.
3. The passkey approval step (real or, if the demo environment can't show
   biometrics on a shared screen, a clearly-labeled simulated prompt).
4. The completed transaction + updated audit/savings log.

---

## 10. Restock Teams (B2B skin) — SaaS subscription renewal, not office pantry

This track exists specifically to answer the hackathon brief's "manage a
subscription" and "procure software" examples directly — treat it as core
scope, not a stretch goal, since it's genuinely cheap: it reuses the entire
engine, and its trigger source (§6.2 in `TECHNICAL_PRD.md`) is *simpler* than
the consumables track because there's no forecasting — the renewal date is
just a known fact on the `TrackedItem` record.

**What to build:**
- One seeded `TrackedItem` with `track=teams`, `trigger_type=known_date` — e.g.
  a mocked "TeamTool Pro" subscription with a `renewal_date` two days out, a
  `current_plan_amount`, and a cheaper `alternate_plan_amount` (annual plan).
- When the trigger fires, the proposal is: *"TeamTool Pro renews in 2 days at
  $29/mo. Switch to the annual plan and save $58/year, or keep as is?"*
- Present that proposal in the disclosed mocked Slack-style surface with an
  explicit renew-as-is vs. switch-plan choice. Never switch plans without the
  user's explicit approval, even when the alternate is cheaper.
- Same Prava mandate flow, same passkey approval, same audit log as Restock
  Home — only the merchant/billing call differs (see next point).
- One-time hosted-invoice quoting is implemented. Unattended final payment is a
  **disclosed mock**. Prava now documents active-mandate charging through its
  server REST API, but Restock has not implemented or sandbox-proved that
  separate charge/report boundary. Keep recurring Teams charging disabled
  until those integration tests pass; do not infer readiness from the
  platform endpoint alone.
- The Prava mandate is scoped to a **team budget cap** instead of a personal
  one, and the audit log is framed as a savings report ("caught 1 price
  increase, saved $58/year") rather than a personal pantry log.

Build this as a config/data change against the same `TrackedItem` schema, not
a fork of the codebase — if it turns into a second codebase, the abstraction
in `TECHNICAL_PRD.md` §6 wasn't done right.

---

## 11. Pre-submission checklist

- [ ] One end-to-end Prava flow per track, agent-initiated: (1) session created, (2) credential generated, (3) credential populated into real checkout form via browser automation, (4) Pay attempt fails due to test-card status — not due to a bug
- [ ] At least 2 of 3–5 demo items successfully reorder autonomously in a run-through
- [ ] Proactive notification clearly fires without a user-typed purchase request
- [ ] Spend caps and approve/adjust/skip step are visible in the demo, not just in code
- [ ] Audit/savings log is populated and shown
- [ ] Anything mocked (merchant fulfillment, biometric prompt) is explicitly disclosed
- [ ] Pre-event foundation and official-window work are separated using commit evidence
- [ ] `/capabilities` matches every real/simulated badge shown in the demo
- [ ] Built on OpenAI Agents SDK, not the deprecated Agent Builder
- [ ] README explains the user, the problem, and the flow in plain language
- [ ] 5-minute demo video recorded per `demo/script.md`
- [ ] Submitted on Devfolio before the deadline under the solo builder account

---

## 12. Reference files

- `PRD.md` — product rationale, competitive landscape, business model, roadmap
- `PITCH.md` — founder-voice pitch, demo script, application answers
- External (fetch at build time, don't rely on memory): `docs.prava.space`,
  `github.com/Prava-Payments/prava-skills`
