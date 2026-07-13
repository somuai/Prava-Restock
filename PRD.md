Restock — Final Detailed PRD
Prava Agentic Commerce Hackathon · Jul 31–Aug 2, 2026
Soumyajit Ghosh · Dhruv Saxena · Pabak P Pany · Ritvik Mukherjee
Version 2.0 — Consolidated Product & Technical Specification

Contents
Executive Summary
Theme alignment . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

3
3

Part I — Product
1. The problem . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
2. The solution . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
3. Why now — market context . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
4. Competitive landscape . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
5. Target users . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
6. Scope for the 48-hour build . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
7. Core user flows . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

4
4
4
4
4
5
5
6

Part II — Technical Architecture
8. System context . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
9. Component architecture . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
10. Design principles . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
11. Data model . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
12. Trigger sources . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
13. Orchestrator agent . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
14. End-to-end sequence (happy path) . . . . . . . . . . . . . . . . . . . . . . . .
15. External integration contracts . . . . . . . . . . . . . . . . . . . . . . . . . . .
16. Non-functional requirements . . . . . . . . . . . . . . . . . . . . . . . . . . . .
17. Error handling and edge cases . . . . . . . . . . . . . . . . . . . . . . . . . . .
18. Testing strategy . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

7
7
7
7
8
9
9
10
11
11
11
11

Part III — Trust & Operations
19. Privacy and data handling . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
20. Risks and mitigations . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
21. Deployment for the hackathon . . . . . . . . . . . . . . . . . . . . . . . . . . .
22. Observability . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

13
13
13
14
14

Part IV — Business & Execution
23. Success metrics for the demo . . . . . . . . . . . . . . . . . . . . . . . . . . .
24. Judging-criteria alignment . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
25. Business model . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
26. Roadmap beyond the hackathon . . . . . . . . . . . . . . . . . . . . . . . . . .
27. Team and suggested roles for the 48 hours . . . . . . . . . . . . . . . . . . . .
28. Immediate action items . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

15
15
15
15
15
16
16

1

Appendices
A. Known limitations and non-goals (v1) . . . . . . . . . . . . . . . . . . . . . . . .
B. Open questions — verify before/during build . . . . . . . . . . . . . . . . . . . .
C. Glossary . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

2

18
18
18
18

Executive Summary
Restock is Auto-Buy for the open web. Amazon’s Rufus AutoBuy proved that conditiontriggered autonomous purchasing works — roughly $12B a year in incremental sales — but it
fires on one signal (price), inside one catalog. Restock generalizes the pattern: one engine,
two trigger sources, both ending in the same Prava-mediated purchase.
• Restock Home — predicts when a household consumable (coffee, filters, printer paper)
is about to run out, and reorders it before the user notices.
• Restock Teams — watches known SaaS subscription renewal dates for a small team, and
autonomously renews at the best available terms or flags a switch.
Both tracks share one pipeline: trigger → propose → passkey-approve → Prava mandate
→ merchant checkout → audit log. Only the source of the trigger date differs — predicted
for Home, known for Teams.

Theme alignment
Hackathon brief asks for

Restock’s answer

Agent that discovers, decides, completes a
transaction using Prava

Trigger date → proposal → passkey approval
→ Prava mandate → merchant checkout, end
to end
Deliberately the latter — proactive, not
comparison-shopping
Restock Teams: autonomous SaaS renewal
and right-sizing
Same Restock Teams track — a small team’s
subscription renewal is its software
procurement
Deliberately out of scope — one-off,
discovery-driven decisions are the opposite
of the proactive thesis; forcing them in would
dilute the product
Real monetization path and roadmap — see
Part IV

“shop across merchants… or create a new
kind of commerce experience”
“manage a subscription”
“procure software”

“book a trip” / “reserve a table”

“useful products that can live beyond the
hackathon, not slide decks”

3

Part I — Product
1. The problem
Households, hostel residents, and small teams sit on a bad binary every week: over-order
recurring essentials to avoid running out, or under-order and pay a panic-priced surcharge. It’s
not a decision problem — the user already knows they’ll need more coffee in ~10 days — it’s
an attention problem nobody wants to own.
Every agentic-commerce product shipping today is reactive: the user asks, the agent shops.
That pattern has a real ceiling. Walmart’s ChatGPT Instant Checkout converted 3x worse
than simply linking to walmart.com, and OpenAI walked back pure in-chat checkout toward
merchant-hosted apps within months of launch. A chat window doesn’t replace a cart, a loyalty
program, or a returns relationship.
The same underlying problem shows up in B2B: small teams get silently auto-renewed on SaaS
subscriptions at a price they never re-checked, or keep paying for seats nobody uses — and
they’re too small for an enterprise procurement platform like Ramp or Vendr to bother serving.

2. The solution
Restock tracks a trigger date per item — predicted depletion for physical consumables, or a
known renewal date for subscriptions — and, without being asked in the moment, proposes
and executes a real purchase through Prava’s passkey-approved, merchant-scoped, one-time
credential flow.
“You’ll run out of coffee in 2 days — reorder the usual bag for ₹450?” “TeamTool Pro
renews in 2 days at $29/mo. Switch to the annual plan and save $58/year, or keep
as is?”
One approval either way. The agent proposes; it never silently substitutes or switches without
explicit confirmation.

3. Why now — market context
Signal

What it tells us

Google AP2 v0.2 (Apr 2026) shipped “Human
Not Present” payments
Amazon Rufus AutoBuy (Nov 2025): 60%
higher purchase completion, ~$12B
incremental annualized sales
Visa piloting recurring-fee autonomous
payments (Aldar, UAE)
Walmart’s Instant Checkout: 3x worse
conversion than the website
Prava’s own skill repo ships Zepto and
Swiggy MCP checkout skills

The protocol layer is now explicitly built for
autonomous, pre-authorized purchases
Condition-triggered autonomous buying is
proven at scale — inside one walled garden,
on one signal
Card networks are actively building rails for
this exact pattern
The reactive “shop in chat” pattern is not
where the value is
The India-first merchant integration risk is
largely pre-solved

4. Competitive landscape

4

Player

Layer

Trigger

Merchant scope

Gap Restock fills

Amazon Rufus
AutoBuy

Consumer
product

Price threshold

Amazon catalog
only

Google AP2 /
UCP

Protocol

Human-present
or
pre-authorized

Any UCP
merchant

OpenAI ACP /
Instant
Checkout

Protocol +
product

User asks,
in-chat

Etsy, Shopify,
Instacart, etc.

Visa TAP / VIC

Trust/identity
layer

N/A (infra)

Any Visa
merchant

Skyfire, Nekuda,
Rye

Agent identity/checkout
infra

N/A (infra)

Cross-merchant

Ramp, Vendr

Enterprise SaaS
procurement

Manual/periodic
review

Enterprise
vendors

Restock

Application,
on Prava

Predicted
depletion or
known
renewal date

Zepto/Swiggy
(Home); any
SaaS
subscription,
mocked billing
(Teams)

Not price-only;
not
Amazon-only
Restock is an
application on
Prava, not
another protocol
Reactive; proven
lower-converting
for this shape of
purchase
Infra, not a
consumer
product
Infra —
redundant to
rebuild for this
hackathon
Doesn’t serve
teams too small
for enterprise
procurement
First
consumptionand renewaltriggered
autonomous
agent on the
open web

5. Target users
• Restock Home: hostel/PG residents and young professionals managing their own pantry
and toiletries with no time for restocking admin.
• Restock Teams: small founders/team leads (2–15 people) already overpaying for unused
SaaS seats or getting silently auto-renewed at a price they never re-checked.

6. Scope for the 48-hour build
In scope: - 3–5 demo consumable SKUs (predicted-trigger track) with manually-seeded cadence, plus exponential-smoothing recalibration. - One SaaS subscription item (known-trigger
track) with a real stored renewal date. - Full Prava intent → passkey → mandate → one-timecredential → checkout flow against sandbox, shared by both tracks. - Zepto/Swiggy checkout
via Prava’s published MCP skill for Home (or a disclosed mock if sandbox access isn’t confirmed
in time). - A disclosed mock subscription-billing checkout for Teams from the start — real SaaS
OAuth integration isn’t realistic in 48 hours. - Proactive notification UI with approve/adjust/skip,
identical pattern for both tracks. - Savings/audit log after every autonomous action.
Explicitly out of scope (roadmap items): - A real trained forecasting model — deterministic
exponential smoothing only. - Real OAuth/billing-portal integration with any actual SaaS vendor.
- Multi-user household or team mandate sharing. - Native mobile app.

5

7. Core user flows
Restock Home: 1. User connects a wallet in Prava, sets spend caps, adds 3–5 items with
a rough cadence. 2. Two days before predicted depletion, Restock messages the user with
an item, amount, and merchant. 3. User approves via passkey (or adjusts/skips). 4. Prava
mandate issued; merchant checkout completes via Zepto/Swiggy MCP. 5. Confirmation and
updated savings log shown; cadence recalibrated for next cycle.
Restock Teams: 1. Same onboarding; team budget cap set instead of a personal one. 2.
Two days before a known renewal date, Restock proposes renew-as-is or switch-to-cheaperplan. 3. User approves via passkey. 4. Prava mandate issued; billing checkout completes
(disclosed mock). 5. Confirmation and savings report shown (e.g., “caught 1 price increase,
saved $58/year”).

6

Part II — Technical Architecture
8. System context
Four actors, one system:
• User — approves every purchase via passkey; sets spend caps once at onboarding.
• Restock backend — trigger engine, orchestrator, audit logging.
• Prava — payment intent, passkey challenge, mandate issuance, one-time credential. Restock never stores a card number; Prava is the only component that ever sees payment
instrument data.
• Merchant / billing surface — Zepto/Swiggy (Home) or a disclosed mock (Teams) —
receives the one-time credential and fulfills the order.
User <--approve/adjust/skip--> Restock Backend <--intent/mandate--> Prava
|
+--credential-> Merchant/Billing (real or disclosed mock)

9. Component architecture
Component

Responsibility

Notes

Trigger engine

Two interchangeable sources
feeding the same pipeline:
predicted (Home) and
known-date (Teams)
Tool-using loop (OpenAI
Agents SDK) deciding
what/when to propose,
sequencing Prava +
merchant calls
Thin wrapper around Prava’s
SDK — intent creation,
mandate polling/webhook,
credential retrieval
Wraps Zepto/Swiggy MCP
checkout (Home) and a
disclosed mock billing
checkout (Teams)
Persists Intents, Mandate
references, Transactions, and
the user-facing audit log
Displays proactive
notifications and the
audit/savings log

Deterministic, no ML model
for v1

Orchestrator agent

Prava client

Merchant client

Audit/notification store

UI (chat surface)

Scheduled tick, not a chat
handler;
trigger-type-agnostic

Isolate Prava-specific code
behind this interface

Both implement the same
complete_checkout(...)
contract
See §11 for schemas

ChatKit or minimal web
dashboard

10. Design principles
1. Payment data never touches our storage. Every persisted field is a reference (mandate ID, credential reference, transaction ID) — never a card number, never raw passkey
material.
2. Every autonomous action is bounded. Spend caps are hard limits enforced before a
Prava intent is even created.
7

3. The orchestrator proposes; it never silently substitutes. Price/availability changes
beyond tolerance, or a plan switch, always route back to the user.
4. Idempotency by construction. Every merchant/billing call carries the originating intent_id as an idempotency key.

11. Data model
User
user_id
UUID (pk)
display_name
string
prava_account_ref
string
# Prava's account/wallet reference, never a card
monthly_cap
decimal
per_item_cap
decimal
per_transaction_cap decimal
created_at
timestamp
TrackedItem
# base entity — both tracks share this shape
item_id
UUID (pk)
user_id
UUID (fk -> User)
name
string
track
enum(home, teams)
trigger_type
enum(predicted, known_date)
category
enum(grocery, stationery, health, saas_subscription, other)
sensitive_flag
bool
# user-marked; excluded from any analytics
preferred_merchant
enum(zepto, swiggy, mock_subscription_billing, mock)
merchant_sku_id
string
status
enum(active, paused, deleted)
# predicted trigger only (Restock Home)
typical_cadence_days float
last_purchased_at
date
last_purchase_amount decimal
# known-date trigger only (Restock Teams)
renewal_date
date
current_plan_amount
decimal
alternate_plan_amount decimal
alternate_plan_label
string
Intent
intent_id
UUID (pk)
item_id
UUID (fk -> TrackedItem)
proposed_amount
decimal
proposed_merchant
string
status
enum(pending_approval, approved, adjusted, rejected, expired)
created_at
timestamp
Mandate
# reference only — Prava owns the real object
mandate_id
string (pk, Prava-issued)
intent_id
UUID (fk -> Intent)
credential_reference string
# opaque, one-time, never a raw card number
scope_merchant
string
scope_max_amount
decimal
scope_expiry
timestamp
8

passkey_approved_at
Transaction
transaction_id
mandate_id
item_id
merchant_order_id
amount
status
completed_at
AuditLogEntry
log_id
user_id
event_type

payload
timestamp

timestamp

UUID (pk)
string (fk -> Mandate)
UUID (fk -> TrackedItem)
string
decimal
enum(completed, failed, disputed)
timestamp

UUID (pk)
UUID (fk -> User)
enum(notification_sent, approved, adjusted, skipped,
transaction_completed, transaction_failed,
item_deleted, data_exported)
JSON
# minimal — never payment data
timestamp

12. Trigger sources
Both trigger sources answer one question — should_fire(item) -> bool — and hand the
orchestrator the same shape of output. Everything downstream is identical for both tracks;
this abstraction is what lets Teams exist as a data variant instead of a second codebase.
12.1 Predicted trigger (Restock Home)
predicted_depletion_date = last_purchased_at + typical_cadence_days
days_until_depletion
= predicted_depletion_date - today
trigger_condition
= days_until_depletion <= TRIGGER_WINDOW_DAYS # default 2
typical_cadence_days_new = ALPHA * observed_interval_days
+ (1 - ALPHA) * typical_cadence_days_old

# ALPHA default 0.3

First-time items seed typical_cadence_days from a user-provided estimate; there’s no coldstart model, just an honest guess corrected within 2–3 real cycles. A real regression/time-series
model is explicitly deferred to post-hackathon.
12.2 Known-date trigger (Restock Teams)
days_until_renewal = renewal_date - today
trigger_condition = days_until_renewal <= TRIGGER_WINDOW_DAYS

# default 2

proposed_action = "renew_as_is" if alternate_plan_amount >= current_plan_amount
else "switch_to_alternate"
No recalibration needed — renewal_date is a fact, not a prediction. This is deliberately the
simpler track, which is exactly why it’s the right second track to add: near-zero additional
orchestrator complexity for direct coverage of the brief’s “manage a subscription” and “procure
software” examples.

13. Orchestrator agent
Built on OpenAI’s Agents SDK (not Agent Builder — deprecated June 2026, shutting down Nov
30, 2026). Runs as a scheduled tool-using loop, not a request/response chat handler. Single

9

agent, not multi-agent — the brief’s own language (“an AI agent,” “an agent”) is singular both
times it describes what’s judged, not a scope compromise for 48 hours.
Model split: gpt-5.4-mini (low reasoning effort/verbosity — the SDK’s own default for this
shape of workload) drives the routine loop — checking triggers, sequencing tool calls. gpt5.6-sol is reserved for the two moments needing real judgment: writing the notify_user
proposal copy, and the Restock Teams renew-vs-switch decision. Cheap model for the mechanical majority of calls, better model only where a wrong call actually costs something.
Guardrails and human-in-the-loop — named SDK primitives, not hand-rolled checks:
spend caps and the “never silently substitute” rule are implemented as the Agents SDK’s
Guardrails primitive, validating tool inputs/outputs in code the model doesn’t control — not
something the model self-polices via its instructions. The passkey-approval pause is the SDK’s
built-in human-in-the-loop resumable-approval mechanism, not a custom polling loop.
Tool surface:
check_trigger_status() -> list[TrackedItem]
# items where trigger_condition is true (predicted OR known-date)
# and no pending Intent exists
request_prava_intent(merchant, amount, item_id, constraints) -> Intent
# gated by a Guardrail checking per_item_cap / monthly_cap before proceeding
notify_user(item_id, message, actions=["approve","adjust","skip"]) -> None
# copy generated by gpt-5.6-sol; the trigger decision itself stays on gpt5.4-mini
await_passkey_approval(intent_id) -> MandateResult
# the SDK's human-in-the-loop resumable-approval mechanism
complete_merchant_checkout(mandate_id, item_id) -> Transaction
log_event(event_type, payload) -> None
Guardrail constraints — enforced in code, not just stated in the system prompt: Never call complete_merchant_checkout without a MandateResult showing passkey approval.
- Never propose an amount exceeding per_item_cap or monthly_cap — a Guardrail on request_prava_intent, not a prompt instruction the model could get wrong. - If price deviates from last_purchase_amount by more than ~15%, or the item is out of stock, re-route
to notify_user rather than proceeding silently. - For known-date items: never auto-select
switch_to_alternate without explicit approval, even when strictly cheaper — a plan switch
can carry consequences (feature loss, contract terms) the amount alone doesn’t capture.

14. End-to-end sequence (happy path)
1. Scheduler tick calls check_trigger_status().
2. Triggered item → request_prava_intent(...) → local Intent created, Prava intent request sent.
3. notify_user(...) — proactive message, no user-initiated request.
4. User taps Approve → passkey challenge → Prava registers a Mandate, returns a one-time
credential reference.
5. complete_merchant_checkout(...) invokes the merchant/billing client.
6. Merchant confirms → Transaction created; TrackedItem state updated (recalibrated cadence for Home; nothing to update for Teams beyond marking the cycle done).
7. log_event appends the trail; UI shows the updated audit/savings log.
Branches: Skip → Intent.status = rejected, cooldown before re-check. Adjust → new
proposal, loop back to step 2. Out-of-stock/price-tolerance breach/plan-switch proposal
→ re-route to notify_user, never auto-resolve.

10

15. External integration contracts
Prava (verify exact signatures at build time): conceptually, intent → passkey → mandate
→ one-time credential. Pull the current PravaSDK class and session API reference from pravasdk-integration in Prava-Payments/prava-skills — do not hardcode API paths from this
document.

create_intent(merchant, amount, item_description, constraints) -> intent_ref
await_mandate(intent_ref) -> { mandate_id, credential_reference, scope, approved_at } | reject
Merchant/billing checkout — one contract, two implementations:
complete_checkout(credential_reference, merchant_sku_id, amount, idempotency_key) > { merchant_order_id, status }
Home: reuse Prava’s published Zepto/Swiggy checkout skill, or a disclosed mock if sandbox
access isn’t confirmed. Teams: a disclosed mock billing checkout from the start — real SaaS
OAuth isn’t realistic in 48 hours regardless of sandbox access.
OpenAI Agents SDK: standard tool-calling loop; verify current model pricing/latency at build
time rather than assuming.

16. Non-functional requirements
Requirement

Target

Notification-to-confirmation latency
(excluding user response time)
Mandate creation success rate (sandbox)
Unauthorized transactions
Spend-cap breaches
Idempotent checkout
Secrets handling

< 5s
≥ 99% across test runs
0 — hard guardrail
0 — hard guardrail
Every call keyed by intent_id
Environment variables only; never committed

17. Error handling and edge cases
Scenario

Handling

Merchant reports out-of-stock

Notify user; no transaction created;
re-checked next cycle
Require explicit re-approval
Propose the switch; never auto-select it
Intent.status = expired; item re-enters
normal check cycle
Retry with backoff (max 2), then notify user
and log the failure
Suppress duplicate notification

Price deviates >15% from last purchase
Cheaper alternate plan available (Teams)
Mandate/passkey rejected or times out
Merchant/billing API error or timeout
Duplicate trigger while an Intent is pending

18. Testing strategy
• Unit tests: trigger math for both tracks (predicted-date recalibration; known-date comparison) against fixed fixtures; tool functions against mocked Prava/merchant responses.
• Integration test: one full sandbox run of the happy path for each track, plus one
rejected-mandate path, before demo day.

11

• Demo rehearsal: a timed run-through fitting inside the 5-minute submission video window.

12

Part III — Trust & Operations
19. Privacy and data handling
Two distinct privacy problems, not one.
Payment privacy — structurally solved by Prava. Restock never stores a card number, CVV, or any PCI-scoped instrument. Every transaction runs through Prava’s one-time,
merchant-scoped credential.
Behavioral privacy — the one to actually design for. Consumption data (what’s bought,
how often, when) can reveal health conditions (medication cadence), financial stress (erratic
reordering), or household composition. Subscription data (Teams) can reveal a team’s tooling
and spend patterns to anyone who gains access.
Regulatory context: India’s DPDP Act — Rules notified Nov 2025, phased implementation:
Data Protection Board live now, Consent Manager framework live Nov 2026, full substantive
enforcement from May 13, 2027. Not legally binding on a hackathon build today, but worth
designing toward now — most Indian companies haven’t started this work yet, and full enforcement lands before Restock could plausibly be a real product.
Design commitments: - Data minimization: store item name, category, cadence/renewal
data, last-purchase or current-plan amount — nothing else. - Purpose limitation, stated explicitly: data is used only to predict a trigger, never for ad targeting or resale. - Consent
re-confirmed per transaction: the passkey approval on every purchase is a per-transaction
consent checkpoint, stronger than a one-time signup checkbox. - Visible, deletable data: a
“here’s what we track and why” screen with a working delete button, per item and accountwide. - Sensitive-category flagging: items marked sensitive (e.g., medication) are excluded
from any analytics, even anonymized. - Retention limits: a rolling window (e.g., 12 months)
on the audit log rather than indefinite retention. - Age-gated to 18+: DPDP’s strict minors’
provisions are out of scope for a 48-hour build.

20. Risks and mitigations
Risk

Mitigation

Prava markets “US & SEA” coverage, but its
skill repo ships Zepto/Swiggy (India)
integrations — unclear if live for hackathon
sandbox use
Forecasting looks like a science project and
eats the clock

Confirm in Prava’s Discord/office hours on
day 1; fall back to a disclosed mock by hour 8

Passkey/biometric approval doesn’t demo
well on a shared screen
Judges read “proactive” as unsafe or spammy

Teams track reads as “not really using Prava”
since billing is mocked

Ship the day-counter first; add smoothing
only if time remains after the payment flow
works end-to-end
Scripted, clearly-labeled fallback ready for
the recorded demo
Make spend caps and the approve/adjust/skip
step visually central — control is the pitch,
not autonomy for its own sake
State plainly: the trigger, the Prava mandate,
and the passkey approval are real; only the
SaaS billing call is simulated

13

21. Deployment for the hackathon
Single lightweight backend (FastAPI or equivalent) plus the orchestrator process. Sandbox credentials only — nothing touches a real card until the full flow is verified end-to-end in sandbox
at least once. Cheap hosting (Render/Railway, or a tunneled local instance for the live demo)
is entirely sufficient.

22. Observability
A structured log line at every state transition (Intent created/approved/rejected, Transaction
completed/failed). logs/audit_log.json doubles as both the user-facing savings log and the
engineering debug trail for the hackathon — no separate dashboard needed.

14

Part IV — Business & Execution
23. Success metrics for the demo
• One real (or sandboxed) end-to-end Prava transaction per track, agent-initiated, with no
user-typed purchase request.
• At least 2 of the 3–5 Home items reordered autonomously during the judged walkthrough,
plus the one Teams subscription renewal proposal.
• A visible, believable savings number in the audit log for both tracks.
• Judges can articulate, unprompted, how this differs from “just another shopping bot.”

24. Judging-criteria alignment
Criterion

How Restock addresses it

Works

End-to-end Prava transaction, live or
sandboxed, on both tracks
Stockouts/over-ordering (Home) and silent
overpaying on subscriptions (Teams) — both
universal
Autonomous, condition-triggered purchase —
not a chat-mediated single click
Prava mandate flow front and center, spend
caps visible
Clear monetization below, reuses Prava’s
own published merchant skills
Agents SDK orchestrator (not the deprecated
Agent Builder)
Core to the product on both tracks, not
bolted on
Restock Home
Restock Teams — directly answers the brief’s
own “manage a subscription” / “procure
software” examples
Real recurring-revenue and affiliate paths,
see below

Solves a clear problem

Agent takes meaningful action
Handles payment clearly
Could become a real product
OpenAI usage
Prava integration
Consumer experience
B2B value

Startup potential

25. Business model
Restock Home: small monthly subscription per household (₹99–199), or a cut of avoidedstockout savings, or affiliate revenue from quick-commerce partners on autonomous reorders.
Restock Teams: a cut of savings actually found (e.g., 20% of first-year savings from a caught
price increase or right-sized seat count), or a flat per-seat monthly fee once a team tracks more
than a handful of subscriptions.

26. Roadmap beyond the hackathon
Each v1 limitation has a specific resolution path, not just a “later” label — sequenced by impact
vs. effort rather than by how they’re listed in Appendix A.
1. Notification delivery (highest priority — this is the product’s core value prop, not
a nice-to-have). A web dashboard nobody has open defeats the entire “reaches you before

15

you ask” thesis. Skip a native app first; go straight to WhatsApp Business API (fits an Indiafirst, Zepto/Swiggy userbase that already lives in WhatsApp — approve/adjust/skip map directly
onto WhatsApp’s interactive buttons) or an installable PWA with web push (no app-store
review cycle, works immediately). Native app only becomes justified once retention data on
one of those two shows people actually act on the notifications — building app-store presence
before that risks being wasted effort.
2. Real SaaS billing integration. The mock exists because a subscription renewal is
merchant-initiated (recurring), not agent-initiated (one-time) like a grocery reorder — a genuinely different transaction shape from what’s built. Two paths:
• Path A (elegant, unconfirmed): if Prava supports a standing/recurring mandate scoped
to one merchant with a cap, the vendor’s own billing system charges it directly, and
Restock’s job becomes watching for a decline or an over-cap amount as the trigger for a
renegotiation notification. This is the direction Visa’s Aldar pilot and AP2’s “Human Not
Present” mode both point toward — worth a direct question to Prava’s team rather than
an assumption (see Appendix B).
• Path B (buildable now, no new dependency): keep the existing agent-initiated, onetime-credential flow exactly as built, and have Restock pay the vendor’s hosted
invoice/payment link directly two days before the known renewal date — same architecture, different merchant_sku_id target. This is the one to actually build first.
3. Real forecasting model. The constraint is data volume, not modeling difficulty — a
single household doesn’t generate enough history to train anything meaningful per-user for
months. Sequence: keep logging (item, actual_interval, predicted_interval) from
day one even while running on plain exponential smoothing, so training data exists when it’s
needed; once there’s a real user base, train a shared model at the category level (coffee-type
items, paper-type items — where the volume actually is) with a small per-user bias term for
personalization, rather than per-user models that will always be data-starved. Keep the EWMA
as a permanent cold-start fallback for any new item regardless of how mature the overall
system gets — every new item starts cold no matter what.
4. Multi-user/household mandates. The hard part isn’t the schema (a Household entity
with member sub-limits is straightforward) — it’s an unresolved product-policy question: who’s
allowed to approve what, and what happens when two members disagree? Deliberately holding this until a single-user version is validated in the real world, rather than guessing at an
approval policy nobody’s tested against actual usage.
Also on the roadmap: expand merchant coverage beyond Zepto/Swiggy as Prava adds MCP
skills; combine the predicted and known-date triggers on the same item where relevant (buy
on whichever fires first) — directly one-ups Amazon AutoBuy’s single-signal model.

27. Team and suggested roles for the 48 hours
• Payments/Prava integration lead — owns the intent → passkey → mandate → credential flow end-to-end against sandbox; first thing to get working, for both tracks.
• Agent/orchestration lead — OpenAI Agents SDK loop, tool definitions, both triggersource implementations.
• Merchant/MCP integration lead — Zepto/Swiggy MCP wiring, checkout completion,
both mock fallbacks.
• Product/demo lead — UI, demo script, video, submission write-up, Discord/office-hours
liaison for the Zepto/Swiggy access question.

28. Immediate action items
1. Apply on Devfolio today if not already done — rolling review, 3-day RSVP window.
16

2. Confirm Zepto/Swiggy sandbox access in Prava’s Discord before hour 8.
3. Post a build-in-progress update tagging Prava per the overview page’s fast-track note.

17

Appendices
A. Known limitations and non-goals (v1)
Resolution paths for each of these are in §26 (Roadmap) — this list is deliberately just the “not
done yet” inventory, not the plan to close it.
• No real ML forecasting model — deterministic exponential smoothing only, for the
predicted-trigger track.
• No real SaaS billing-portal integration — the known-date track’s checkout is a disclosed
mock; the renewal date and Prava mandate flow around it are real.
• No multi-user/shared household or team mandates.
• No native mobile app.
• Merchant coverage limited to Zepto/Swiggy (or the disclosed mock) for Home; one disclosed mock subscription for Teams.

B. Open questions — verify before/during build
• RESOLVED — Model selection for the orchestrator: gpt-5.4-mini for the routine triggercheck loop, gpt-5.6-sol for notification copy and the Teams plan-comparison judgment
call. See §13.
• Exact PravaSDK method signatures for intent creation and mandate webhook payload
shape.
• Zepto/Swiggy MCP skill’s exact tool names and required auth scopes.
• Location of Prava’s sandbox test-card/test-data reference in prava-skills.
• Whether Prava mandates expose a configurable TTL/expiry we should set explicitly on
Intent creation, or whether it’s fixed by Prava.
• Whether Prava supports a standing/recurring mandate (scoped to one merchant, capped,
valid for repeat charges) — would let Restock Teams move off the disclosed billing mock
onto real vendor-initiated renewal charges (Path A in §26). Ask directly in Discord/office
hours rather than assuming either way.

C. Glossary
• Intent — internal record of a proposed purchase, before user approval.
• Mandate — Prava’s record of user-approved, scoped permission to charge a specific merchant a bounded amount.
• Credential reference — the opaque, one-time token held in place of any real payment
instrument.
• Trigger source — the mechanism that decides when a proposal fires: predicted (consumption forecast) or known-date (subscription renewal).

18

