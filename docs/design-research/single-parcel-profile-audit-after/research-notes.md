# Single-parcel, billing-receipt, and profile pass

## What was observed

- The first Teams frame could show the billing receipt before the parcel had
  visually responded, then show an already-open parcel. That made the reveal
  feel like two unrelated scenes.
- The Restock mark sat on a separate plane close to the front wall and could
  visually disappear or flicker at some camera angles.
- Important receipt metadata, plan copy, and actions fell below a comfortable
  reading size. The same-screen “View plan” action used a forward-navigation
  arrow even though it changed an in-place tab.
- The prior profile drawer repeated generic outlined cards and small status
  text instead of presenting account identity, spend boundaries, delivery
  routes, preferences, and privacy as one coherent settings surface.
- Detailed Mobbin flows require an authenticated account, so this pass does
  not claim access to gated Mobbin captures.

## Design decisions

- One preloaded premium parcel stage owns both matched closed and open states.
  It does not hand off to a visually different WebGL model; product or
  subscription content rises only after the opening state begins.
- The Restock mark is composited into both parcel source states. The opened
  parcel gains only a subtle settled float; shelf products remain still.
- The billing view remains a single continuous receipt, with larger body copy,
  ledger rows, plan titles, amounts, and 48 px actions. In-place plan details
  use a descriptive icon rather than a misleading forward arrow.
- The profile is one warm paper folio with grouped rows and progressive
  disclosure: identity, spending boundaries, delivery routes, experience, and
  privacy. It has one real preference control and no wall of interchangeable
  cards.
- Home uses seven real retail packshots across three shelf levels. Exact
  merchant images remain an adapter responsibility in production.

## UX references

- [Apple Human Interface Guidelines — Settings](https://developer.apple.com/design/human-interface-guidelines/settings)
- [Apple Human Interface Guidelines — Motion](https://developer.apple.com/design/human-interface-guidelines/motion?changes=_2_2)
- [Shopify app layout guidance](https://shopify.dev/docs/apps/design/layout)
- [Android settings pattern](https://developer.android.com/design/ui/mobile/guides/patterns/settings)
- [Atlassian typography foundations](https://atlassian.design/foundations/typography/)
- [WCAG 2.2 target-size minimum](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
- [WCAG 2.2 text spacing](https://www.w3.org/WAI/WCAG22/Understanding/text-spacing)

These references informed hierarchy, readable text sizing, grouped settings,
single-primary-action regions, target sizing, and reduced-motion behavior.
They were used as principles rather than copied as a branded screen.

## Product-image sources added in this pass

- [Tata Salt — Driftbasket](https://driftbasket.com/product/tata-salt-1-kg/)
- [Surf Excel Expert White — Hydri Supermarket](https://www.hydrisupermarket.com.pk/surf-excel-expert-white-detergent-powder-500gm-m22252)
- [Colgate Strong Teeth — Gandhi Bazar](https://www.gandhi-bazar.com/products/colgate-strong-teeth-anticavity-toothpaste-200g)

Only deterministic background removal was applied to those retail packshots.

## Final shelf and reveal correction

- Shelf rows now reserve separate vertical zones for the retail packshot,
  shelf edge, and hanging note. The products retain a strong first-viewport
  scale while every note ends inside its own row instead of crossing into the
  product below.
- The opened-parcel reveal settles the product just above the front lip, with
  a seven-pixel ambient float. The front wall remains in front of the content
  to preserve depth, but the product no longer reads as resting inside the
  parcel.
- Final QA references:
  `35-home-products-large-notes-deliverable.jpg` and
  `32-product-floating-above-parcel-final.jpg`.
