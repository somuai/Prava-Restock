# Activity streak design notes

## Product meaning

The streak measures **pantry coverage**, not shopping frequency. A day is
checked only when every due item was either restocked with approval or
consciously skipped. Passive monitoring alone does not create a purchase, and
Restock never awards a streak for acting without approval.

## Reference translation

The supplied Dribbble shot, “Fitness App – Badges” by Alex Reji, was used as a
reference for compact achievement hierarchy:

- a small collection count;
- earned objects presented as individual medallions;
- distinct gold, amber, green, and locked states;
- concise labels beneath each achievement.

Restock retains its own green, ivory, paper, typography, icons, and
replenishment language. It does not reproduce the source artwork.

## Implemented structure

- A large current-streak medallion leads the page.
- Seven calendar days form one connected checked timeline.
- Longest streak, completed cycles, and watched items provide context.
- A plain-language rule explains exactly when a day counts.
- Three earned pantry badges and one locked next badge make progress tangible.
- Recent completed replenishments remain visible beneath the streak.
- The environment disclosure and detailed audit record remain available below.

## Evidence

- Before: `01-activity-before.jpg`.
- Dribbble page and artwork: `02-fitness-badges-reference.jpg` and
  `03-fitness-badge-artwork.jpg`.
- Final streak viewport: `04-activity-streak-after-viewport.jpg`.
- Final badge section: `06-activity-badges-after.jpg`.
- Combined comparisons: `08-activity-before-after.jpg` and
  `09-badge-reference-vs-restock.jpg`.
