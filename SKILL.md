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
  the canonical file structure, the payment-flow sequencing, the fallback
  plan if Zepto/Swiggy sandbox access isn't confirmed, and the pre-submission
  checklist.
---

# Restock — Hackathon Build Skill

## What this skill is for

Use this whenever building, fixing, or extending any part of **Restock**: an agent
that predicts when a recurring consumable will run out and autonomously buys a
replacement through Prava before that happens — no chat request required.

**Read the companion `PRD.md` for product rationale.** This file is the *build spec* —
it tells you what to actually implement and in what order.

**Never invent Prava SDK method names from memory.** This skill describes Prava's
integration model at the *conceptual* level (Intent → Passkey → Mandate → one-time
credential), because the exact class/endpoint names may have shifted since this
skill was written. Before writing the payment integration code, fetch:

- `https://docs.prava.space/llms.txt` (documentation index)
- The `prava-sdk-integration` and `prava-pay` skill folders in
  `github.com/Prava-Payments/prava-skills` (these contain the actual
  `PravaSDK` class reference, session API reference, and test/sandbox card data)
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

---

## 2. Judging breakdown → build priorities

| Judged on | Weight in your build time | What to actually do |
|---|---|---|
| Does it work | Highest | Get **one real Prava transaction** (sandbox or live) completing end-to-end before building anything else |
| Meaningful agent action | High | The purchase must be agent-initiated on a predicted condition, not a user-typed "buy X" |
| Handles payment clearly | High | Spend caps and the approve/adjust/skip step must be visually obvious in the demo |
| Solves a clear problem | Medium | One clean, well-narrated user story beats five half-built features |
| Could become a real product | Medium | Keep the audit/savings log — it's your "this isn't a toy" signal |
| OpenAI usage | Medium | Use the **Agents SDK** (code-first). Do not build on Agent Builder — OpenAI deprecated it June 3, 2026, shutting down Nov 30, 2026 |
| Prava integration depth | Medium | Reuse Prava's own published merchant skills rather than reinventing checkout |
| Startup potential / consumer / B2B | Lower, but free | The Home/Teams dual-skin costs little extra and covers two award categories at once |

**Sequencing rule:** payment flow first, forecasting logic second, UI polish third,
B2B skin last (only if time remains). A team that nails the Prava flow with a
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
│   ├── prava_client.py             ← wraps the actual Prava SDK (see §4)
│   └── mandate_flow.py             ← intent → passkey → mandate → credential sequence
├── merchant/
│   ├── zepto_checkout.py           ← wraps Prava's zepto-prava-skill (Home)
│   ├── mock_checkout.py            ← fallback if Zepto/Swiggy sandbox isn't confirmed (see §8)
│   └── mock_subscription_checkout.py ← disclosed mock billing call (Teams, see §10)
├── ui/
│   └── chat_surface/               ← ChatKit or simple web chat, proactive-message capable
├── logs/
│   └── audit_log.json              ← running savings/avoided-stockout record
└── demo/
    ├── script.md                   ← the 5-minute submission video script
    └── seed_reset.py                ← resets demo state between run-throughs
```

---

## 4. Prava integration — conceptual flow (confirm exact API against live docs)

Prava's model, per their documentation, is: **Intent → Passkey → Mandate → one-time
credential → merchant checkout.**

```
1. Merchant/session setup (server-side): create a session describing the order
   (merchant identity, amount, item description).
2. User enrollment (one-time, during onboarding): user connects a card/wallet
   and sets up a passkey via the Prava SDK/dashboard flow.
3. Agent creates a purchase INTENT: specifies merchant + amount + constraints
   (this is the "I want to buy X from Zepto for ₹450" step — happens the moment
   the consumption tracker fires, NOT when the user asks).
4. User authenticates the intent via PASSKEY (Face ID / Touch ID / platform
   equivalent). In the hackathon demo, this is the approve/adjust/skip UI moment.
5. Prava registers a MANDATE with the card network and returns a one-time,
   merchant-scoped, amount-scoped credential.
6. Agent executes checkout at the merchant using that credential — via the
   merchant's Prava-published MCP skill (see §6), not a hand-rolled integration.
7. Log the completed transaction + amount + item to the audit log (§7).
```

**Implementation instructions for whoever builds this:**

- Do not hardcode API paths/class names here — pull the current `PravaSDK` class
  reference and session API reference from the `prava-sdk-integration` skill
  folder in `Prava-Payments/prava-skills` at build time.
- Use their **sandbox test cards / test data** (documented in that same skill
  folder under `test-data.md`) for all development — never use a real card
  until the flow is fully verified.
- Build the intent-creation call as a function the orchestrator agent can call
  as a tool (`request_prava_intent(merchant, amount, item, constraints)`), not
  as inline code in the orchestrator's prompt — keeps it testable in isolation.
- Test this flow **before** writing a single line of the consumption tracker or
  UI. If this doesn't work, nothing else matters for the submission.

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
remain bounded by code-level Guardrails and human-in-the-loop controls.

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

## 7. Merchant checkout — reuse Prava's own skill, don't rebuild it

Prava publishes ready-made merchant checkout skills at
`github.com/Prava-Payments/prava-skills/tree/main/prava-merchants-checkout/`,
including `swiggy-prava-skill` and (per their skill index) a Zepto MCP
configuration. Point your coding agent at that folder directly and ask it to
wire up the merchant side — this is meant to be consumed, not reverse-engineered.

**Audit log:** every completed transaction appends `{item, merchant, amount,
timestamp, days_saved_vs_stockout}` to `logs/audit_log.json`. This log is what
you show judges to make the "could become a real product" case — it's the
receipt trail, not just a chat transcript.

---

## 8. Fallback plan if Zepto/Swiggy sandbox access isn't confirmed

Check this in Prava's Discord / office hours in the first few hours of the
hackathon. If sandbox merchant access isn't confirmed by roughly hour 8:

- Build `merchant/mock_checkout.py`: a clearly-labeled simulated merchant endpoint
  that still receives and validates the real Prava one-time credential (so the
  *payment* half of the demo is 100% real — only the merchant fulfillment step
  is mocked).
- State this explicitly in the submission write-up. The hackathon rules ask you
  to disclose what's simulated — do this rather than let a judge discover it.
- This does not weaken the "meaningful agent action" or "handles payment
  clearly" criteria, since the Prava mandate flow itself is still real.

---

## 9. UI / demo surface

Build two disclosed mocked surfaces matching the primary channels defined in
`PRD.md` §10, "Distribution and surface":

- **Restock Home:** a WhatsApp-style conversation with a proactive message and
  interactive approve/adjust/skip controls.
- **Restock Teams:** a Slack-style billing notification and approval surface.

Do not attempt real WhatsApp Business API or real Slack app integration during
the hackathon window. WhatsApp Business verification takes 1–2 weeks, outside
the 48-hour build, and both mocked surfaces must be disclosed in the demo and
submission. The implementation may use ChatKit or a minimal web dashboard, but
it must **push** a message to the user unprompted (the proactive notification is
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
- Checkout completion is a **disclosed mock** (`merchant/mock_subscription_checkout.py`)
  against the same `complete_checkout(...)` contract as the Zepto/Swiggy
  client — real OAuth into a SaaS vendor's billing portal isn't realistic in
  48 hours, and disclosing a mock here costs you nothing with judges; pretending
  otherwise would.
- The Prava mandate is scoped to a **team budget cap** instead of a personal
  one, and the audit log is framed as a savings report ("caught 1 price
  increase, saved $58/year") rather than a personal pantry log.

Build this as a config/data change against the same `TrackedItem` schema, not
a fork of the codebase — if it turns into a second codebase, the abstraction
in `TECHNICAL_PRD.md` §6 wasn't done right.

---

## 11. Pre-submission checklist

- [ ] One real (sandbox or live) Prava transaction completes end-to-end, agent-initiated
- [ ] At least 2 of 3–5 demo items successfully reorder autonomously in a run-through
- [ ] Proactive notification clearly fires without a user-typed purchase request
- [ ] Spend caps and approve/adjust/skip step are visible in the demo, not just in code
- [ ] Audit/savings log is populated and shown
- [ ] Anything mocked (merchant fulfillment, biometric prompt) is explicitly disclosed
- [ ] Built on OpenAI Agents SDK, not the deprecated Agent Builder
- [ ] README explains the user, the problem, and the flow in plain language
- [ ] 5-minute demo video recorded per `demo/script.md`
- [ ] Submitted on Devfolio before the deadline, with team members all individually accepted

---

## 12. Reference files

- `PRD.md` — product rationale, competitive landscape, business model, roadmap
- `PITCH.md` — founder-voice pitch, demo script, application answers
- External (fetch at build time, don't rely on memory): `docs.prava.space`,
  `github.com/Prava-Payments/prava-skills`
