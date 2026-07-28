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

For every `order_products__prior.csv` line marked `reordered=1`, the extractor
uses that order's `days_since_prior_order` and groups the interval by the
product's mapped department. This is an order-basket interval attached to a
reordered line item, not an exact same-SKU survival interval. It is adequate
only as a weak, transparent cold-start prior.

The checked-in values are the only derived output; the raw dataset is neither
checked in nor loaded by the application:

| Restock Category | Instacart Department(s) | Reordered lines | Average | Median used as prior |
|---|---|---:|---:|---:|
| `grocery` | beverages, snacks, pantry | 4,066,166 | 10.2085 days | 7.0 days |
| `health` | personal care | 143,584 | 10.6572 days | 7.0 days |
| `stationery` | (no match) | — | — | — |
| `saas_subscription` | N/A | — | — | — |
| `other` | (no match) | — | — | — |

The result is reproducible with:

```bash
python scripts/extract_category_priors.py /path/to/unmodified-instacart-csvs
```

The four input SHA-256 hashes, exact sample counts, averages, medians, dataset
reference, version, and method are stored beside the lookup values in
`triggers/category_priors.json`. The extraction script uses only the Python
standard library.

### How it is used

The values in `triggers/category_priors.json` seed `typical_cadence_days` for
new `TrackedItem` records that have no purchase history. This is a one-time
offline extraction producing a small static lookup table — **not** a trained
model.

- The prior is used only when a new item is created with no purchase history.
- Per-user EWMA recalibration (α = 0.3) progressively replaces the prior after
  completed purchase cycles.
- The prior does not personalize per user — it is a category-level aggregate.

See `TECHNICAL_PRD.md` §6.1 for the recalibration formula and `PRD.md` §27
for why a real forecasting model is post-hackathon scope.
