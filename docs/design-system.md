# Restock design system

## Product direction

Restock uses a **decision inbox**, not a marketing-dashboard layout. The visual system is deliberately quiet: neutral surfaces carry most of the interface, teal marks approvals and Restock-owned actions, indigo distinguishes Teams decisions, and amber only identifies something that needs attention.

The system borrows interaction discipline rather than trade dress:

- WhatsApp's 2024 redesign increased its use of neutrals and became more selective about where green appears. Restock follows that restraint without copying WhatsApp's palette or chat wallpaper. Source: [Meta — Keeping WhatsApp Modern, Simple and Accessible](https://about.fb.com/br/news/2024/05/mantendo-o-whatsapp-moderno-simples-e-acessivel/).
- Slack's Block Kit guidance recommends progressive disclosure, concise buttons, context blocks for secondary information, and color plus text—not color alone—to communicate meaning. Restock applies those rules to Teams approvals without copying Slack's visual identity. Source: [Slack — Designing with Block Kit](https://docs.slack.dev/concepts/designing-with-block-kit).
- IBM Plex Sans is self-hosted through the pinned Fontsource package. It replaces the previous unimported Inter/Georgia pairing with one consistent product typeface. The interface uses only regular, medium, and semibold optical roles. Source: [Carbon Design System — Typography](https://carbondesignsystem.com/elements/typography/overview/).

## Logo

The Restock mark is a parcel on a shelf with a single replenishment arrow and approval cutout. It encodes the core workflow: an item is detected, the user approves it, and it is replenished. It intentionally contains no letterform, shopping cart, or merchant-specific symbol.

Primary asset: `ui/web/public/assets/restock-mark.png`.

PWA icons: `restock-icon-192.png` and `restock-icon-512.png`.

## Type

| Role | Size / line height | Weight |
| --- | --- | --- |
| Page title | 30 / 35 px | 600 |
| Decision title | 19 / 26 px | 600 |
| Section title | 17 / 24 px | 600 |
| Body | 14–16 / 21–24 px | 400 |
| Control | 14 / 20 px | 600 |
| Metadata | 11–13 / 16–19 px | 400–500 |

Prices, dates, caps, and thresholds use tabular numerals.

## Color tokens

| Role | Token | Value |
| --- | --- | --- |
| Canvas | `--canvas` | `#F6FAF8` |
| Surface | `--surface` | `#FFFFFF` |
| Subtle surface | `--surface-subtle` | `#EEF5F1` |
| Primary text | `--text` | `#1D2A24` |
| Secondary text | `--text-muted` | `#56655E` |
| Border | `--border` | `#CBD8D1` |
| Restock teal | `--primary` | `#006C67` |
| Teal tint | `--primary-soft` | `#D9F0EC` |
| Teams indigo | `--teams` | `#4F46E5` |
| Attention amber | `--signal` | `#F2C94C` |
| Danger | `--danger` | `#B3261E` |
| Focus | `--focus` | `#175CD3` |

## Interaction rules

- One filled primary action per decision.
- Home approvals use teal; Teams renewals use indigo.
- Skip is explicit red text but remains visually secondary.
- Payment mode disclosure is attached to the affected decision, not only the global header.
- Mobile places approval controls before the longer fact table.
- All core targets are at least 44 px high and have a visible focus ring.
- State is always expressed with text or an icon plus text; color is never the only signal.
- No gradients, glass effects, decorative dashboard metrics, oversized marketing headlines, or nested card stacks.
