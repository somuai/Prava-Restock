# Restock — Technical PRD

**Version 1.0 · Prava Agentic Commerce Hackathon, Jul 31–Aug 2, 2026**
**Status:** Implemented architecture and remaining activation gates. Companion
to `PRD.md` (product rationale), `SKILL.md` (build guide), and the runtime
`/capabilities` disclosure.

---

## 1. Purpose and scope

This document specifies the system Restock actually is: components, data
contracts, sequence flow, and the non-functional bar it needs to clear.
`PRD.md` answers *why*; this answers *exactly how*. The repository contains a
production-oriented pre-event foundation. Git history records that work;
anything judged as official-window work must be disclosed separately rather
than treating the existing implementation as newly built during the event.

## 2. System context

Four external actors, one system:

- **User** — approves every purchase via passkey; sets spend caps once at onboarding.
- **Restock backend** — the system this document specifies: consumption tracking, orchestration, audit logging.
- **Prava** — Session creation, passkey challenge, one-time mandate/credential
  issuance, payment-result polling, and terminal status reporting. Restock never
  stores a card number. Token/CVV/expiry values temporarily enter only the
  consume-once server-side payment boundary and are never persisted or logged.
- **Merchant** — Zepto/Swiggy MCP supplies catalog/cart/quote/order operations;
  a separate Playwright boundary handles card-form execution.

```
User <──approve/adjust/skip──> Restock Backend <──session/polling──> Prava
                                      │
                                      └──consume-once credential──> Browser payment boundary
```

## 3. Component architecture

| Component | Responsibility | Notes |
|---|---|---|
| **Trigger engine** | Two interchangeable trigger sources feeding the same downstream pipeline: **predicted** (consumption forecast, Restock Home) and **known-date** (subscription renewal date, Restock Teams) | Deterministic, no ML model for v1 — see §6 |
| **Orchestrator agent** | Tool-using loop (OpenAI Agents SDK) deciding what/when to propose, handling approve/adjust/skip, sequencing the Prava + merchant calls | Runs on a schedule tick; not a chat-request handler; trigger-type-agnostic |
| **Prava client** | Implements the documented server-side Session REST API, payment-result polling, consume-once credential custody, and report-status | Prava has no Python SDK for this path; the browser package owns passkey UI |
| **Merchant client** | Zepto/Swiggy MCP catalog/cart/quote operations plus a separate browser-payment executor; one-time invoice support for Teams | Catalog truth and final-payment execution are independently mode-tagged |
| **Workflow and compatibility stores** | SQLite for local/demo; Postgres-compatible SQLAlchemy repositories with Alembic migrations through `20260801_11` for production | Persist references/state only; never raw credentials, approval URLs, or payment links |
| **UI (chat surface)** | Displays proactive notifications, approve/adjust/skip controls, and the audit/savings log | The real Restock PWA is the launch/submission surface. A single-workspace Slack Bolt adapter is implemented; the Meta webhook/template adapter remains optional post-launch. Runtime `/capabilities` discloses which external processes are actually active. |

See `PRD.md` §10, "Distribution and surface," for why these user-facing surfaces remain independent of the merchant apps that Restock calls at the backend.

## 4. Design principles

1. **Payment data never touches durable storage.** Every persisted field is a
reference. A one-time token, dynamic CVV, and expiry may exist briefly in
server memory at the payment executor, is consumed once, and is then deleted.
2. **Every autonomous action is reversible or bounded.** Spend caps are hard limits enforced before a Prava intent is even created, not just checked afterward.
3. **The orchestrator proposes; it never silently substitutes.** Spend caps are
the completed Agents SDK Guardrail. Exact-SKU checks, price-deviation
reapproval, substitution refusal, and checkout idempotency are code-owned
workflow policies whose live merchant-boundary proof remains Phase 8 work.
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
  tenant_id           UUID | null
  name                string
  track               enum(home, teams)          # which product surface this belongs to
  trigger_type        enum(predicted, known_date) # see §6 — determines which fields below apply
  category            enum(grocery, stationery, health, saas_subscription, other)
  sensitive_flag       bool          # user-marked; excluded from any analytics
  preferred_merchant   enum(zepto, swiggy, mock_subscription_billing, mock)
  merchant_sku_id      string
  merchant_address_ref string | null  # opaque saved-address ID; never a raw address/phone
  quantity             integer | null # positive exact quantity for Home quotes
  currency             string         # ISO 4217
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
  renewal_method        enum(hosted_link, manual_required)

Intent
  intent_id           UUID (pk)
  item_id             UUID (fk -> TrackedItem)
  proposed_amount     decimal
  proposed_merchant   string
  currency            string
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
  currency             string
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

This is the public-domain compatibility model, not the complete production
database diagram. The durable schema additionally includes tenants,
memberships, invitations, consent, workflow runs, quotes, notification
actions, idempotency records, delivery outboxes, checkout attempts, leases,
and completion effects. The authoritative production schema is the Alembic
chain through `20260801_11`; Pydantic models and migrations must evolve
together.

## 6. Trigger sources (v1 — deliberately simple, both implement the same interface)

Both trigger sources answer one question — `should_fire(item) -> bool`. A
Teams item with `renewal_method=hosted_link` hands the orchestrator the normal
purchase-proposal shape (item, proposed amount, proposed merchant). A Teams item
with `renewal_method=manual_required` still fires on schedule, but `propose()`
returns a notification-only `flag_for_manual_renewal` action with no amount or
merchant, so it cannot enter the autonomous purchase path. This keeps the
trigger abstraction shared without pretending every provider exposes a safe
payment surface.

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

**Cold-start priors:** Cold-start estimates are seeded from public aggregate reorder-interval data (Instacart Market Basket Kaggle mirror) at the category level, not personalized — per-user recalibration via EWMA remains the mechanism that adapts to actual behavior. The reproducible extractor associates each reordered line with its basket's `days_since_prior_order`; it is a weak basket-interval proxy, not an exact same-SKU survival interval. Categories with a direct mapping (`grocery` and `health`) currently use the extracted 7.0-day median; categories without a match (`stationery`, `saas_subscription`, `other`) fall back to the user-provided estimate. Exact sample counts, averages, medians, method, dataset version, and input SHA-256 hashes are stored in `triggers/category_priors.json`, with reproduction instructions in `docs/data_sources.md`. The specific mirror’s data card lists CC0, while original-source terms require separate review; no raw records are redistributed and the priors do not clear a trained production model. This is deliberately not a trained model — see `PRD.md` §27 for why a real forecasting model is post-hackathon scope.

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

# providers that require a full account-dashboard login are notification-only
proposed_action = "flag_for_manual_renewal" if renewal_method == "manual_required"
```

This is deliberately the simpler of the two trigger sources — there's no forecasting error to manage, which is exactly why it's the right second track to add inside a 48-hour window: it reuses the entire downstream pipeline (§7, §8) for close to zero additional orchestrator complexity, while directly answering the brief's "manage a subscription" and "procure software" examples.

The autonomous path is deliberately limited to subscriptions exposing a hosted,
tokenized payment link. Restock does not store credentials for, or automate
login to, a provider's full account dashboard; those renewals become manual
flags even though their known-date trigger still fires.

## 7. Orchestrator agent

Built on OpenAI's **Agents SDK** (not Agent Builder — deprecated June 2026). Runs as a scheduled tool-using loop, not a request/response chat handler. Single agent, not multi-agent — confirmed against the brief's own language ("an AI agent," "an agent," singular both times), not just a 48-hour scope call.

**Single-model decision:** use **`gpt-5.4-mini`** for the full orchestrator
loop, including `notify_user` copy and the Restock Teams plan comparison. One
verified model removes a constrained-quota dependency. Spend caps use the SDK
Guardrail; the other safety decisions are bounded by deterministic workflow
policies and explicit approval rather than model capability.

**Guardrails and human-in-the-loop — named SDK primitives, not prompt promises:**

- Spend caps are implemented as the Agents SDK's **tool-input Guardrail**. A
  per-item, per-transaction, or monthly-cap rejection occurs before the Prava
  Session request and cannot be overridden by model output.
- Exact-SKU/no-substitution, price deviation, plan-switch approval, mandate
  gating, and idempotency are deterministic workflow policies. They are not
  represented as extra SDK Guardrails, and their live merchant proof belongs
  to Phase 8.
- The passkey-approval pause is the SDK's built-in **human-in-the-loop**
  mechanism. After the user completes the Prava browser flow, Restock resumes
  by polling Prava; no mandate webhook is assumed.

**Tool surface:**

```
check_trigger_status() -> list[TrackedItem]
    # items where trigger_condition is true (predicted OR known-date, per §6)
    # and no pending Intent exists — trigger-type-agnostic from here on

request_prava_intent(merchant: str, amount: decimal, item_id: UUID,
                      constraints: dict) -> Intent
    # creates local Intent (status=pending_approval), calls Prava Session API — see §9.1
    # gated by a Guardrail checking all spend caps before the call proceeds

notify_user(item_id: UUID, message: str,
            actions: list[str] = ["approve", "adjust", "skip"]) -> None
    # the proactive push — this is the product's entire differentiator;
    # it must fire without any user-initiated request in the same session
    # generated by the same gpt-5.4-mini configuration as the trigger loop

await_passkey_approval(intent_id: UUID) -> MandateResult
    # resumable SDK approval boundary, followed by Prava payment-result polling

complete_merchant_checkout(mandate_id: str, item_id: UUID) -> Transaction
    # calls the merchant client (§9.2) using the Prava-issued credential

log_event(event_type: str, payload: dict) -> None
    # writes an AuditLogEntry — payload must never include raw payment data
```

**Policy constraints — spend caps are complete; live merchant safeguards remain
Phase 8 proof items:**

- Never call `complete_merchant_checkout` without a `MandateResult` showing passkey approval.
- Never propose an amount exceeding `per_item_cap` or that would exceed `monthly_cap` for the period — a Guardrail on `request_prava_intent`, not a prompt instruction the model could get wrong.
- If a fresh merchant quote increases above the approved amount at all, or decreases by more than 15%, or the item is out of stock, do not proceed silently — re-route to `notify_user` for explicit re-approval.
- For known-date items (Restock Teams): never auto-select `switch_to_alternate` without explicit approval, even when it's strictly cheaper — a plan switch can have consequences (feature loss, contract terms) the amount alone doesn't capture.

## 8. End-to-end sequence (autonomous purchase, happy path)

1. Scheduler tick calls `check_depletion_status()`.
2. For each triggered item, orchestrator calls `request_prava_intent(...)` →
local `Intent` created (`pending_approval`), then a Prava Session is created.
3. Orchestrator calls `notify_user(...)` — proactive message with item, amount, merchant, and Approve/Adjust/Skip.
4. User taps **Approve** and completes Prava's device-side passkey flow.
5. The backend polls the Session payment-result endpoint until credential
creation, rejection, expiry, or timeout. It creates an opaque local reference;
raw one-time values stay only in the consume-once server boundary.
6. Merchant MCP creates/revalidates the exact cart; the separate Playwright
executor consumes the credential for the payment-form attempt.
7. The terminal result is reconciled and reported to Prava. Only a completed
Home purchase updates cadence.
8. `log_event` appends the full trail; UI shows the updated audit/savings log.

**Branch — Skip:** `Intent.status = rejected`; re-check deferred by a configurable cooldown (default 3 days); no `Transaction` created.
**Branch — Adjust:** new proposed amount/quantity; loop back to step 2 with the updated `Intent`.
**Branch — merchant out-of-stock or price outside tolerance:** do not auto-substitute; re-route to `notify_user` for explicit re-approval (§7 constraint).

## 9. External integration contracts

### 9.1 Prava Session API

The implemented server contract is **Session → Passkey → payment-result
polling → one-time credential → report status**. Prava does not publish a
Python SDK for this server path and does not expose a mandate webhook. Restock
uses the documented REST endpoints; exact response validation lives in
`payments/prava_client.py`.

```
create_session(user_id, user_email, total_amount, currency, merchant_name,
               merchant_url, merchant_country_iso2, product_description,
               unit_price, product_id=None, quantity=1,
               effective_until_minutes=15)
    -> { session_id, session_token, iframe_url, order_id, expires_at }
    # create_intent(...) remains as a compatibility wrapper. Intent is
    # Restock's proposal record; Prava's external object is the Session.
await_mandate(session_ref)
    -> { mandate_id, txn_ref_id, credential_reference, scope, approved_at }
       | rejected | expired
    # Polling only.
report_status(session_ref, txn_ref_id, txn_status,
              authorization_code=None, response_code=None) -> result
    # Required after every terminal merchant payment attempt.
```

**Known platform fact for production planning:** Prava requires a Visa card issued in the US, Canada, Hong Kong, or Singapore for any real card used in the flow, whether in sandbox or production. Prava's own documented sandbox test cards are unaffected and complete a full simulated flow with no geography restriction; use those for all hackathon build and demo work. See the resolved merchant-access and real-card-testing entries in `PRD.md` §21, "Risks and mitigations."

### 9.2 Merchant / billing execution

Restock reuses published merchant MCP tools for catalog/cart/order work. Those
tools do not perform browser card entry. The public compatibility contract
remains:

```
complete_checkout(credential_reference, merchant_sku_id, amount, idempotency_key) -> { status, merchant_order_id, charged_amount, currency, retryable, execution_mode }
```

**Restock Home implementation:** Zepto/Swiggy MCP covers OAuth where required,
saved-address selection, product/cart tools, exact-price preview, and status
reconciliation. The final card-form attempt is a separate Playwright boundary.
Merchant/catalog mode and payment mode are disclosed independently. The public
deployment currently configures both as `disclosed_mock`; a real mode requires
fresh provider authorization and explicit operator enablement.

Real Home proposals must be based on a fresh exact-cart quote for the tracked `merchant_sku_id`, positive `quantity`, and opaque `merchant_address_ref`. Initial quoting prepares and verifies the exact cart before preview; pre-checkout revalidation previews the already-prepared cart again. The Zepto device ID is supplied only through deployment configuration (`ZEPTO_DEVICE_ID`) and must never be persisted in `TrackedItem`, logs, or API payloads. Merchant clients remain injected so credential-free tests cannot make live calls by accident.

**Restock Teams:** one-time hosted-invoice quoting is implemented. Unattended
final invoice payment remains disclosed simulation. Prava now documents
`POST /v1/mandates/{id}/charge` for active mandates, including idempotent charge
references and merchant/cap enforcement. Restock has not implemented or
sandbox-proved that separate charge/report flow, so recurring Teams charging
remains disabled rather than being approximated.

### 9.3 OpenAI Agents SDK

Standard tool-calling loop; no fine-tuning required for the hackathon scope. Model selection should favor the fastest model that reliably respects the hard constraints in §7 — verify actual latency/cost against current OpenAI pricing at build time rather than assuming.

## 10. Non-functional requirements

| Requirement | Target |
|---|---|
| Notification-to-confirmation latency (excluding user response time) | < 5s |
| Mandate creation success rate (sandbox) | ≥ 99% across test runs |
| End-to-end success definition | (1) session created, (2) credential generated, (3) credential populated into real checkout form, (4) Pay attempt fails due to test-card status — not due to a bug in steps 1–3 |
| Unauthorized transactions (no valid passkey-approved mandate) | 0 — code-owned gate, pending live-boundary proof |
| Spend-cap breaches | 0 — hard guardrail |
| Idempotent merchant checkout | Every call keyed by `intent_id`; live-boundary proof required |
| Secrets handling | Prava/OpenAI keys in environment variables only; never committed to the repo |

## 11. Error handling and edge cases

| Scenario | Handling |
|---|---|
| Merchant reports out-of-stock | Notify user with the situation; no transaction created; item re-checked next cycle |
| Price increases at all, or decreases >15% from the approved quote | Do not auto-proceed; require explicit re-approval (§7) |
| Mandate/passkey rejected or times out | `Intent.status = expired`; item re-enters the normal check cycle |
| Merchant API error/timeout | Retry with backoff, max 2 attempts, then notify user of failure and log it |
| Duplicate trigger while an Intent is already pending for that item | Suppress duplicate notification |

## 12. Testing strategy

- **Unit tests:** forecasting math (predicted date, recalibration formula), depletion-only/price-only/both/neither trigger behavior, exact-SKU Zepto price normalization, refusal of similar-product substitution, and tool functions against mocked Prava/merchant responses. A read-only integration check verifies the same price path against Zepto's live MCP server; CI uses deterministic responses and no merchant credentials.
- **Integration test:** at least one full sandbox run of the happy path (steps 1–8 above) and one rejected-mandate path, before demo day.
- **Demo rehearsal:** a timed, scripted run-through matching `demo/script.md` (see `SKILL.md`), fitting inside the 5-minute submission video window.

## 13. Privacy and data handling

Full detail in `PRD.md` §20. Restock never receives or stores a card number.
Prava's one-time token/CVV set is visible only to the transient server-side
payment executor and is consumed once. Behavioral data gets minimization,
purpose limitation, export/deletion, sensitive-item handling, and bounded
retention.

## 14. Deployment for the hackathon

The implementation separates the FastAPI web process from a leased scheduler
worker and persists resumable workflows through a Postgres-compatible
SQLAlchemy repository with Alembic migrations through `20260801_11`. SQLite
remains the local/demo default. The public Railway service currently reports
`demo_mode=false`, Prava sandbox configured, real money disabled, Home and
Teams final execution as `disclosed_mock`, and no persistently deployed channel
listeners. `/capabilities` is authoritative; this text is only the last verified
snapshot. Provider production access, final-payment enablement, persistent
channel processes, and the final restore drill remain activation gates.

## 15. Observability

Every durable state transition writes a sanitized domain-audit entry with run, user, item, trigger reason, and real/simulated mode tags. Raw credentials, approval URLs, payment links, and card fields are structurally rejected. Engineering logs remain separate from the user-facing audit/savings feed.

## 16. Known limitations and non-goals (v1)

*Resolution paths for each of these live in `PRD.md` §15 (Roadmap) — this list is deliberately just the "not done yet" inventory, not the plan to close it.*

- No production ML forecasting model — deterministic EWMA remains the production baseline while consented observation logging and offline benchmarking collect evidence.
- One-time hosted SaaS invoice quoting is implemented; its unattended final payment remains a disclosed mock. Prava now documents active-mandate charging, but Restock has not integrated or sandbox-proved that charge/report boundary, so recurring Teams charging remains disabled.
- Multi-user Household/Organization membership, roles, invitations, consent, and multi-approver policy are implemented; shared approval is not treated as reusable payment authority until Restock's mandate-charge integration enforces the same policy.
- Capacitor Android/iOS wrappers are implemented and simulator-built; store enrollment, physical-device push validation, and publication remain external launch gates.
- The real Restock PWA is the guaranteed submission surface, not a mocked channel. The Slack adapter must disclose whether its external process is active; WhatsApp activation is optional post-launch and not a submission gate.
- Home adapters cover real Zepto and Swiggy catalog/cart quoting. Zepto's unattended final payment remains disclosed-mock by default; Swiggy card payment remains an explicit browser boundary and is never silently replaced by COD.
- Long-term, the correct solution for authenticated billing platforms is OAuth-based delegated access to the platform's own billing API (e.g., Stripe Billing API, Chargebee API) — scoped and revocable access to the subscription object specifically, never the user's login credentials. This mirrors Prava's own trust model at the SaaS-account layer rather than the payment layer, and is explicitly preferred over any browser-automation approach to login.

## 17. Open questions — verify before/during build

- [x] **RESOLVED** — Model selection for the orchestrator: one verified-reliable model, `gpt-5.4-mini`, for the full loop including notification copy and the Teams plan-comparison decision. This removes a constrained-quota live-demo dependency; hard constraints stay in code-level Guardrails. See §7.
- [x] **RESOLVED** — Prava has no Python SDK for the server path. Restock
  implements the documented Session REST endpoints and normalizes the polling
  payload in `payments/prava_client.py`.
- [x] **RESOLVED — Zepto merchant contract:** the official skill uses `mcp-remote https://mcp.zepto.co.in/mcp` with OAuth/mobile OTP and publishes tools for saved addresses, product search, cart mutation/view, payment methods, online-order preview/creation, payment status, and order history. Final payment-link execution is operator-controlled because no merchant sandbox is documented.
- [x] **RESOLVED** — Prava's documented sandbox test data was used for the
  Session/passkey proof. Its expected real-merchant decline is part of the
  disclosed success criterion, not a completed charge.
- [x] **RESOLVED** — Restock sends `effective_until_minutes` on Session
  creation (15 minutes by default) and treats expiry as terminal.
- [x] **RESOLVED — platform fact:** Prava requires a Visa card issued in the US, Canada, Hong Kong, or Singapore for any real card used in the flow, whether in sandbox or production. Prava's own documented sandbox test cards are unaffected and complete a full simulated flow with no geography restriction; use those for the hackathon. For production, Prava has offered: "reach out to us and we'll sort you out with a compatible card".
- [x] **RESOLVED AT THE PLATFORM CONTRACT; RESTOCK INTEGRATION PENDING:** Prava
  now documents `POST /v1/mandates/{id}/charge` for active mandates and a
  corresponding terminal report operation. The charge is idempotent when a
  reference is supplied and enforces mandate merchant/cap constraints. This
  supersedes the earlier hackathon-era availability note. Restock Teams still
  uses the one-time hosted-invoice path or disclosed mock until the new
  mandate-charge boundary is implemented and sandbox-proved end to end.

## 18. Glossary

- **Intent** — our internal record of a proposed purchase, before user approval.
- **Mandate** — Prava's record of user-approved, scoped permission to charge a specific merchant a bounded amount.
- **Credential reference** — Restock’s opaque handle for a one-time token/CVV
  set. Raw values are held only in the consume-once server payment boundary and
  are never persisted or logged.
