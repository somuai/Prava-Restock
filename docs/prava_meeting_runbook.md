# Prava review meeting runbook

Use this as the speaking and operating guide for the 3 August 2026, 9:30 a.m.
IST review. Keep the one-page brief open beside it.

## 1. Prepare 20 minutes before the call

Open these tabs in this order:

1. [One-page brief](prava_meeting_one_pager.md).
2. The deployed [Restock PWA](https://restock-offline-stub-production.up.railway.app/app/).
3. Home with the Coffee item ready to open.
4. Teams with the subscription proposal ready to open.
5. Activity/audit view.
6. The private Slack workspace containing the Restock Teams message.
7. Public [`/capabilities`](https://restock-offline-stub-production.up.railway.app/capabilities).
8. The latest green GitHub Actions run.
9. [Phase 7 sandbox evidence](phase7_evidence.md) and the locally stored masked
   failure screenshot, if needed.
10. [Production activation runbook](provider_activation_runbook.md).

Then:

- Check `/health` and `/ready` without opening Railway's Variables page.
- Sign in to the isolated reviewer account before screen sharing. Keep its
  password outside the clipboard history and out of visible notes.
- Ensure Slack is open on the already-verified message; do not create a payment
  merely to make the channel look active.
- Close `.env`, password-manager, terminal history containing secrets, personal
  email, and any Zepto page showing a complete address or phone number.
- Disable desktop notifications and unrelated browser extensions.
- Keep the exact sandbox failure message and session identifier available in a
  private note, but show the identifier only if Prava asks for it.

## 2. Opening — first 60 seconds

Say:

> Restock is a proactive replenishment and renewal agent. Home predicts an
> essential running out or crossing a price threshold; Teams detects a known
> renewal. It obtains a current merchant or invoice quote, enforces hard policy,
> and asks for an explicit decision. Prava is the core trust boundary that lets
> an independent agent request scoped approval without storing a user's card.

Then state the meeting goal:

> I want to show you the working product and safety architecture, reproduce the
> one sandbox blocker honestly, and leave with an exact production-activation
> checklist and an owner for the test-card passkey issue.

Do not begin with a long market overview. Let the working product establish
credibility first.

## 3. Product walkthrough — 6 to 8 minutes

### Step A — Home trigger

1. Show the living pantry and open Coffee.
2. Explain the two independent signals: predicted depletion and an optional
   price threshold. If both fire, Restock creates one notification containing
   both reasons.
3. Point to Approve, Adjust, and Skip. State that a proposal is not a charge.
4. Explain that a fresh exact-SKU quote is required before requesting payment;
   unavailable or different products are never substituted silently.

Suggested line:

> The agent can choose a proposal and tools, but it cannot override the spend
> cap, substitute the SKU, skip user approval, or bypass idempotency. Those are
> code-owned policies.

### Step B — Prava boundary

1. Choose Approve only if the reviewer workflow is in a safe pending state.
2. Show that Restock creates a real hosted sandbox Session.
3. Stop at the provider result. State precisely:

> The assigned card is accepted, then Prava shows Security Check Failed. On
> retry it is marked No Passkey and cannot be selected. We therefore do not
> claim a completed mandate or credential. I need your help provisioning or
> resetting this sandbox card.

4. Show the Activity entry and its sandbox/simulated tag. Do not show the
   complete test card, approval URL, OTP, dynamic CVV, or any payment token.

### Step C — merchant boundary

Show the Phase 8 evidence rather than mutating a live cart during the meeting.
Explain that the verified Zepto path includes OAuth, saved-address lookup,
exact-SKU search, live price, cart preview, payment methods, and
`confirmOrder=false` quoting. No order was confirmed and final payment remains
operator-gated.

### Step D — Teams and Slack

1. Open the Teams subscription shelf.
2. Show renew-as-is versus switch-plan. A switch requires its own explicit
   action; a generic approval cannot select it.
3. Show the real Slack message and the resolved callback state.
4. Explain the billing boundary: hosted payment links are supported; platforms
   requiring account-login automation are flagged for manual renewal. Restock
   does not store SaaS login credentials.

### Step E — safety and operations

Show the latest green CI and name only the most relevant invariants:

- An over-cap proposal is rejected before Prava is called.
- Checkout cannot run without approved payment state.
- Rejected or expired approval creates zero transactions.
- Duplicate triggers and checkout retries are idempotent.
- More-than-15-percent quote deviation returns to approval.
- Raw credentials and approval URLs are rejected from durable audit data.
- A restarted process resumes from durable workflow state.

## 4. Architecture explanation — 90 seconds

Use this sequence:

```text
scheduled trigger
  -> exact merchant/invoice quote
  -> code-owned policy checks
  -> proactive notification
  -> explicit user action
  -> Prava hosted approval
  -> payment-result polling
  -> consume-once credential boundary
  -> merchant reconciliation
  -> Prava terminal status report
  -> sanitized audit + cadence update
```

Clarify ownership:

- The OpenAI Agents SDK proposes and selects tools.
- Restock code owns money/state invariants.
- Prava owns the hosted approval and scoped credential issuance.
- Merchant MCP/API owns catalog, price, stock, cart, and order truth.
- Postgres owns recoverable references and state, never raw card data.

## 5. Questions Prava is likely to ask

### “How do you know an item is running out?”

The user begins with a tracked item and a rough cadence. A transparent category
prior can seed the first estimate; completed Restock purchases update that
cadence through EWMA. A price threshold is a second signal. Restock does not
claim to read a user's entire Zepto/Swiggy purchase history without an
authorized data source.

### “Is this just a shopping chatbot?”

No. The scheduler detects conditions without a purchase request. The user acts
only after Restock proactively prepares a bounded proposal. The same workflow
supports household depletion and known-date subscription renewal.

### “Why is Prava necessary?”

Restock is independent of any single merchant. A merchant's own app can charge
its stored card; an independent cross-merchant agent needs scoped user approval
and a revocable, limited credential. That is Prava's structural role.

### “What is real right now?”

The deployed PWA, authentication, triggers, workflow, Postgres, worker, Slack,
safety rules, Prava Session creation, and verified Zepto catalog/cart/quote
operations are real. The assigned card is blocked before Prava passkey approval.
Final Zepto payment and Teams fulfillment remain disclosed simulations, with
real money disabled.

### “Why did we not see the sandbox flow?”

There were two separate issues. The temporary reviewer route was a pre-seeded
login, not a sign-up, and its UI is now labelled accordingly. After entering
the Home Coffee approval, Restock creates the real hosted Session, but the
assigned card stops at Security Check Failed / No Passkey. Provide the private
session identifier so Prava can trace it.

### “Do you store card information?”

No card number, CVV, OTP, approval URL, or one-time credential is persisted or
logged. A one-time token/dynamic CVV may temporarily enter the isolated
server-side payment boundary for one checkout attempt; it is memory-only,
consume-once, and deleted after use.

### “Can the model overspend?”

No. Spend limits are enforced by an Agents SDK tool-input Guardrail before the
Prava client is invoked. Quote binding, approval, idempotency, substitution,
and state transitions are separately enforced in deterministic workflow code.

### “What if the price changes?”

Restock revalidates the exact SKU immediately before checkout. Any increase—or
a decrease greater than the configured 15-percent tolerance—returns to explicit
approval. Out-of-stock never causes an automatic replacement.

### “What happens if the API or worker restarts?”

Workflow state, leases, notification actions, intent/mandate references,
idempotency records, and audit entries are durable in Postgres. The worker
resumes the state machine; one-time payment credentials are deliberately not
recoverable and a lost credential terminalizes safely rather than retrying a
charge blindly.

### “How does Teams pay subscriptions?”

Today it targets hosted, tokenized invoice/payment links or flags manual renewal.
It never automates a vendor dashboard login. Prava now documents active-mandate
charging, but Restock will not advertise recurring Teams charging until that
separate endpoint and terminal-report path are integrated and sandbox-proved.

### “Why PWA and Slack rather than WhatsApp?”

The PWA is the guaranteed product surface and Slack is the verified Teams
channel. WhatsApp is optional post-launch and is not claimed as activated.
This keeps the judged flow independent of Meta approval and pricing.

### “How are multiple users isolated?”

The schema supports Household and Organization tenants, memberships, roles,
invitations, tenant-scoped resources, and multi-approver policies. Browser
sessions are signed, short-lived, Secure, HttpOnly cookies. Cross-tenant
authorization tests gate enablement.

### “How does Restock make money?”

Home can use a small household subscription or merchant affiliate revenue.
Teams can charge a flat subscription or a share of verified first-year savings.
No business model requires selling household purchase data.

### “What makes it different from Amazon AutoBuy?”

Amazon operates inside its own catalog using its stored payment method. Restock
is cross-merchant, supports depletion and renewal triggers, and uses Prava
because it has no direct payment relationship with those merchants.

### “How much was built before the event?”

Answer from git history. The production-oriented foundation predates the
official window and is disclosed as such; event-window provider activation,
integration fixes, evidence, and submission work remain separate commits.
Never imply that pre-existing work was built during the 48 hours.

### “What is the NANDA submission?”

There are two artifacts: a public stateless trigger-math skill and a reusable
Prava payments adapter implementing NANDA's `quote`, `pay`, `verify_payment`,
and merchant-delegated refund boundary. The upstream PR remains draft because
the same interactive Prava sandbox blocker prevents the required live proof.

## 6. Questions Restock must ask Prava

Ask these before the meeting ends and record the exact answer and owner:

1. Is this assigned card expected to have passkey support automatically?
2. Can Prava reset or provision it, and what session/log identifier is needed?
3. Is an enrollment, OTP, supported browser, authenticator, or device step
   missing from the published sandbox procedure?
4. What exact production key/host/mode flags change after approval?
5. What compatible-card help is available for the controlled production test?
6. What maximum transaction, merchant, geography, and expiry limits apply?
7. Must every failed merchant attempt call `report-status`, and what exact
   status/retry mapping should Restock use for ambiguous failures?
8. Can `POST /v1/mandates/{id}/charge` support a capped repeated Teams renewal,
   and does every charge require a fresh user-presence/passkey event?
9. Are there special restrictions on the documented Zepto flow in production?
10. What evidence does Prava need before granting or retaining production access?

## 7. Failure protocol during the call

If the live app or provider page fails:

1. Do not retry a mutating merchant action blindly.
2. State which boundary failed: Restock API, Prava hosted flow, Zepto MCP, or
   browser/device passkey support.
3. Show the corresponding evidence document and correlation/session reference.
4. Keep the disclosure badge visible and continue with deterministic safety
   proof, Slack, and architecture.
5. Never switch to a real-money path just to rescue the demo.

## 8. Close the meeting

Summarize aloud:

> The application, workflow, merchant quote path, Slack delivery, durable state,
> and safety controls are ready. The immediate blocker is the assigned sandbox
> card's passkey/security provisioning. Once you confirm that and production
> activation, I will run one controlled proof using the documented runbook and
> return the exact terminal status evidence.

Before leaving, read back each action with owner and target time. Send the
follow-up template within fifteen minutes.
