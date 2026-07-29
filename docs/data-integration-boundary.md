# Restock data-integration boundary

## What is real in the current build

Restock owns the tracked-item record and the resulting lifecycle state. The
trigger engine evaluates purchase dates, cadence estimates, renewal dates,
price observations, and workflow status that have already been written into
Restock. When a trigger becomes actionable, the item materialises on the Home
shelf. A completed purchase removes it from that action shelf and moves it to
the compact recently-restocked list with its next expected date.

Zepto's authenticated remote MCP server provides merchant operations for the
selected transaction: address selection, product search, SKU resolution, cart
preview, availability and final-price checks, payment-method discovery,
checkout, order history, and payment-status reconciliation. Prava provides the
scoped intent, passkey, mandate, and short-lived payment credential used at the
payment boundary. The current Prava skills repository exposes a generic
`prava-shopping` workflow; Restock's Zepto adapter talks to Zepto's remote MCP
directly instead of assuming a Zepto-specific skill still exists in that repo.

These are deep transaction integrations, but they are not an automatic feed of
everything a user has ever bought.

## What is not automatic

Zepto, Blinkit, Swiggy, Zomato, Amazon, and SaaS vendors do not collectively
send their consumer purchase histories into Restock through one public API.
Prava is not a cross-merchant purchase-history aggregator. It authorizes and
executes scoped payments.

The live Zepto MCP connection can list order history and past-order items. In
the response shape verified on 30 July 2026, that history does not include the
stable SKU and purchase timestamp needed to infer depletion by itself. It can
help a user choose or confirm an item, but it is not silently promoted into
forecast history.

Slack is not an ingestion source. It receives Teams renewal notifications and
returns explicit user actions. SaaS renewal dates and invoice amounts must come
from Restock's tracked-item record or a separate, authorized vendor/invoice
connector.

The current build therefore uses tracked items and histories created inside
Restock, plus merchant quotes, order-history facts where sufficiently scoped,
and checkout/status calls made by the relevant adapter. It must not claim that
every consumer platform is already streaming order data into the product.

## How Restock knows an item is likely to run out

Restock predicts depletion; it does not measure the physical contents of a
packet. Each Home item starts with a last-purchase date and cadence from a
user-confirmed value, a sufficiently detailed authorized order/receipt source,
or a public category-level cold-start prior. The deterministic trigger compares
the predicted depletion date with the trigger window. A user-set price
threshold is an independent second signal. After a purchase completed through
Restock, the actual interval updates the cadence through EWMA.

This is intentionally explainable. A message such as "coffee is due in two
days" means "the current purchase-history and cadence estimate predicts two
days," not "Zepto reported that two days of coffee remain."

## Production ingestion paths

A production all-in-one experience can grow its known history through explicit
and consented connectors:

- merchant-specific account or MCP integrations where the merchant exposes the
  required order-history scope;
- receipt and invoice ingestion from user-authorized email sources;
- user-confirmed first-purchase dates and cadence during onboarding;
- open-commerce or financial-data providers whose terms explicitly allow the
  intended use;
- reconciliation of purchases initiated by Restock through merchant
  order/payment status.

Each source must be visible to the user, independently revocable, and tagged in
the audit log. Missing merchant access falls back to user-confirmed history; it
does not justify inventing a purchase or silently scraping a private consumer
account.

## UI lifecycle contract

The presentation follows workflow truth:

1. `triggered` through any active non-terminal state: show the item on the
   action shelf with its trigger reason.
2. `completed`: remove it from the action shelf and show it as recently
   restocked with the next predicted date.
3. `failed`, `skipped`, `rejected`, or `expired`: remove it from the action
   shelf and return it to quiet tracking unless a new trigger fires.
4. Only a completed Home purchase recalibrates cadence. Approval alone is not a
   purchase.

The same rule applies to Teams: a provider appears as a decision object when a
renewal workflow is active, while watched subscriptions remain in the quieter
cabinet state. A plan switch always remains a distinct explicit action.
