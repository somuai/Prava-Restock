# Teams billing UX research

The rebuilt Teams detail follows recurring patterns from official billing
surfaces rather than a generic dashboard layout.

## Patterns applied

- Open on the existing plan, next billing event, owner/quantity, usage context,
  and payment state. Figma and Vercel both separate plan/cycle information from
  invoice history and usage.
- Reveal plan comparisons only after the user asks to manage the plan. Stripe's
  customer portal treats product and price selection as a curated management
  surface rather than the default landing state.
- Keep plan selection, review, and payment as separate decisions. GitHub,
  Notion, Figma, and Stripe all account for effective-date and proration
  differences before a plan change is confirmed.
- Treat invoice settlement as distinct from plan changes. The invoice view
  reserves fields for status, issue/due date, line items, payment method, and
  receipt instead of fabricating a complete invoice from the tracked renewal.
- Use provider color only as a local accent. Restock green owns trust,
  guardrails, and approval boundaries.

## Source material

- [GitHub: impact of plan changes](https://docs.github.com/en/billing/concepts/impact-of-plan-changes)
- [GitHub Copilot organization billing](https://docs.github.com/en/copilot/concepts/billing/organizations-and-enterprises)
- [Stripe: configure the customer portal](https://docs.stripe.com/customer-management/configure-portal)
- [Stripe: modify subscriptions](https://docs.stripe.com/billing/subscriptions/change)
- [Figma: manage payment and invoice details](https://help.figma.com/hc/en-us/articles/360040532093-Manage-payment-and-invoice-details)
- [Figma: guide to billing](https://help.figma.com/hc/en-us/articles/29717597009431-Guide-to-billing-at-Figma)
- [Notion: upgrade or downgrade a plan](https://www.notion.com/help/upgrade-or-downgrade-your-plan)
- [Notion: invoices](https://www.notion.com/help/invoices)
- [Vercel: Pro plan billing](https://vercel.com/docs/plans/pro-plan/billing)
- [Vercel: understanding an invoice](https://vercel.com/docs/pricing/understanding-my-invoice)

## Data boundary

The interface renders only the tracked plan values already present in Restock.
Unknown seat counts, invoice numbers, line items, credits, tax, prorations, and
effective dates are explicitly left for a sourced vendor quote or invoice.
The UI does not invent those values.
