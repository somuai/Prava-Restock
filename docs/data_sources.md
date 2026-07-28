# Data Sources

## Instacart Market Basket Analysis Dataset

**Source:** [Kaggle — Instacart Market Basket Analysis](https://www.kaggle.com/c/instacart-market-basket-analysis)  
**Original publisher:** Instacart, 2017  
**License and provenance:** The specific [Kaggle mirror used for this
aggregate](https://www.kaggle.com/datasets/psparks/instacart-market-basket-analysis/metadata)
is marked **CC0: Public Domain** in its data card. The original Instacart 2017
release has also been described in published work as non-commercial-use data.
Those terms are not interchangeable, so Restock does not redistribute raw
records or treat this as clearance for a trained production model. Legal review
is required before any broader use.

### What was extracted

Median days-between-reorders at the department/category level, mapped to
Restock's `Category` enum. The checked-in values are the only derived output;
the raw dataset is neither checked in nor loaded by the application:

| Restock Category | Instacart Department(s) | Median Reorder Interval |
|---|---|---|
| `grocery` | beverages, snacks, pantry | 11.0 days |
| `health` | personal care | 18.0 days |
| `stationery` | (no match) | — |
| `saas_subscription` | N/A | — |
| `other` | (no match) | — |

### How it is used

The values in `triggers/category_priors.json` seed `typical_cadence_days` for
new `TrackedItem` records that have no purchase history. This is a one-time
offline extraction producing a small static lookup table — **not** a trained
model.

- The prior is used only when a new item is created with no purchase history.
- Per-user EWMA recalibration (α = 0.3) replaces the prior after the first
  completed purchase cycle.
- The prior does not personalize per user — it is a category-level aggregate.

See `TECHNICAL_PRD.md` §6.1 for the recalibration formula and `PRD.md` §27
for why a real forecasting model is post-hackathon scope.
