# Parcel, billing-receipt, profile, and notification research

## Applied decisions

- The parcel is one articulated WebGL object. Its front wall and Restock mark
  remain physically stable while four flap pivots open. The former DOM-poster
  to WebGL crossfade and closed/open image swap were removed.
- The visible response begins on the first rendered frame. Flaps open in about
  340 ms and the product/provider object overlaps that motion, settling in
  about 480 ms.
- Teams billing is one continuous warm-paper statement with ledger rows,
  perforated sections, pull-out plan slips, a distinct plan-change review
  tear-off, and explicit approval boundaries. The prior grid of nested square
  cards was removed from the rendered flow.
- Pointer velocity, not absolute pointer position, supplies a small wind force
  to loose paper. The transform is written in one animation frame, damped back
  to zero, ignored over controls, disabled for touch, and removed under
  `prefers-reduced-motion`.
- The profile is a right-side pantry folio outside primary navigation. The
  notification center and foreground slip use concise, contextual information
  and never turn dismissing the presentation into skipping the workflow.

## Evidence

- [Material Design — Choreography](https://m1.material.io/motion/choreography.html)
  supports one clear focal element and continuous motion relationships.
- [Material Design — Duration and easing](https://m1.material.io/motion/duration-easing.html)
  recommends shorter desktop transitions and reserving longer durations for
  larger, more complex movement.
- [Apple Human Interface Guidelines — Motion](https://developer.apple.com/design/human-interface-guidelines/motion)
  recommends brief, precise motion tied directly to an interaction.
- [W3C WCAG — Animation from interactions](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions)
  requires nonessential interaction-triggered motion to be suppressible.
- [Apple Human Interface Guidelines — Notifications](https://developer.apple.com/design/human-interface-guidelines/notifications)
  recommends timely, high-value, glanceable notifications, no duplicates, and
  restrained contextual actions.
- [PaperTouch, CHI 2024](https://doi.org/10.1145/3613904.3642571) demonstrates
  that paper’s expressive physical qualities can communicate both affordance
  and aesthetics. Restock uses the receipt metaphor for hierarchy while
  retaining standard digital controls and radio semantics.
- [Stripe subscription change guidance](https://docs.stripe.com/billing/subscriptions/change)
  informed the separate plan-selection, proration review, approval, and
  payment states.
- [W3C ARIA alert pattern](https://www.w3.org/WAI/ARIA/apg/patterns/alert/)
  informed the non-focus-stealing notification slip and polite announcement.

The physical receipt composition and pointer-wind mapping are Restock-specific
design inferences from these sources, not claims made by the sources.

## Visual QA evidence

- Before:
  `docs/design-research/paper-billing-audit-before/02-teams-parcel-immediate-current.png`
- Final Teams parcel and receipt:
  `docs/design-research/paper-billing-audit-after/04-teams-receipt-final.png`
- Combined reference/before/after review:
  `docs/design-research/paper-billing-audit-after/05-reference-before-after.png`
