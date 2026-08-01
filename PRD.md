# Restock — Final Detailed PRD

**Prava Agentic Commerce Hackathon · Jul 31–Aug 2, 2026**

**Builder:** Soumyajit Ghosh (solo)

**Version 2.0 — Consolidated Product & Technical Specification**

## Contents

- [Executive Summary](#executive-summary)
- [Part I — Product](#part-i--product)
- [Part II — Technical Architecture](#part-ii--technical-architecture)
- [Part III — Trust & Operations](#part-iii--trust--operations)
- [Part IV — Business & Execution](#part-iv--business--execution)
- [Appendices](#appendices)

## Executive Summary

Restock is Auto-Buy for the open web. Amazon’s Rufus AutoBuy proved that condition-triggered autonomous purchasing works — roughly $12B a year in incremental sales — but it
fires on one signal (price), inside one catalog. Restock generalizes the pattern: one engine,
two trigger sources, both ending in the same Prava-mediated purchase.

- Restock Home — predicts when a household consumable (coffee, filters, printer paper)
is about to run out, and reorders it before the user notices.
- Restock Teams — watches known SaaS subscription renewal dates for a small team, and
autonomously renews at the best available terms or flags a switch.

Both tracks share one pipeline: trigger → propose → passkey-approve → Prava mandate
→ merchant checkout → audit log. Only the source of the trigger date differs — predicted
for Home, known for Teams.

### Theme alignment

| Hackathon brief asks for | Restock’s answer |
| --- | --- |
| Agent that discovers, decides, completes a transaction using Prava | Trigger date → proposal → passkey approval → Prava mandate → merchant checkout, end to end |
| “shop across merchants… or create a new kind of commerce experience” | Deliberately the latter — proactive, not comparison-shopping |
| “manage a subscription” | Restock Teams: autonomous SaaS renewal and right-sizing |
| “procure software” | Same Restock Teams track — a small team’s subscription renewal is its software procurement |
| “book a trip” / “reserve a table” | Deliberately out of scope — one-off, discovery-driven decisions are the opposite of the proactive thesis; forcing them in would dilute the product |
| “useful products that can live beyond the hackathon, not slide decks” | Real monetization path and roadmap — see Part IV |


## Part I — Product

### 1. The problem

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

### 2. The solution

Restock tracks a trigger date per item — predicted depletion for physical consumables, or a
known renewal date for subscriptions — and, without being asked in the moment, proposes
and executes a real purchase through Prava’s passkey-approved, merchant-scoped, one-time
credential flow.
“You’ll run out of coffee in 2 days — reorder the usual bag for ₹450?” “TeamTool Pro
renews in 2 days at $29/mo. Switch to the annual plan and save $58/year, or keep
as is?”
One approval either way. The agent proposes; it never silently substitutes or switches without
explicit confirmation.

### 3. Why now — market context

| Signal | What it tells us |
| --- | --- |
| Google AP2 v0.2 (Apr 2026) shipped “Human Not Present” payments | The protocol layer is now explicitly built for autonomous, pre-authorized purchases |
| Amazon Rufus AutoBuy (Nov 2025): 60% higher purchase completion, ~$12B incremental annualized sales | Condition-triggered autonomous buying is proven at scale — inside one walled garden, on one signal |
| Visa piloting recurring-fee autonomous payments (Aldar, UAE) | Card networks are actively building rails for this exact pattern |
| Walmart’s Instant Checkout: 3x worse conversion than the website | The reactive “shop in chat” pattern is not where the value is |
| Prava’s own skill repo ships Zepto and Swiggy MCP checkout skills | The India-first merchant integration risk is largely pre-solved |

### 4. Competitive landscape

| Player | Layer | Trigger | Merchant scope | Gap Restock fills |
| --- | --- | --- | --- | --- |
| Amazon Rufus AutoBuy | Consumer product | Price threshold | Amazon catalog only | Not price-only; not Amazon-only |
| Google AP2 / UCP | Protocol | Human-present or pre-authorized | Any UCP merchant | Restock is an application on Prava, not another protocol |
| OpenAI ACP / Instant Checkout | Protocol + product | User asks, in-chat | Etsy, Shopify, Instacart, etc. | Reactive; proven lower-converting for this shape of purchase |
| Visa TAP / VIC | Trust/identity layer | N/A (infra) | Any Visa merchant | Infra, not a consumer product |
| Skyfire, Nekuda, Rye | Agent identity/checkout infra | N/A (infra) | Cross-merchant | Infra — redundant to rebuild for this hackathon |
| Ramp, Vendr | Enterprise SaaS procurement | Manual/periodic review | Enterprise vendors | Doesn’t serve teams too small for enterprise procurement |
| **Restock** | **Application, on Prava** | **Predicted depletion or known renewal date** | **Zepto/Swiggy (Home); any SaaS subscription, mocked billing (Teams)** | **First consumption- and renewal-triggered autonomous agent on the open web** |

### 5. Target users

- Restock Home: hostel/PG residents and young professionals managing their own pantry
and toiletries with no time for restocking admin.
- Restock Teams: small founders/team leads (2–15 people) already overpaying for unused
SaaS seats or getting silently auto-renewed at a price they never re-checked.

### 6. Scope and disclosure boundary

Restock is being developed as a production-oriented application before the
official 48-hour event. The repository history is the disclosure record for
that pre-event foundation. Only work completed during the official window may
be presented as hackathon-window work; pre-existing code, external provider
setup, and any simulated boundary must be identified plainly in the submission.

**In scope:**

- 3–5 demo consumable SKUs (predicted-trigger track) with manually-seeded cadence, plus exponential-smoothing recalibration.
- One SaaS subscription item (known-trigger track) with a real stored renewal date.
- Full Prava Session → passkey → polling → one-time credential → checkout-attempt flow against sandbox, shared by both tracks.
- Zepto/Swiggy catalog, stock, cart, and quote work through their published MCP surfaces, followed by a separately disclosed browser-payment boundary.
- A disclosed mock subscription-billing checkout for Teams from the start — real SaaS OAuth integration isn’t realistic in 48 hours.
- Proactive notification UI with approve/adjust/skip, identical pattern for both tracks.
- Savings/audit log after every autonomous action.

See §10, Distribution and surface, for the PWA-first launch surface, optional channel adapters, and why Restock is not embedded in a merchant’s app.

**Not part of the guaranteed judged flow:**

- A real trained forecasting model — deterministic exponential smoothing only.
- Real OAuth/billing-portal integration with any actual SaaS vendor.
- Store-published native apps or a reusable/shared Prava mandate. Tenant controls
  and Capacitor wrappers exist, but provider/store activation and physical-device
  proof remain outside the guaranteed flow.

**Truthful capability matrix at the current public deployment:**

| Boundary | Built capability | Current public activation |
| --- | --- | --- |
| Trigger, orchestration, spend caps, workflow recovery | Real code with credential-free CI coverage | Active; `demo_mode=false` |
| Prava | Real sandbox Session creation, passkey handoff, polling, credential normalization, and status reporting are implemented | Sandbox configured; the assigned card is currently blocked at Prava's Security Check Failed / No Passkey step; no production money |
| Zepto/Swiggy | Real catalog/cart/quote adapters and an explicit browser-payment executor | Catalog and final payment both `disclosed_mock` on the public service |
| Restock Teams billing | Hosted-link/manual-required workflow and one-time hosted-invoice adapter; Prava recurring charging is documented but not integrated or sandbox-proved by Restock | Fulfillment `disclosed_mock`; recurring disabled |
| Slack | Bolt/Socket Mode adapter built; private-workspace delivery/callback evidence recorded | Persistent deployed listener active with rotated credentials |
| WhatsApp | Cloud API template/webhook adapter built | Optional post-launch; deliberately outside the launch/submission gate |
| Native | Capacitor Android/iOS wrappers built and simulator-tested | Physical-device/store distribution not activated |

The running `/capabilities` response, not a static document, is authoritative
for the environment shown to judges.

### 7. Core user flows

**Restock Home:**

1. User connects a wallet in Prava, sets spend caps, adds 3–5 items with a rough cadence.
2. Two days before predicted depletion, Restock messages the user with an item, amount, and merchant.
3. User approves via passkey (or adjusts/skips).
4. Prava mandate issued; merchant checkout completes via Zepto/Swiggy MCP.
5. Confirmation and updated savings log shown; cadence recalibrated for next cycle.

**Restock Teams:**

1. Same onboarding; team budget cap set instead of a personal one.
2. Two days before a known renewal date, Restock proposes renew-as-is or switch-to-cheaper-plan.
3. User approves via passkey.
4. Prava mandate issued; billing checkout completes (disclosed mock).
5. Confirmation and savings report shown (e.g., “caught 1 price increase, saved $58/year”).

#### Restock Teams renewal boundary

Restock Teams targets subscriptions with a hosted, tokenized payment link
(Stripe Billing, Chargebee, Paddle, and similar platforms all support this
pattern — a payable invoice link that doesn't require a full account login).
Where a SaaS platform's only renewal path requires authenticating into a full
account dashboard, Restock explicitly does not attempt automated login — it
flags the item to the user as requiring manual renewal instead. This is a
deliberate boundary: storing or automating a user's real login credentials for
a third-party account is a fundamentally larger trust surface than Prava's
scoped, one-time, revocable credential model, and would contradict the trust
architecture the rest of the product is built on.

## Part II — Technical Architecture

### 8. System context

Four actors, one system:

- User — approves every purchase via passkey; sets spend caps once at onboarding.
- Restock backend — trigger engine, orchestrator, audit logging.
- Prava — payment Session, passkey challenge, one-time mandate/credential issuance.
  Restock never stores a card number. The short-lived token, dynamic CVV, and
  expiry data temporarily enter only the server-side payment boundary for one
  checkout attempt; they are held in memory, consumed once, and never logged or
  persisted.
- Merchant / billing surface — Zepto/Swiggy (Home) or a disclosed mock (Teams) —
receives the one-time credential and fulfills the order.

```text
User <--approve/adjust/skip--> Restock Backend <--session/polling--> Prava
|
+--consume-once credential-> Browser payment boundary (real or disclosed mock)
```

### 9. Component architecture

| Component | Responsibility | Notes |
| --- | --- | --- |
| Trigger engine | Two interchangeable sources feeding the same pipeline: predicted (Home) and known-date (Teams) | Deterministic, no ML model for v1 |
| Orchestrator agent | Tool-using loop (OpenAI Agents SDK) deciding what/when to propose, sequencing Prava + merchant calls | Scheduled tick, not a chat handler; trigger-type-agnostic |
| Prava client | Server-side Session creation, payment-result polling, one-time credential custody, and terminal status reporting | The browser Prava flow owns passkey approval; no mandate webhook is assumed |
| Merchant client | Zepto/Swiggy MCP catalog/cart/quote operations plus a separate Playwright payment boundary; one-time hosted invoice support for Teams | Catalog truth and final-payment execution expose independent real/simulated modes |
| Workflow store | SQLite for local/demo use; Postgres-compatible SQLAlchemy repositories and Alembic migrations through `20260801_11` for production | Persists references and state only, never raw payment credentials or approval URLs |
| UI and channels | PWA decision inbox plus Slack and WhatsApp adapters | Built capability is distinct from provider activation; `/capabilities` is authoritative at runtime |

See §10, Distribution and surface, for why this architecture is independent of every merchant app and where users actually interact with Restock.

### 10. Distribution and surface

Restock is an independent agent. It is not embedded inside Zepto, Swiggy, Amazon, or any other merchant’s app. This is a structural consequence of the payment architecture, not a distribution preference. Prava’s intent → passkey → mandate → one-time-credential model exists so an independent agent can transact on a user’s behalf across merchants with which it has no direct account relationship. A merchant’s own app already has the user’s payment method on file and does not need a scoped, revocable third-party mandate to charge it. “Embed Restock inside Zepto” and “use Prava as a real part of the product” are therefore close to mutually exclusive. Embedding would also trap Restock inside one merchant’s catalog and eliminate the cross-merchant value proposition entirely.

Amazon’s Rufus AutoBuy is the contrast. It works, but only inside Amazon’s catalog, using Amazon’s stored payment method and requiring no third-party mandate. That is the embedded model. Restock deliberately does not copy it.

Integration with Zepto or Swiggy means backend integration through the
merchant's remote MCP where available, with Prava handling the scoped payment
boundary. Prava's current skills repository also exposes generic Shopping and
Pay workflows rather than requiring a merchant-specific Restock UI. Restock
calls the merchant programmatically to complete a transaction. That is real,
deep integration at the API layer, invisible to the user; it is never a
Restock widget embedded in the merchant’s app screens. The same logic applies
to Restock Teams and SaaS billing: Restock pays the invoice through the
vendor’s billing surface; it does not live inside the vendor’s dashboard.

The user-facing surface is track-specific:

- **Restock Home — PWA at launch.** The Restock PWA is the primary launch and hackathon surface, with proactive Approve, Adjust, and Skip controls and explicit sandbox/simulation labels at affected provider steps. The WhatsApp Cloud API adapter remains a post-launch option for near-zero-friction delivery after Meta setup; activating it is not a launch or submission gate.
- **Restock Teams — Slack.** Small teams and founders already handle billing alerts and approvals where they work. Restock Teams meets that audience in Slack, not WhatsApp.
- **Native delivery — wrapper built, store launch deferred.** The shared PWA is
  wrapped with Capacitor for Android and iOS. Physical-device push/deep-link
  validation, store enrollment, and public distribution remain launch gates.
  Paying for and maintaining an App Store presence before notification-action
  retention is demonstrated would still be premature.

**Hackathon scope:** The real Restock PWA is the submission surface; it is not a mocked WhatsApp client. The WhatsApp adapter may remain in the codebase, but Meta onboarding, number, billing, opt-in, template, and webhook activation are optional post-launch work and are not a submission gate. Any future test-number integration must be labeled separately and must not be presented as a verified production WhatsApp deployment.

### 11. Design principles

1. Raw card and passkey data never touches our storage. Prava's one-time token and dynamic CVV are confined to the server-side payment boundary, held only long enough to complete one checkout, and never logged or persisted. Every durable field is a reference (mandate ID, credential reference, transaction ID).
2. Every autonomous action is bounded. Spend caps are hard limits enforced by
the Agents SDK tool guardrail before a Prava Session is created.
3. The orchestrator proposes; it never silently substitutes. Price/availability
changes, exact-SKU validation, and plan-switch approval are deterministic
workflow policies. They have local test coverage, but remain part of the live
Phase 8 boundary proof rather than being described as completed SDK Guardrails.
4. Idempotency by construction. Every merchant/billing call carries the originating intent_id as an idempotency key.

### 12. Data model

```text
User
  user_id             UUID (pk)
  display_name        string
  prava_account_ref   string        # Prava's account/wallet reference, never a card
  monthly_cap         decimal
  per_item_cap        decimal
  per_transaction_cap decimal
  created_at          timestamp

TrackedItem                         # base entity — both tracks share this shape
  item_id               UUID (pk)
  user_id               UUID (fk -> User)
  tenant_id             UUID | null
  name                  string
  track                 enum(home, teams)
  trigger_type          enum(predicted, known_date)
  category              enum(grocery, stationery, health, saas_subscription, other)
  sensitive_flag        bool        # user-marked; excluded from any analytics
  preferred_merchant    enum(zepto, swiggy, mock_subscription_billing, mock)
  merchant_sku_id       string
  merchant_address_ref  string | null # opaque saved-address reference, never raw address/phone
  quantity              integer | null # positive exact Home quote quantity
  currency              string        # ISO 4217
  status                enum(active, paused, deleted)

  # predicted trigger only (Restock Home)
  typical_cadence_days  float
  last_purchased_at     date
  last_purchase_amount  decimal
  price_threshold       decimal | null  # user-set price signal
  last_observed_price   decimal | null  # latest merchant price check
  # merchant_address_ref and quantity are required before a real Home quote;
  # legacy/mock Home items may omit them. Device IDs
  # stay in deployment configuration and are never stored on the item.

  # known-date trigger only (Restock Teams)
  renewal_date          date
  current_plan_amount   decimal
  alternate_plan_amount decimal
  alternate_plan_label  string

Intent
  intent_id             UUID (pk)
  item_id               UUID (fk -> TrackedItem)
  proposed_amount       decimal
  proposed_merchant     string
  currency              string        # ISO 4217
  status                enum(pending_approval, approved, adjusted, rejected, expired)
  created_at            timestamp

Mandate                              # reference only — Prava owns the real object
  mandate_id            string (pk, Prava-issued)
  intent_id             UUID (fk -> Intent)
  credential_reference  string      # opaque, one-time, never a raw card number
  scope_merchant        string
  scope_max_amount      decimal
  scope_expiry          timestamp
  passkey_approved_at   timestamp

Transaction
  transaction_id        UUID (pk)
  mandate_id            string (fk -> Mandate)
  item_id               UUID (fk -> TrackedItem)
  merchant_order_id     string
  amount                decimal
  currency              string        # ISO 4217
  status                enum(completed, failed, disputed)
  completed_at          timestamp

AuditLogEntry
  log_id                UUID (pk)
  user_id               UUID (fk -> User)
  event_type            enum(notification_sent, approved, adjusted, skipped,
                             transaction_completed, transaction_failed,
                             item_deleted, data_exported)
  payload               JSON        # minimal — never payment data
  timestamp             timestamp
```

This public model explains the agent contract. The durable database additionally
contains tenants, memberships, invitations, consent, workflow runs, quotes,
notification actions, idempotency records, delivery outboxes, checkout attempts,
leases, and completion effects. The Alembic chain through `20260801_11` is the
authoritative production schema.

### 13. Trigger sources

Both trigger sources answer one question — should_fire(item) -> bool. Hosted-link
renewals hand the orchestrator the normal purchase proposal; manual-required renewals
hand it a notification-only flag with no amount or merchant and never enter the
autonomous purchase path. This shared trigger abstraction lets Teams remain a data
variant instead of a second codebase without automating a provider login.

#### 13.1 Predicted trigger (Restock Home)

```text
predicted_depletion_date = last_purchased_at + typical_cadence_days
days_until_depletion = predicted_depletion_date - today
depletion_condition = days_until_depletion <= TRIGGER_WINDOW_DAYS # default 2
price_condition = price_threshold is set
                  and last_observed_price <= price_threshold
trigger_condition = depletion_condition or price_condition
typical_cadence_days_new = ALPHA * observed_interval_days
                         + (1 - ALPHA) * typical_cadence_days_old

# ALPHA default 0.3
```

First-time items seed `typical_cadence_days` from a transparent public
category prior when one maps honestly, otherwise from the user's estimate.
The checked-in priors are reproducibly extracted aggregate basket intervals,
not personalized predictions or a trained model; EWMA corrects the starting
value as completed purchase cycles accumulate. A real regression/time-series
model is explicitly deferred to post-hackathon.

When depletion and price conditions fire together, Restock sends one proposal explaining both reasons rather than two notifications for the same item.

#### 13.2 Known-date trigger (Restock Teams)

```text
days_until_renewal = renewal_date - today
trigger_condition = days_until_renewal <= TRIGGER_WINDOW_DAYS

# default 2

proposed_action = "renew_as_is" if alternate_plan_amount >= current_plan_amount
                  else "switch_to_alternate"
```

No recalibration needed — renewal_date is a fact, not a prediction. This is deliberately the
simpler track, which is exactly why it’s the right second track to add: near-zero additional
orchestrator complexity for direct coverage of the brief’s “manage a subscription” and “procure
software” examples.

### 14. Orchestrator agent

Built on OpenAI’s Agents SDK (not Agent Builder — deprecated June 2026, shutting down Nov
30, 2026). Runs as a scheduled tool-using loop, not a request/response chat handler. Single
agent, not multi-agent — the brief’s own language (“an AI agent,” “an agent”) is singular both
times it describes what’s judged, not a scope compromise for 48 hours.

Single-model decision: gpt-5.4-mini runs the full orchestrator loop, including notification
generation and the Restock Teams renew-vs-switch comparison. This is deliberate: one
verified-reliable model removes a constrained-quota failure mode from the live demo, while
these judgment calls are already bounded by code-level Guardrails and explicit user approval.

Guardrails and human-in-the-loop — named SDK primitives, not prompt promises:
spend caps are implemented as the Agents SDK’s tool-input Guardrail, validating
the request before a Prava Session call. Price deviation, exact-SKU/no-substitution,
idempotency, and plan-switch approval are code-owned workflow checks, not additional
SDK Guardrails. The approval tool uses the SDK’s resumable human-in-the-loop flag;
after approval, Prava payment results are resolved by polling rather than a webhook.

Tool surface:

```text
check_trigger_status() -> list[TrackedItem]
# items where trigger_condition is true (predicted OR known-date)
# and no pending Intent exists
request_prava_intent(merchant, amount, item_id, constraints) -> Intent
# gated by a Guardrail checking per_item_cap / per_transaction_cap /
# monthly_cap before Prava Session creation
notify_user(item_id, message, actions=["approve","adjust","skip"]) -> None
# copy and trigger decision both use the single gpt-5.4-mini configuration
await_passkey_approval(intent_id) -> MandateResult
# the SDK's human-in-the-loop resumable-approval mechanism
complete_merchant_checkout(mandate_id, item_id) -> Transaction
log_event(event_type, payload) -> None
```

Policy constraints — spend caps are complete; live merchant safeguards remain
Phase 8 proof items:

- Never call `complete_merchant_checkout` without a `MandateResult` showing passkey approval.
- Never propose an amount exceeding `per_item_cap` or `monthly_cap` — a Guardrail on `request_prava_intent`, not a prompt instruction the model could get wrong.
- If a fresh exact-SKU quote increases at all or decreases by more than 15%
  from the approved quote, or the item is out of stock, the workflow must re-route to the user rather
  than proceed. This remains a Phase 8 live-boundary proof item, not an Agents
  SDK Guardrail claim.
- For known-date items: never auto-select `switch_to_alternate` without explicit approval, even when strictly cheaper — a plan switch can carry consequences (feature loss, contract terms) the amount alone doesn’t capture.

### 15. End-to-end sequence (happy path)

1. Scheduler tick calls check_trigger_status().
2. Triggered item → request_prava_intent(...) → local Intent created and a Prava Session requested.
3. notify_user(...) — proactive message, no user-initiated request.
4. User taps Approve → passkey challenge; the backend polls the Session payment
result until the one-time credential is ready, rejected, expired, or times out.
5. Merchant MCP creates/revalidates the exact cart; the consume-once credential
is handed to the separate browser-payment boundary.
6. The terminal merchant result is reconciled and reported back to Prava before
a Transaction is finalized. Home cadence updates only after completion.
7. log_event appends the trail; UI shows the updated audit/savings log.

Branches: Skip → Intent.status = rejected, cooldown before re-check. Adjust → new
proposal, loop back to step 2. Out-of-stock/price-tolerance breach/plan-switch proposal
→ re-route to notify_user, never auto-resolve.

### 16. External integration contracts

Prava’s current server-side contract is Session → passkey → payment-result
polling → one-time credential → terminal status report. `Intent` remains
Restock’s internal proposal record; it is not a separate Prava object.

```text
create_session(user_id, user_email, total_amount, currency, merchant_name,
               merchant_url, merchant_country_iso2, product_description,
               unit_price, product_id=None, quantity=1,
               effective_until_minutes=15)
  -> {session_id, session_token, iframe_url, order_id, expires_at}
# create_intent(...) is the retained compatibility wrapper
await_mandate(session_id)
  -> {mandate_id, txn_ref_id, credential_reference, scope, approved_at}
     | reject | expire
# polls /v1/sessions/:sessionId/payment-result
report_status(session_id, txn_ref_id, txn_status,
              authorization_code=None, response_code=None) -> result
# called after every terminal checkout attempt
```

Merchant/billing execution keeps the compatibility contract below, while its
real Home implementation is split internally into MCP quote/cart work and a
Playwright payment executor:

```text
complete_checkout(credential_reference, merchant_sku_id, amount, idempotency_key) > { merchant_order_id, status }
```

Home: merchant access is confirmed; real Zepto/Swiggy catalog/cart/quote work
does not imply a real final charge. That payment boundary remains independently
mode-tagged and operator-gated. Teams: one-time hosted invoice quoting is built;
unattended fulfillment remains disclosed simulation. Prava now documents
active-mandate charging, but Restock has not integrated or sandbox-proved that
separate charge/report boundary, so recurring Teams charging remains disabled.

OpenAI Agents SDK: standard tool-calling loop; verify current model pricing/latency at build
time rather than assuming.

### 17. Non-functional requirements

| Requirement | Target |
| --- | --- |
| Notification-to-confirmation latency (excluding user response time) | < 5s |
| Mandate creation success rate (sandbox) | ≥ 99% across test runs |
| Unauthorized transactions | 0 — code-owned mandate gate, pending live-boundary proof |
| Spend-cap breaches | 0 — hard guardrail |
| Idempotent checkout | Every call keyed by `intent_id`; live-boundary proof required |
| Secrets handling | Environment variables only; never committed |

### 18. Error handling and edge cases

| Scenario | Handling |
| --- | --- |
| Merchant reports out-of-stock | Notify user; no transaction created; re-checked next cycle |
| Price increases at all, or decreases >15% from the approved quote | Require explicit re-approval |
| Cheaper alternate plan available (Teams) | Propose the switch; never auto-select it |
| Mandate/passkey rejected or times out | `Intent.status = expired`; item re-enters normal check cycle |
| Merchant/billing API error or timeout | Retry with backoff (max 2), then notify user and log the failure |
| Duplicate trigger while an Intent is pending | Suppress duplicate notification |

### 19. Testing strategy

- Unit tests: trigger math for both tracks (predicted-date recalibration; known-date comparison) against fixed fixtures; tool functions against mocked Prava/merchant responses.
- Integration test: one full sandbox run of the happy path for each track, plus one
rejected-mandate path, before demo day.
- Demo rehearsal: a timed run-through fitting inside the 5-minute submission video window.


## Part III — Trust & Operations

### 20. Privacy and data handling

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

Design commitments:

- Data minimization: store item name, category, cadence/renewal data, last-purchase or current-plan amount — nothing else.
- Purpose limitation, stated explicitly: data is used only to predict a trigger, never for ad targeting or resale.
- Consent re-confirmed per transaction: the passkey approval on every purchase is a per-transaction consent checkpoint, stronger than a one-time signup checkbox.
- Visible, deletable data: a “here’s what we track and why” screen with a working delete button, per item and account-wide.
- Sensitive-category flagging: items marked sensitive (e.g., medication) are excluded from any analytics, even anonymized.
- Retention limits: a rolling window (e.g., 12 months) on the audit log rather than indefinite retention.
- Age-gated to 18+: DPDP’s strict minors’ provisions are out of scope for a 48-hour build.

### 21. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| **RESOLVED** — Prava markets “US & SEA” coverage, but its skill repo ships Zepto/Swiggy (India) integrations — previously unclear if live for hackathon sandbox use | Merchant flows are confirmed buildable per Prava’s team directly, not just the docs. Shubham Kukreti confirmed via Discord on 17 July 2026: "Merchants aren't restricted, so you can build flows for things like Zepto or Swiggy." |
| Real-card testing (sandbox or production) requires a Visa card issued in US/Canada/Hong Kong/Singapore, which the builder does not currently hold | Use Prava's documented sandbox test cards for the Session/passkey/credential proof. They have no geography restriction, although the currently assigned card is separately provider-blocked at Security Check Failed / No Passkey. Their expected decline at a real merchant is not a successful live charge. Defer real-money testing to an operator-approved controlled purchase; Prava has offered to help source a compatible card at that stage. |
| Forecasting looks like a science project and eats the clock | Ship the day-counter first; add smoothing only if time remains after the payment flow works end-to-end |
| Passkey/biometric approval doesn’t demo well on a shared screen | Scripted, clearly-labeled fallback ready for the recorded demo |
| Judges read “proactive” as unsafe or spammy | Make spend caps and the approve/adjust/skip step visually central — control is the pitch, not autonomy for its own sake |
| Teams track reads as “not really using Prava” since billing is mocked | State plainly: the trigger and shared Prava Session integration are real code, the currently assigned card is provider-blocked before mandate/passkey proof, and SaaS fulfillment remains simulated until its separate boundary is integrated and verified |

**Merchant choice:** Zepto was confirmed as an explicit, deliberate choice
(Prava, Discord, 22–23 July 2026: "any merchant you can target totally on your
use-case") because it fits the grocery/consumables narrative better than a
restaurant-delivery platform like Zomato or Swiggy's core product.


### 22. Deployment for the hackathon

The implementation separates the FastAPI service, leased scheduler worker, and
optional channel listener. SQLite is the local/demo default. Production uses
the Postgres-compatible repository and Alembic migrations through
`20260801_11`; the public deployment already uses managed Postgres. A separate
worker, final production secrets, and a restore drill against the final target
remain external cutover gates. Real-money checkout stays disabled until an
operator explicitly authorizes a controlled purchase.

### 23. Observability

A structured, sanitized log line is emitted at every workflow transition.
User-facing audit and notification compatibility stores use SQLite locally;
the resumable production path uses Postgres-compatible repositories with
Alembic migrations through `20260801_11`. Runtime request logs, metrics, and
the user-facing audit/savings feed remain separate, and none may contain raw
credentials or approval URLs.


## Part IV — Business & Execution

### 24. Success metrics for the demo

- One end-to-end Prava flow per track, agent-initiated, with no user-typed purchase request. Success = (1) intent/session created, (2) one-time credential generated, (3) credential correctly populated into the real checkout form via browser automation, (4) Pay attempt fails specifically due to test-card status — not due to a bug in steps 1–3. Sandbox transactions cannot succeed against any real merchant because the test card will be declined; this is expected and fully acceptable for judging. This remains the target bar: the currently assigned sandbox card is still blocked earlier at Prava's Security Check Failed / No Passkey step and is not claimed as an achieved end-to-end result.
- At least 2 of the 3–5 Home items reordered autonomously during the judged walkthrough,
plus the one Teams subscription renewal proposal.
- A visible, believable savings number in the audit log for both tracks.
- Judges can articulate, unprompted, how this differs from “just another shopping bot.”

### 25. Judging-criteria alignment

| Criterion | How Restock addresses it |
| --- | --- |
| Works | End-to-end Prava transaction, live or sandboxed, on both tracks |
| Solves a clear problem | Stockouts/over-ordering (Home) and silent overpaying on subscriptions (Teams) — both universal |
| Agent takes meaningful action | Autonomous, condition-triggered purchase — not a chat-mediated single click |
| Handles payment clearly | Prava mandate flow front and center, spend caps visible |
| Could become a real product | Clear monetization below, reuses Prava’s own published merchant skills |
| OpenAI usage | Agents SDK orchestrator (not the deprecated Agent Builder) |
| Prava integration | Core to the product on both tracks, not bolted on |
| Consumer experience | Restock Home |
| B2B value | Restock Teams — directly answers the brief’s own “manage a subscription” / “procure software” examples |
| Startup potential | Real recurring-revenue and affiliate paths, see below |

### 26. Business model

Restock Home: small monthly subscription per household (₹99–199), or a cut of avoided-stockout savings, or affiliate revenue from quick-commerce partners on autonomous reorders.
Restock Teams: a cut of savings actually found (e.g., 20% of first-year savings from a caught
price increase or right-sized seat count), or a flat per-seat monthly fee once a team tracks more
than a handful of subscriptions.

### 27. Roadmap beyond the hackathon

Each v1 limitation has a specific resolution path, not just a “later” label — sequenced by impact
vs. effort rather than by how they’re listed in Appendix A.

**Built and live-query capable:** Restock Home fires on predicted depletion or a user-set price threshold, whichever condition is met first, and combines both reasons into one notification when they coincide. The Phase 8 Zepto adapter now reads the current price for the exact product-variant ID through Zepto's live MCP search and refuses similar-product substitution. Seeded/offline demonstrations retain deterministic prices; production mode uses the live exact-SKU path.

1. **Built foundation; provider activation gated:** Notification delivery
   (highest priority — this is the product’s core value prop, not
   a nice-to-have). A web dashboard nobody has open defeats the entire “reaches you before
   you ask” thesis. The PWA, Slack adapter, WhatsApp Cloud API adapter, and
   Capacitor wrappers are built. The PWA is the launch/submission surface;
   Slack deployment with rotated credentials, physical-device verification,
   and store publication remain external activation gates. WhatsApp activation
   is optional post-launch work, not a launch or submission gate.
2. **One-time invoice path built; recurring integration is pending:** Real SaaS billing integration. The mock exists because a subscription renewal is
merchant-initiated (recurring), not agent-initiated (one-time) like a grocery reorder — a genuinely different transaction shape from what’s built. Two paths:
   - Path A (platform contract now documented; Restock integration pending):
     Prava documents `POST /v1/mandates/{id}/charge` for active mandates,
     idempotent references, and merchant/cap enforcement. Restock must still
     implement and sandbox-prove the charge plus terminal-report flow before
     advertising recurring Teams billing.
   - Path B (buildable now, no new dependency): keep the existing agent-initiated, one-time-credential flow exactly as built, and have Restock pay the vendor’s hosted
invoice/payment link directly two days before the known renewal date — same architecture, different merchant_sku_id target. This is the one to actually build first.
3. **Data foundation built; production ML still gated:** Real forecasting model. The constraint is data volume, not modeling difficulty — a
single household doesn’t generate enough history to train anything meaningful per-user for
months. Sequence: keep logging (item, actual_interval, predicted_interval) from
day one even while running on plain exponential smoothing, so training data exists when it’s
needed; once there’s a real user base, train a shared model at the category level (coffee-type
items, paper-type items — where the volume actually is) with a small per-user bias term for
personalization, rather than per-user models that will always be data-starved. Keep the EWMA
as the explainable production baseline; keep category priors and user estimates
as cold-start inputs for any new item regardless of how mature the overall
system gets — every new item starts cold no matter what.
4. **Tenant controls built; payment semantics still gated:** Household and
Organization tenants, memberships, roles, invitations, consent, and
multi-approver policy exist. They do not turn Prava’s one-time mandate into a
shared or recurring payment authority. Production enablement still requires
cross-tenant review and real-world validation of approval policy.
Also on the roadmap: expand merchant coverage beyond Zepto/Swiggy as Prava adds MCP
skills; combine the predicted and known-date triggers on the same item where relevant (buy
on whichever fires first) — directly one-ups Amazon AutoBuy’s single-signal model.

### 28. Solo execution plan for the 48 hours

The project has one builder. Work is sequenced, not divided into fictional team
roles:

1. Re-prove the Prava sandbox Session/passkey/polling path.
2. Re-prove the exact-SKU merchant quote and browser-payment boundary.
3. Capture the truthful real/simulated evidence matrix and safety tests.
4. Polish and rehearse the PWA/channel demo only after those boundaries are stable.

### 29. Immediate action items

1. Freeze and record the pre-event commit boundary before the official window.
2. At event start, re-prove Prava Session/passkey/polling and capture sanitized evidence.
3. Complete Phase 8 live-boundary tests for exact-SKU, price deviation,
   substitution refusal, idempotency, reconciliation, and report-status.
4. Keep `/capabilities`, UI badges, README, and submission language identical
   about every real, simulated, and provider-unactivated boundary.

## Appendices

### A. Known limitations and non-goals (v1)

Resolution paths for each of these are in §27 (Roadmap) — this list is deliberately just the “not
done yet” inventory, not the plan to close it.

- No real ML forecasting model — deterministic exponential smoothing only, for the
predicted-trigger track.
- No real SaaS billing-portal fulfillment — hosted-link items use the bounded
  approval workflow but finish at a disclosed mock; `manual_required` items
  produce a notification only and never create a Prava purchase proposal.
- Household/Organization tenants and approval policies are implemented, but
  reusable mandate charging is not enabled until Restock integrates and proves
  the documented mandate-charge boundary under the same approval policy.
- Capacitor Android/iOS wrappers are implemented; physical-device validation,
  store enrollment, and publication remain launch gates.
- Merchant adapters cover Zepto and Swiggy catalog/cart quoting. Final card
  payment remains an explicit browser boundary and defaults to disclosed
  simulation; Teams supports one-time invoice quoting with disclosed fulfillment.

### B. Open questions — verify before/during build

- RESOLVED — Model selection for the orchestrator: one verified-reliable model,
gpt-5.4-mini, for the full loop including notification copy and the Teams plan-comparison
decision. The hard constraints remain enforced by code-level Guardrails. See §14.
- RESOLVED — Prava has no Python SDK for this server path. Restock implements
  the documented Session REST API and polls payment results; there is no mandate webhook.
- RESOLVED — Zepto and Swiggy MCP tool surfaces are represented by the locked
  adapters; provider OAuth/mobile-OTP activation remains deployment-specific.
- PROVIDER-BLOCKED — Prava's sandbox test data creates the hosted Session, but
  the currently assigned card stops at Security Check Failed / No Passkey.
  Passkey provisioning or the missing enrollment step must be resolved before
  claiming a completed Session/passkey proof; no merchant charge is claimed.
- Whether Prava mandates expose a configurable TTL/expiry we should set explicitly on
Intent creation, or whether it’s fixed by Prava.
- RESOLVED AT PLATFORM CONTRACT; RESTOCK INTEGRATION PENDING — Prava now
  documents active-mandate charging and terminal status reporting. Restock
  Teams uses Path B or the disclosed mock until that new boundary is
  implemented and sandbox-proved under Restock's explicit approval policies.

### C. Glossary

- Intent — internal record of a proposed purchase, before user approval.
- Mandate — Prava’s record of user-approved, scoped permission to charge a specific merchant a bounded amount.
- Credential reference — Restock’s opaque handle for a one-time token/CVV set.
  Raw values exist only transiently in the server-side consume-once payment
  boundary and are never persisted or logged.
- Trigger source — the mechanism that decides when a proposal fires: predicted (consumption forecast) or known-date (subscription renewal).
