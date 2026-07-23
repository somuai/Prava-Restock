# Restock — Technical PRD

**Version 1.0 · Prava Agentic Commerce Hackathon, Jul 31–Aug 2, 2026**
**Status:** Pre-build design spec. Companion to `PRD.md` (product rationale) and `SKILL.md` (build guide for coding agents).

---

## 1. Purpose and scope

This document specifies the system Restock actually is: components, data contracts, sequence flow, and the non-functional bar it needs to clear. `PRD.md` answers *why*; this answers *exactly how*. Anyone picking up implementation should read this before writing code, and should treat §9 (external integration contracts) as provisional pending a live check against Prava's current SDK reference.

## 2. System context

Four external actors, one system:

- **User** — approves every purchase via passkey; sets spend caps once at onboarding.
- **Restock backend** — the system this document specifies: consumption tracking, orchestration, audit logging.
- **Prava** — payment intent, passkey challenge, mandate issuance, one-time credential. Restock never stores a card number; Prava is the only component that ever sees payment instrument data.
- **Merchant (Zepto / Swiggy, via Prava's published MCP skill)** — receives the one-time credential and fulfills the order.

```
User <──approve/adjust/skip──> Restock Backend <──intent/mandate──> Prava
                                      │
                                      └──credential──> Merchant (Zepto/Swiggy MCP)
```

## 3. Component architecture

| Component | Responsibility | Notes |
|---|---|---|
| **Trigger engine** | Two interchangeable trigger sources feeding the same downstream pipeline: **predicted** (consumption forecast, Restock Home) and **known-date** (subscription renewal date, Restock Teams) | Deterministic, no ML model for v1 — see §6 |
| **Orchestrator agent** | Tool-using loop (OpenAI Agents SDK) deciding what/when to propose, handling approve/adjust/skip, sequencing the Prava + merchant calls | Runs on a schedule tick; not a chat-request handler; trigger-type-agnostic |
| **Prava client** | Thin wrapper around Prava's SDK — intent creation, mandate status polling, credential retrieval | Isolate all Prava-specific code behind this interface so a real SDK-signature mismatch only requires changing one file |
| **Merchant client** | Wraps the Zepto/Swiggy MCP checkout skill (Home) and a disclosed mock subscription-billing checkout (Teams) | Same isolation principle as the Prava client; both implement the same `complete_checkout(...)` contract — see §9.2 |
| **Audit/notification store** | Persists Intents, Mandates (references only, never raw credentials), Transactions, and the user-facing audit log | See §5 for schemas |
| **UI (chat surface)** | Displays proactive notifications, approve/adjust/skip controls, and the audit/savings log | The guaranteed surface is the disclosed WhatsApp-style/Slack-style PWA. A real single-workspace Slack Bolt adapter and a Meta test-number webhook/template adapter are implemented; whether the external accounts are configured is exposed at runtime. Meta publishes template review guidance of up to 24 hours, but no fixed business-verification SLA is claimed. |

See `PRD.md` §10, "Distribution and surface," for why these user-facing surfaces remain independent of the merchant apps that Restock calls at the backend.

## 4. Design principles

1. **Payment data never touches our storage.** Every field we persist about a transaction is a reference (mandate ID, credential reference, transaction ID) — never a card number, never raw passkey material.
2. **Every autonomous action is reversible or bounded.** Spend caps are hard limits enforced before a Prava intent is even created, not just checked afterward.
3. **The orchestrator proposes; it never silently substitutes.** A price or availability change beyond a configured tolerance always routes back to the user, never auto-resolves.
4. **Idempotency by construction.** Every merchant checkout call carries the originating `intent_id` as an idempotency key — a retried network call must not double-charge.

## 5. Data model

```
User
  user_id            UUID (pk)
  display_name       string
  prava_account_ref  string        # Prava's own account/wallet reference, not a card
  monthly_cap        decimal
  per_item_cap       decimal
  per_transaction_cap decimal
  created_at          timestamp

TrackedItem                     # base entity — both tracks share this shape
  item_id             UUID (pk)
  user_id             UUID (fk -> User)
  name                string
  track               enum(home, teams)          # which product surface this belongs to
  trigger_type        enum(predicted, known_date) # see §6 — determines which fields below apply
  category            enum(grocery, stationery, health, saas_subscription, other)
  sensitive_flag       bool          # user-marked; excluded from any analytics
  preferred_merchant   enum(zepto, swiggy, mock_subscription_billing, mock)
  merchant_sku_id      string
  merchant_address_ref string | null  # opaque saved-address ID; never a raw address/phone
  quantity             integer | null # positive exact quantity for Home quotes
  status               enum(active, paused, deleted)

  # populated only when trigger_type = predicted (Restock Home)
  typical_cadence_days float
  last_purchased_at    date
  last_purchase_amount decimal
  price_threshold      decimal | null  # user-set; fire when observed price is at/below this
  last_observed_price  decimal | null  # latest price returned by the merchant price check

  # Home quote context: merchant_address_ref and quantity are required before
  # a real quote, optional for legacy/mock items, and unused for known-date items. Device IDs remain
  # deployment secrets/configuration and are never persisted on TrackedItem.

  # populated only when trigger_type = known_date (Restock Teams)
  renewal_date          date          # the actual, known billing date — not predicted
  current_plan_amount   decimal
  alternate_plan_amount decimal       # e.g. annual-plan price, for the switch-and-save proposal
  alternate_plan_label  string

Intent
  intent_id           UUID (pk)
  item_id             UUID (fk -> TrackedItem)
  proposed_amount     decimal
  proposed_merchant   string
  status              enum(pending_approval, approved, adjusted, rejected, expired)
  created_at          timestamp

Mandate                # reference only — Prava owns the real object
  mandate_id           string (pk, Prava-issued)
  intent_id            UUID (fk -> Intent)
  credential_reference string        # opaque, one-time, never a raw card number
  scope_merchant       string
  scope_max_amount     decimal
  scope_expiry         timestamp
  passkey_approved_at  timestamp

Transaction
  transaction_id       UUID (pk)
  mandate_id           string (fk -> Mandate)
  item_id              UUID (fk -> TrackedItem)
  merchant_order_id    string
  amount               decimal
  status               enum(completed, failed, disputed)
  completed_at         timestamp

AuditLogEntry
  log_id               UUID (pk)
  user_id              UUID (fk -> User)
  event_type           enum(notification_sent, approved, adjusted, skipped,
                             transaction_completed, transaction_failed,
                             item_deleted, data_exported)
  payload              JSON          # minimal — item name/amount/merchant, never payment data
  timestamp            timestamp
```

## 6. Trigger sources (v1 — deliberately simple, both implement the same interface)

Both trigger sources answer one question — `should_fire(item) -> bool` — and hand the orchestrator the same shape of output (item, proposed amount, proposed merchant). Everything downstream of that call is identical for both tracks. This is the one abstraction worth getting right early, because it's what lets Restock Teams exist as a data variant instead of a second codebase.

### 6.1 Predicted trigger (Restock Home — consumption forecast)

```
predicted_depletion_date = last_purchased_at + typical_cadence_days
days_until_depletion     = predicted_depletion_date - today
depletion_condition      = days_until_depletion <= TRIGGER_WINDOW_DAYS   # default 2
price_condition          = price_threshold is set
                           and last_observed_price <= price_threshold
trigger_condition        = depletion_condition or price_condition

# recalibration, applied every time an item is actually reordered
# (autonomous or manual), exponential smoothing:
typical_cadence_days_new = ALPHA * observed_interval_days
                          + (1 - ALPHA) * typical_cadence_days_old       # ALPHA default 0.3
```

**First-time items** seed `typical_cadence_days` from a transparent category prior or a user-provided estimate at onboarding. Personal EWMA observations replace the prior as completed purchases accumulate.

**Cold-start priors:** Cold-start estimates are seeded from public aggregate reorder-interval data (Instacart Market Basket dataset, Kaggle, CC0/research-use) at the category level, not personalized — per-user recalibration via EWMA remains the mechanism that adapts to actual behavior. Categories with a direct Instacart mapping (`grocery` → 11.0 days, `health` → 18.0 days) use the dataset median; categories without a match (`stationery`, `saas_subscription`, `other`) fall back to the user-provided estimate. This is deliberately not a trained model — see `PRD.md` §27 for why a real forecasting model is post-hackathon scope.

If depletion and price conditions become true in the same check, `propose(item)` emits one notification containing both reasons. In `HOME_MERCHANT_MODE=real`, the Phase 8 Zepto adapter queries Zepto's live MCP search for the tracked product's exact product-variant ID, converts the returned minor-unit price to INR, and refuses a nearby result rather than silently substituting it. `HOME_PAYMENT_MODE` is independent: it can remain `disclosed_mock` while catalog/cart/quote operations are real, and capabilities plus audit events report the two modes separately. Seeded/offline tests retain the deterministic adapter.

**Production baseline:** EWMA remains authoritative. Consent-gated observations, deletion, category priors, and an offline comparison harness are built. A regression/time-series candidate remains feature-flagged until it materially beats EWMA on MAE, trigger precision, missed depletion, and action rate without weakening explainability.

### 6.2 Known-date trigger (Restock Teams — subscription renewal)

```
days_until_renewal = renewal_date - today
trigger_condition  = days_until_renewal <= TRIGGER_WINDOW_DAYS   # default 2

# no recalibration needed — renewal_date is a fact, not a prediction.
# the only "intelligence" here is the proposal itself:
proposed_action = "renew_as_is" if alternate_plan_amount >= current_plan_amount
                  else "switch_to_alternate"   # e.g. annual plan, cheaper tier
```

This is deliberately the simpler of the two trigger sources — there's no forecasting error to manage, which is exactly why it's the right second track to add inside a 48-hour window: it reuses the entire downstream pipeline (§7, §8) for close to zero additional orchestrator complexity, while directly answering the brief's "manage a subscription" and "procure software" examples.

## 7. Orchestrator agent

Built on OpenAI's **Agents SDK** (not Agent Builder — deprecated June 2026). Runs as a scheduled tool-using loop, not a request/response chat handler. Single agent, not multi-agent — confirmed against the brief's own language ("an AI agent," "an agent," singular both times), not just a 48-hour scope call.

**Single-model decision:** use **`gpt-5.4-mini`** for the full orchestrator loop, including `notify_user` copy and the Restock Teams plan-comparison decision (renew-as-is vs. switch-to-alternate). This is not only a cost choice: one model already verified against the project account removes a constrained-quota dependency that could break the live demo. The two apparent judgment calls are narrow and structured, while spend caps, no-silent-substitution, and explicit approval for plan switches are enforced by code-level Guardrails and human-in-the-loop controls rather than relying on greater model capability.

**Guardrails and human-in-the-loop — named SDK primitives, not hand-rolled checks:**

- Spend caps and the "never silently substitute" rule are implemented as the Agents SDK's **Guardrails** primitive — single-purpose tripwires that validate tool inputs/outputs concurrently with the agent, not something the model self-polices via its instructions. A guardrail rejecting an out-of-cap `request_prava_intent` call happens in code the model doesn't control, regardless of what the model decided.
- The passkey-approval pause is the SDK's built-in **human-in-the-loop** mechanism (resumable approval flow), not a custom polling loop — `await_passkey_approval` is where the run pauses for the real-world passkey callback before resuming.

**Tool surface:**

```
check_trigger_status() -> list[TrackedItem]
    # items where trigger_condition is true (predicted OR known-date, per §6)
    # and no pending Intent exists — trigger-type-agnostic from here on

request_prava_intent(merchant: str, amount: decimal, item_id: UUID,
                      constraints: dict) -> Intent
    # creates local Intent (status=pending_approval), calls Prava intent API — see §9.1
    # gated by a Guardrail checking per_item_cap / monthly_cap before the call proceeds

notify_user(item_id: UUID, message: str,
            actions: list[str] = ["approve", "adjust", "skip"]) -> None
    # the proactive push — this is the product's entire differentiator;
    # it must fire without any user-initiated request in the same session
    # generated by the same gpt-5.4-mini configuration as the trigger loop

await_passkey_approval(intent_id: UUID) -> MandateResult
    # blocks on Prava's passkey callback/webhook via the SDK's human-in-the-loop
    # resumable-approval mechanism — see §9.1

complete_merchant_checkout(mandate_id: str, item_id: UUID) -> Transaction
    # calls the merchant client (§9.2) using the Prava-issued credential

log_event(event_type: str, payload: dict) -> None
    # writes an AuditLogEntry — payload must never include raw payment data
```

**Guardrail constraints — enforced in code, not just stated in the system prompt:**

- Never call `complete_merchant_checkout` without a `MandateResult` showing passkey approval.
- Never propose an amount exceeding `per_item_cap` or that would exceed `monthly_cap` for the period — a Guardrail on `request_prava_intent`, not a prompt instruction the model could get wrong.
- If merchant-reported price deviates from `last_purchase_amount` by more than a configured tolerance (e.g., 15%), or the item is out of stock, do not proceed silently — re-route to `notify_user` for explicit re-approval.
- For known-date items (Restock Teams): never auto-select `switch_to_alternate` without explicit approval, even when it's strictly cheaper — a plan switch can have consequences (feature loss, contract terms) the amount alone doesn't capture.

## 8. End-to-end sequence (autonomous purchase, happy path)

1. Scheduler tick calls `check_depletion_status()`.
2. For each triggered item, orchestrator calls `request_prava_intent(...)` → local `Intent` created (`pending_approval`), Prava intent request sent.
3. Orchestrator calls `notify_user(...)` — proactive message with item, amount, merchant, and Approve/Adjust/Skip.
4. User taps **Approve** → device-side passkey challenge (Prava's client flow) → Prava registers a `Mandate` and returns a one-time credential reference via callback.
5. `await_passkey_approval` resolves; local `Mandate` record stored (credential *reference* only).
6. Orchestrator calls `complete_merchant_checkout(...)` with the mandate reference; merchant client invokes the Zepto/Swiggy MCP skill.
7. Merchant confirms order → local `Transaction` created (`completed`); `TrackedItem.last_purchased_at` and `typical_cadence_days` updated per §6.
8. `log_event` appends the full trail; UI shows the updated audit/savings log.

**Branch — Skip:** `Intent.status = rejected`; re-check deferred by a configurable cooldown (default 3 days); no `Transaction` created.
**Branch — Adjust:** new proposed amount/quantity; loop back to step 2 with the updated `Intent`.
**Branch — merchant out-of-stock or price outside tolerance:** do not auto-substitute; re-route to `notify_user` for explicit re-approval (§7 constraint).

## 9. External integration contracts

### 9.1 Prava (conceptual — verify exact method signatures at build time)

Conceptually: **Session → Passkey → Mandate → one-time credential.** Do not hardcode API paths or class names from this document — pull the current `PravaSDK` class reference and session API reference from the `prava-sdk-integration` skill folder in `Prava-Payments/prava-skills`, and use their documented sandbox test cards for all development. Treat this section as an interface contract our own `Prava client` component must satisfy, not a literal API spec. Prava does not expose a mandate webhook; poll to fetch successful credential creation (Prava's exact words: "polling to fetch successful credential creation; that's the reliable way to integrate"):

```
create_session(merchant, amount, item_description, constraints) -> session_ref
    # Prava's term is Session; what we previously called Intent maps directly
    # to this — no separate object exists on their side.
await_mandate(session_ref) -> { mandate_id, credential_reference, scope, approved_at } | rejected | expired
    # Polling only — Prava does not expose a mandate webhook. Poll to fetch
    # successful credential creation; that's the reliable way to integrate.
```

**Known platform fact for production planning:** Prava requires a Visa card issued in the US, Canada, Hong Kong, or Singapore for any real card used in the flow, whether in sandbox or production. Prava's own documented sandbox test cards are unaffected and complete a full simulated flow with no geography restriction; use those for all hackathon build and demo work. See the resolved merchant-access and real-card-testing entries in `PRD.md` §21, "Risks and mitigations."

### 9.2 Merchant / billing checkout (Zepto / Swiggy for Home; mocked billing for Teams)

Reuse Prava's own published checkout skills (`prava-merchants-checkout/` in the same repo) for Restock Home rather than hand-rolling merchant integration. Contract every implementation must satisfy — same interface regardless of what's behind it:

```
complete_checkout(credential_reference, merchant_sku_id, amount, idempotency_key) -> { status, merchant_order_id, charged_amount, currency, retryable, execution_mode }
```

**Restock Home implementation:** the official Zepto MCP integration now covers OAuth, saved-address selection, product/cart tools, exact-price preview, and payment-status reconciliation. Zepto publishes no dedicated merchant payment sandbox, so the final live-money payment-link execution defaults to `disclosed_mock`. Real execution is a separate operator-controlled mode requiring a compatible card and controllable browser; it is never silently enabled. The Prava sandbox approval and Zepto merchant integration are real, while the final charge boundary is disclosed.

Real Home proposals must be based on a fresh exact-cart quote for the tracked `merchant_sku_id`, positive `quantity`, and opaque `merchant_address_ref`. Initial quoting prepares and verifies the exact cart before preview; pre-checkout revalidation previews the already-prepared cart again. The Zepto device ID is supplied only through deployment configuration (`ZEPTO_DEVICE_ID`) and must never be persisted in `TrackedItem`, logs, or API payloads. Merchant clients remain injected so credential-free tests cannot make live calls by accident.

**Restock Teams:** real OAuth into a SaaS vendor's billing portal (Stripe Billing, Chargebee, etc.) isn't realistic in 48 hours regardless of sandbox access, so `merchant/mock_subscription_checkout.py` is the intended implementation from the start, not a fallback — implement it against the same `complete_checkout(...)` contract so the orchestrator and Prava mandate flow genuinely don't know or care which track they're serving. Disclose this plainly in the submission: the renewal date and the Prava mandate are real, the billing-portal call is simulated.

### 9.3 OpenAI Agents SDK

Standard tool-calling loop; no fine-tuning required for the hackathon scope. Model selection should favor the fastest model that reliably respects the hard constraints in §7 — verify actual latency/cost against current OpenAI pricing at build time rather than assuming.

## 10. Non-functional requirements

| Requirement | Target |
|---|---|
| Notification-to-confirmation latency (excluding user response time) | < 5s |
| Mandate creation success rate (sandbox) | ≥ 99% across test runs |
| End-to-end success definition | (1) session created, (2) credential generated, (3) credential populated into real checkout form, (4) Pay attempt fails due to test-card status — not due to a bug in steps 1–3 |
| Unauthorized transactions (no valid passkey-approved mandate) | 0 — hard guardrail, not a target |
| Spend-cap breaches | 0 — hard guardrail |
| Idempotent merchant checkout | Every call keyed by `intent_id`; retried calls must not double-charge |
| Secrets handling | Prava/OpenAI keys in environment variables only; never committed to the repo |

## 11. Error handling and edge cases

| Scenario | Handling |
|---|---|
| Merchant reports out-of-stock | Notify user with the situation; no transaction created; item re-checked next cycle |
| Price deviates >15% from last purchase | Do not auto-proceed; require explicit re-approval (§7) |
| Mandate/passkey rejected or times out | `Intent.status = expired`; item re-enters the normal check cycle |
| Merchant API error/timeout | Retry with backoff, max 2 attempts, then notify user of failure and log it |
| Duplicate trigger while an Intent is already pending for that item | Suppress duplicate notification |

## 12. Testing strategy

- **Unit tests:** forecasting math (predicted date, recalibration formula), depletion-only/price-only/both/neither trigger behavior, exact-SKU Zepto price normalization, refusal of similar-product substitution, and tool functions against mocked Prava/merchant responses. A read-only integration check verifies the same price path against Zepto's live MCP server; CI uses deterministic responses and no merchant credentials.
- **Integration test:** at least one full sandbox run of the happy path (steps 1–8 above) and one rejected-mandate path, before demo day.
- **Demo rehearsal:** a timed, scripted run-through matching `demo/script.md` (see `SKILL.md`), fitting inside the 5-minute submission video window.

## 13. Privacy and data handling

Full detail in `PRD.md` §14 — summary: payment data privacy is structural (Prava never lets us see a card number); behavioral data (consumption patterns) gets explicit data minimization, purpose limitation, a visible "what we track + delete" screen, sensitive-item flagging, and a bounded retention window on the audit log. Designed toward India's DPDP Act even though full enforcement doesn't land until May 2027.

## 14. Deployment for the hackathon

The implementation now separates the FastAPI web process from a leased scheduler worker and persists the resumable workflow through a Postgres-compatible SQLAlchemy repository with Alembic migrations. SQLite remains the zero-cost local/demo default. Sandbox credentials only; the real-money Zepto path is disabled unless an operator explicitly enables it. Railway/Render configuration must keep the worker separate from web replicas and store all secrets in platform configuration.

## 15. Observability

Every durable state transition writes a sanitized domain-audit entry with run, user, item, trigger reason, and real/simulated mode tags. Raw credentials, approval URLs, payment links, and card fields are structurally rejected. Engineering logs remain separate from the user-facing audit/savings feed.

## 16. Known limitations and non-goals (v1)

*Resolution paths for each of these live in `PRD.md` §15 (Roadmap) — this list is deliberately just the "not done yet" inventory, not the plan to close it.*

- No production ML forecasting model — deterministic EWMA remains the production baseline while consented observation logging and offline benchmarking collect evidence.
- One-time hosted SaaS invoice quoting is implemented; its unattended final payment remains a disclosed mock. Prava's [Report Status documentation](https://docs.prava.space/api-reference/report-status) states that mandates are currently one-time and recurring frequencies are planned, so recurring Teams charging is unsupported and disabled.
- Multi-user Household/Organization membership, roles, invitations, consent, and multi-approver policy are implemented; shared payment approval does not make the underlying one-time Prava mandate reusable or recurring.
- Capacitor Android/iOS wrappers are implemented and simulator-built; store enrollment, physical-device push validation, and publication remain external launch gates.
- The guaranteed submission surface remains the disclosed PWA. The real Slack adapter and Meta test-number adapter must still disclose whether external credentials/setup are active.
- Home adapters cover real Zepto and Swiggy catalog/cart quoting. Zepto's unattended final payment remains disclosed-mock by default; Swiggy card payment remains an explicit browser boundary and is never silently replaced by COD.

## 17. Open questions — verify before/during build

- [x] **RESOLVED** — Model selection for the orchestrator: one verified-reliable model, `gpt-5.4-mini`, for the full loop including notification copy and the Teams plan-comparison decision. This removes a constrained-quota live-demo dependency; hard constraints stay in code-level Guardrails. See §7.
- [ ] Exact `PravaSDK` method signatures for intent creation and mandate polling payload shape.
- [x] **RESOLVED — Zepto merchant contract:** the official skill uses `mcp-remote https://mcp.zepto.co.in/mcp` with OAuth/mobile OTP and publishes tools for saved addresses, product search, cart mutation/view, payment methods, online-order preview/creation, payment status, and order history. Final payment-link execution is operator-controlled because no merchant sandbox is documented.
- [ ] Location of Prava's sandbox test-card/test-data reference in `prava-skills`.
- [ ] Whether Prava mandates expose a configurable TTL/expiry we should set explicitly on `Intent` creation, or whether it's fixed by Prava.
- [x] **RESOLVED — platform fact:** Prava requires a Visa card issued in the US, Canada, Hong Kong, or Singapore for any real card used in the flow, whether in sandbox or production. Prava's own documented sandbox test cards are unaffected and complete a full simulated flow with no geography restriction; use those for the hackathon. For production, Prava has offered: "reach out to us and we'll sort you out with a compatible card".
- [x] **RESOLVED — CONFIRMED UNAVAILABLE:** Prava confirmed (Shubham Kukreti, Discord, 22–23 July 2026) that standing or recurring mandates are not live yet for use — neither in sandbox nor production. Treat everything as one-time per mandate. Restock Teams proceeds on Path B (pay the hosted invoice via one-time credential) or the disclosed mock only, permanently for this hackathon, not pending any answer.

## 18. Glossary

- **Intent** — our internal record of a proposed purchase, before user approval.
- **Mandate** — Prava's record of user-approved, scoped permission to charge a specific merchant a bounded amount.
- **Credential reference** — the opaque, one-time token our system holds in place of any real payment instrument.
