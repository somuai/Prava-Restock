# Restock physical-pantry and subscription-object redesign QA

## Visual source and comparison evidence

- Reference Home capture:
  `docs/design-research/reference-pass2/01-reference-home.png`
- Reference product-detail capture:
  `docs/design-research/reference-pass2/03-reference-product-detail.png`
- Final premium parcel reveal:
  `docs/design-research/implementation-pass4/02-home-premium-parcel.jpg`
- Final Teams renewal gallery:
  `docs/design-research/implementation-pass4/03-teams-subscription-shelf.jpg`
- Final Teams subscription reveal:
  `docs/design-research/implementation-pass4/04-teams-subscription-reveal.jpg`
- Mobile Home and tablet Home:
  `docs/design-research/implementation-pass2/04-home-mobile.png` and
  `docs/design-research/implementation-pass2/05-home-tablet.png`
- Required same-input parcel comparison:
  `docs/design-research/implementation-pass4/05-parcel-reference-comparison.png`
- User-supplied 3D app-object comparison:
  `docs/design-research/implementation-pass4/06-award-reference-comparison.png`
- Final all-tracked Home shelf:
  `docs/design-research/implementation-pass5/01-home-shelf.jpg`
- Final replenishment-cycle Activity view:
  `docs/design-research/implementation-pass5/02-activity-streak.jpg`
- Final Teams shelf and lower-shelf alignment:
  `docs/design-research/implementation-pass5/03-teams-shelf.jpg` and
  `docs/design-research/implementation-pass5/04-teams-lower-shelf.jpg`
- Final Restock parcel and icon-led product facts:
  `docs/design-research/implementation-pass5/05-product-reveal.jpg` and
  `docs/design-research/implementation-pass5/06-product-facts.jpg`
- Final shelf-seating and logo-centering pass:
  `docs/design-research/implementation-pass6/01-teams-centered.jpg` and
  `docs/design-research/implementation-pass6/02-home-seated.jpg`
- Immediate closed-parcel response and completed open state:
  `docs/design-research/implementation-pass6/04-reveal-immediate-poster.jpg`
  and `docs/design-research/implementation-pass6/05-reveal-open.jpg`; the same
  immediate response for Teams is captured in
  `docs/design-research/implementation-pass6/06-teams-reveal-immediate.jpg`
- Branded, jitter-free parcel handoff and the rebuilt Teams billing journey:
  `docs/design-research/teams-billing-pass/01-parcel-immediate-branded.png`,
  `docs/design-research/teams-billing-pass/02-billing-overview.png`,
  `docs/design-research/teams-billing-pass/04-plan-review.png`, and
  `docs/design-research/teams-billing-pass/07-mobile-plans.png`
- Reference and implementation reviewed together:
  `docs/design-research/teams-billing-pass/08-reference-vs-current.png`

## Fidelity review

- Typography now follows the source's role-based system: Inter for interface
  copy, Radio Canada Big for product and page display type, Geist Pixel Square
  for compact metadata, Gloria Hallelujah for parcel labels, and Gaegu for
  quiet handwritten annotations.
- Home is a sparse physical pantry rather than a grid of SaaS cards. Products
  are larger, use real manufacturer photography, sit on shelves at two levels,
  and remain the primary visual focus.
- Every active or quietly tracked product remains on a physical shelf.
  Completed purchases alone leave the shelf and move to Activity, where a
  three-step replenishment cycle shows bought, cadence restarted, and quiet
  watch states. The detached recently-restocked/tracking ledger was removed.
- Real plant/window photography supplies the corner sunlight and shadows. The
  earlier independent plant cutouts were removed.
- Cardboard labels use a photographed material texture, overlap the front shelf
  edge so they read as physically attached, and respond to pointer movement
  within a small decorative range.
- The active destination is one quiet collapsed pill. It expands to all three
  destinations on pointer hover or keyboard focus. Touch layouts keep the
  destinations visible as icons instead of depending on hover.
- Product details reproduce the source's open-box reveal with matched
  photoreal open/closed parcel renders in a WebGL stage. The box is wide and
  shoebox-like, has believable cardboard construction, carries a restrained
  Restock-green brand band, and has no low-poly grid or shadow-acne artifacts.
  Merchant provenance is a smaller adjacent source seal instead of competing
  parcel branding. The real Restock mark is now composited into both parcel
  textures, so it remains present in the immediate poster, live WebGL reveal,
  and static fallback. The WebGL scene holds a closed, non-rotated first frame;
  the branded poster hands off to that matching frame; only then does one
  opening clock begin. Pointer parallax waits until the parcel is fully open.
  The selected product rises from the parcel and settles into a finite, slow
  float.
- Teams uses upright, extruded rounded-square provider objects inspired by the
  supplied 3D App Store reference. Each object uses its provider color
  language and places the source brand mark on the broad front face; no Apple
  mark or narrow Mac-mini port panel remains. Each object now sits directly on
  its shelf slab, while its larger paper plaque hangs below the front edge with
  the provider, date, price, and readable state in one connected object. Every
  provider mark is optically centered on the broad front face.
- Opening a Teams item uses the same parcel interaction as Home. The selected
  subscription object rises from the box and becomes the focal object before
  the explicit renew-versus-switch decision.
- Teams detail now unfolds into a branded billing folio rather than a flat
  renew/switch pair. It begins with the current plan, amount with currency and
  cadence, renewal date, owner, quantity, usage/budget note, payment boundary,
  and sourced plan description. Overview, Plans, and Invoices use progressive
  disclosure, with provider color kept as an accent and Restock green reserved
  for trust and approval.
- Primary preview/mock chips were removed. Environment modes remain available
  in the secondary Activity disclosure and audit records. Plain-language
  real-charge/no-charge disclosure remains immediately above each approval
  surface, where it is needed for informed consent.

## Interaction and safety review

- Product actions are bound only to the coffee preview notification; opening
  another product cannot approve the first pending notification accidentally.
- Teams actions are bound only to the GitHub Copilot decision. Other renewal
  receipts are informational until they have a structured notification.
- `renew_as_is`, `switch_plan`, and `skip` remain distinct backend actions.
  Generic renewal never selects the alternate plan.
- Plan comparison is a draft selection. A separate review sheet shows current
  versus proposed plan, amount presented for approval, effective-date source,
  proration/tax boundary, and Prava payment boundary before the explicit
  approve-and-pay action becomes available.
- Approval, adjustment, and skip controls remain visible pill buttons with
  exact amounts. The parcel animation never initiates a payment.
- Product and renewal detail support Escape, focus the Back control on entry,
  and return focus to the originating shelf item when closed.
- Cancelling amount adjustment now restores focus to the Adjust control.
  Decision clusters use explicit group semantics and expose their busy state.
- Sound remains off by default, opt-in, visibly toggled, and backed by one
  shared audio context. Submission and success use different cues, so a failed
  request cannot produce a success sound. Every sound has visible feedback.
- The first opening sound is now queued after the selected-item render instead
  of initializing audio before the visual response. Contact shadows render as
  one low-resolution frame to avoid a first-click GPU hitch.
- Pointer wind is limited to the paper labels, runs outside React render state,
  and is disabled for coarse pointers, viewports below 800 px, and
  reduced-motion users. Home products and Teams provider objects remain
  stationary on their slabs; floating motion exists only inside an opened
  parcel detail.
- `prefers-reduced-motion` removes continuous transforms and makes reveal
  states effectively immediate.
- Mobile Home, mobile Teams, mobile product detail, and mobile renewal detail
  were measured at 390 × 844 with `innerWidth`, HTML client/scroll width, and
  body client/scroll width all equal to 390 px. `body` does not hide overflow.
- Functional mobile product labels were raised to 11 px and price/SKU metadata
  to 9 px; decision amounts remain larger in the detail view.
- A per-notification synchronous guard and visible busy state prevent repeated
  action submissions. Controls disable until the request resolves.
- Live approval opens a blank passkey tab during the original user gesture,
  then navigates it after the API returns. If a tab cannot be opened, the
  same-page approval handoff is used instead.
- The amount adjustment starts from the selected product's current displayed
  price instead of a hard-coded coffee value.

## Verification

- Frontend production build: passed.
- Frontend unit tests: 8 passed.
- Full Python suite: 321 passed, 1 skipped, 7 deselected.
- `git diff --check`: passed.
- Browser runtime errors/warnings in the final Home, Teams, Activity, and
  parcel-detail states: none.
- Browser interaction checks: Home/Teams navigation, expanding keyboard-focus
  pill, opt-in sound state, product parcel reveal, renewal parcel reveal,
  point-of-action charge disclosure, explicit Teams actions, preview action
  locking, stationary shelf objects, immediate parcel poster, and responsive
  overflow all passed.
- Production dependency audit: 0 vulnerabilities.

Independent audits identified point-of-action disclosure, delayed passkey
popup creation, in-flight action locking, small functional type, cold parcel
loading, shelf-label overlap, floating Teams objects, inconsistent frame-rate
motion, premature success sound, hard-coded adjustment amount, and focus loss
after adjustment cancellation. Each item was fixed or reverified before this
final result. The intentionally collapsed desktop navigation remains the
user's selected interaction; it expands on hover or keyboard focus, while
touch layouts keep icon destinations visible.

No actionable P0, P1, or P2 visual or interaction issue remains in this pass.

Final result: passed

## Decision control legibility

- Previous state: Approve, Adjust, and Skip used the 9px uppercase Geist Pixel
  metadata treatment, which was too small for primary actions.
- Final state: all three actions use Inter at 13.5px, weight 650, sentence
  case, and a 52px minimum control height.
- Browser verification:
  `docs/design-research/decision-controls/approve-adjust-skip-larger.jpg`.
- Frontend production build: passed.
- Frontend unit tests: 8 passed.
- Browser-computed styles matched the intended values for all three controls.

Final result: passed

## Home and Teams hierarchy cleanup

### Comparison target

- User-supplied Teams screenshot:
  `/var/folders/7t/5vnpd2zs6gsflg2c4xfb_2780000gn/T/codex-clipboard-80b8a318-4339-418b-af29-505a9d8aec4d.png`.
- Final Home state:
  `docs/design-research/hierarchy-cleanup/home-living-pantry.jpg`.
- Final Teams state:
  `docs/design-research/hierarchy-cleanup/teams-integrated-shelf-heading.jpg`.
- Combined source/final evidence:
  `docs/design-research/hierarchy-cleanup/teams-reference-vs-final.jpg`.

### Evaluation and fixes

- [P1 fixed] “Living pantry” was too small in the original shelf note. It now
  uses the primary display type at a clearly readable size.
- [P1 fixed] The enlarged Home introduction initially overlapped the first
  product. Its explanatory sentence was removed and the upper shelf was given a
  dedicated vertical offset, leaving the title and every product visibly
  separate.
- [P1 fixed] The oversized “Every provider, held like an earned award” headline
  and all visible renewal-award language were removed. Teams now uses the
  functional title “Subscription shelf.”
- [P2 fixed] The final Teams title was moved inside the cabinet and given the
  same small-context/large-title hierarchy as “My pantry / Living pantry,” so
  Home and Teams now introduce their shelf scenes consistently.
- The approved three-dimensional provider objects remain unchanged; only the
  caricature-like reward metaphor and excessive headline hierarchy were
  removed.

### Verification

- Home and Teams render at 1280 × 720 with no title/product overlap.
- Semantic headings and provider buttons remain present.
- Browser console: no errors or warnings.
- No actionable P0, P1, or P2 issue remains.

Final result: passed

## Wide-product parcel correction

- Source visual truth:
  `docs/design-research/motion-reference/04-reference-open-1000ms.jpg`.
- Implementation:
  `docs/design-research/motion-reference/19-colgate-floating-above-parcel-final.jpg`.
- Combined 1280 × 720 comparison:
  `docs/design-research/motion-reference/20-colgate-reference-vs-final.jpg`.
- [P1 fixed] The toothpaste pack is much wider and shorter than the other
  products, so a shared percentage-based translate left it visually buried in
  the parcel. Reveal content now supports a product-specific vertical anchor;
  Colgate uses that anchor with a larger settled scale and floats clearly above
  the open carton while remaining behind the front parcel wall.
- Browser console: no errors or warnings.
- Frontend production build: passed.
- Frontend unit tests: 8 passed.

Final result: passed

## Shelf scale and staged-motion refinement

### Comparison target

- Source visual truth:
  `docs/design-research/motion-reference/01-reference-home.jpg` through
  `04-reference-open-1000ms.jpg` — the supplied sneaker site, used only for
  spatial calm and staged parcel motion.
- Implementation captures:
  `docs/design-research/motion-reference/14-restock-home-enlarged-final.jpg`,
  `10-restock-motion-90ms-final.jpg`,
  `11-restock-motion-450ms-final.jpg`, and
  `12-restock-motion-1000ms-final.jpg`.
- Viewport/state: both source and Home captures are 1280 × 720 CSS pixels,
  one physical pixel per CSS pixel. The full-view comparison is the settled
  initial state; the focused comparisons are the 90 ms and settled parcel
  states.
- Combined comparison evidence:
  `docs/design-research/motion-reference/15-full-view-reference-vs-restock-final.jpg`,
  `16-open-90ms-reference-vs-restock-final.jpg`, and
  `17-open-settled-reference-vs-restock-final.jpg`.

### Required fidelity surfaces

- **Fonts and typography:** Restock deliberately retains its existing
  functional Inter/Geist/handwritten label hierarchy rather than borrowing
  the reference’s brand type. Product names, price pins, and status text stay
  legible at the enlarged scale and remain within their note.
- **Spacing and layout rhythm:** the pantry now owns the full 720 px viewport
  beneath the fixed 74 px header. Shelf levels were rebalanced so the 7 larger
  product images and their labels all fit in the first view with visible row
  gaps.
- **Colors and tokens:** the quiet ivory backdrop, paper labels, warm wood,
  and Restock green parcel face preserve the existing palette. Motion tokens
  now use a shared settle, spring, and reveal curve rather than unrelated
  easing values.
- **Image quality and asset fidelity:** product images remain source packshots
  and the Parcel uses its existing branded artwork; neither is a recreated
  reference asset. The source brand, imagery, and copy are not reused.
- **Copy and content:** the pantry note is now a compact shelf-side note so it
  no longer takes priority over the products.

### Iteration history

- [P1 fixed] Products were visually too small and required scrolling pressure
  in the first viewport. The page padding was removed at desktop, the stage
  now occupies the space below the persistent header, product height budgets
  increased, and shelf positions/label proportions were recalibrated. Post-fix
  evidence: `14-restock-home-enlarged-final.jpg` shows all seven tracked
  products and labels without cropping.
- [P2 fixed] Parcel motion felt like competing clocks rather than one physical
  action. The open carton now appears before the product at 90 ms, the product
  rises by 450 ms, and settles in a restrained float. Post-fix evidence:
  `16-open-90ms-reference-vs-restock-final.jpg` and
  `17-open-settled-reference-vs-restock-final.jpg`.
- [P2 fixed] Hover and paper motion used inconsistent timing. Shared motion
  tokens now govern shelf tilt, award tilt, label settling, and parcel reveal;
  the Teams shelf was rechecked in
  `13-teams-shelf-motion-final.jpg`.

### Verification

- Browser-rendered Home initial state, parcel reveal, and Teams shelf were
  inspected. No console errors or warnings were present in this pass.
- Home and Teams retain the primary interactions: product/award opening,
  parcel reveal, and navigation state.
- `prefers-reduced-motion` disables the new perspective transforms in addition
  to the existing animation-duration reduction.

### Follow-up polish

- [P3] Tune individual product crops only if a future real merchant catalogue
  introduces an unusually wide or tall package.

Final result: passed

## Paper billing and single-clock parcel correction

- Evidence:
  `docs/design-research/paper-billing-audit-after/01-parcel-immediate.png`
  through `04-teams-receipt-final.png`.
- Required combined review:
  `docs/design-research/paper-billing-audit-after/05-reference-before-after.png`.
- Research and implementation rationale:
  `docs/design-research/paper-billing-audit-after/research-notes.md`.
- The closed-poster/WebGL crossfade and the second delayed opening clock were
  removed. The replacement is one articulated WebGL parcel with four physical
  flap pivots, a stable front panel, and a stable Restock mark. The mark no
  longer swaps position or disappears between closed and open states.
- The parcel now uses a CC0 ambientCG cardboard texture and responds on its
  first rendered frame. The product/provider object overlaps the flap motion
  rather than waiting for a second reveal.
- Teams billing is one continuous receipt with ledger rows, perforated
  sections, plan slips, a separate review tear-off, and standard radio/button
  semantics. The prior nested card dashboard is no longer rendered.
- Pointer-velocity wind is limited to paper, written outside React render
  state, reset over controls, disabled for touch, and removed with reduced
  motion.
- A personalized pantry folio and notification center now live in the header.
  The profile uses `/api/v1/me`, `/api/v1/tenants`, and runtime capabilities
  when available; notification presentation is separate from workflow actions,
  so dismissing a popup cannot skip a purchase or renewal.

Verification for this correction:

- Frontend production build: passed.
- Frontend unit tests: 8 passed.
- Frontend production dependency audit: 0 vulnerabilities.
- Full Python suite in the project virtual environment: 321 passed, 1 skipped,
  7 deselected.
- `git diff --check`: passed.

## Above-the-fold pantry and premium parcel correction

- Evidence:
  `docs/design-research/single-parcel-profile-audit-after/07-home-first-fold-all-products.jpg`,
  `17-premium-parcel-fixed-closed.jpg`,
  `18-premium-parcel-product-inside.jpg`,
  `21-teams-receipt-readable.jpg`, and `22-profile-folio-final.jpg`.
- Required reference/before/after comparison:
  `docs/design-research/single-parcel-profile-audit-after/23-reference-before-after-parcel.jpg`.
- Home no longer spends the first viewport on a separate marketing hero. The
  explanation is a quiet shelf-side note, while all seven active products are
  visible within the initial 936 × 863 desktop viewport. The measured document
  height differs from the viewport by only the page border.
- White packaging artwork is preserved. Colgate, Surf Excel, and Tata Salt now
  use edge-connected background removal rather than global white keying, so
  white logos and printed product areas remain opaque.
- The temporary articulated geometry was removed after comparison showed that
  it solved loading state but lost the premium package finish. The current
  compositor preloads the matched Restock closed/open artwork and performs one
  controlled transition with no different box underneath it.
- The Restock mark is fully contained on the green parcel face in both states.
  A clipped copy of the open parcel's front wall renders above the reveal
  content, so products and provider awards visually emerge from inside the box
  instead of floating in front of it.
- The Home product, Teams award, billing receipt, and profile folio were
  visually inspected at the default desktop viewport. Home was also measured
  at 390 × 844 with width and height overflow absent and all active products
  visible in the initial viewport.

## Motion QA conclusion

The 1280 × 720 full-view and focused staged-reveal comparisons in
`docs/design-research/motion-reference/15-full-view-reference-vs-restock-final.jpg`,
`16-open-90ms-reference-vs-restock-final.jpg`, and
`17-open-settled-reference-vs-restock-final.jpg` confirm the final Home state
and parcel sequence after the shelf-scale revision. No actionable P0, P1, or
P2 issue remains in the current visual QA pass.

Final result: passed

## Final Colgate reveal check

The wide-pack reveal correction is verified in
`docs/design-research/motion-reference/20-colgate-reference-vs-final.jpg`.
The toothpaste pack now clears the parcel opening, remains correctly layered
behind the front wall, and settles above the carton with no clipping. No
actionable P0, P1, or P2 issue remains.

Final result: passed

## Final Aquaguard reveal check

The tall filter-kit correction is verified in
`docs/design-research/motion-reference/21-aquaguard-floating-above-parcel-final.jpg`.
The product-specific reveal anchor places both cartridges clearly above the
open parcel while preserving the front-wall depth cue and ambient float. No
actionable P0, P1, or P2 issue remains.

Final result: passed

## Activity streak and achievement badges

### Comparison target

- Source visual truth:
  `docs/design-research/activity-streak/03-fitness-badge-artwork.jpg`, supplied
  through the Dribbble “Fitness App – Badges” reference.
- Previous Activity implementation:
  `docs/design-research/activity-streak/01-activity-before.jpg`.
- Final implementation:
  `docs/design-research/activity-streak/04-activity-streak-after-viewport.jpg`
  and `06-activity-badges-after.jpg`.
- Combined comparison evidence:
  `docs/design-research/activity-streak/08-activity-before-after.jpg` and
  `09-badge-reference-vs-restock.jpg`.
- Viewport/state: source reference and implementation comparisons are
  normalized to 1280 × 720 pixels at the loaded Activity state.

### Required fidelity surfaces

- **Typography:** the existing Radio Canada Big, Inter, and Geist Pixel
  hierarchy remains intact; the new score, day labels, badge names, and compact
  metadata are legible and consistently weighted.
- **Spacing and rhythm:** the score medallion, seven-day timeline, badges, and
  recent wins read as four clear layers with no overlapping labels.
- **Color and tokens:** earned badges adopt the reference’s gold, amber, green,
  and locked progression while remaining within Restock’s muted paper palette.
- **Image and icon quality:** all badge symbols use the existing Phosphor icon
  system. The completed-product milestone retains its source product packshot.
- **Copy:** “pantry coverage streak” is defined explicitly so the mechanic
  cannot imply an unauthorized purchase or reward excessive shopping.

### Iteration history

- [P1 fixed] The prior “completed cycle” process card did not read as a daily
  fitness-style streak. It is replaced by a prominent seven-day score and one
  checked calendar marker per day.
- [P2 fixed] Progress had no visible achievement language. Three earned
  medallions and one locked next milestone now make progression scannable,
  using the supplied reference as hierarchy inspiration rather than copied
  artwork.
- [P2 fixed] The badge hash target initially aligned underneath the sticky
  header. A dedicated scroll margin now keeps the heading visible.

### Verification

- Primary Activity route and anchored badge state render in the browser.
- Browser console: no errors or warnings.
- Frontend production build: passed.
- Frontend unit tests: 8 passed.
- No actionable P0, P1, or P2 issue remains.

Final result: passed
