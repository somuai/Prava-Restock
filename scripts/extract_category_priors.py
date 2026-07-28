"""Extract reproducible category-level cold-start priors from Instacart CSVs.

The source dataset records the number of days since each user's previous
basket. For every line marked ``reordered``, this script attributes that
basket interval to the product's department and aggregates only the department
groups Restock can map honestly. The result is a weak cold-start prior, not a
same-SKU survival model and not personalized forecasting.
"""

from __future__ import annotations

import argparse
from array import array
from collections import Counter
import csv
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any


DATASET_REF = "psparks/instacart-market-basket-analysis"
DATASET_VERSION = 1
CATEGORY_DEPARTMENTS = {
    "grocery": {"beverages", "pantry", "snacks"},
    "health": {"personal care"},
}
REQUIRED_FILES = (
    "departments.csv",
    "products.csv",
    "orders.csv",
    "order_products__prior.csv",
)


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _grow(values: array, index: int, fill: float | int) -> None:
    if index >= len(values):
        values.extend([fill] * (index + 1 - len(values)))


def _weighted_median(distribution: Counter[float], count: int) -> float:
    target_low = (count - 1) // 2
    target_high = count // 2
    cumulative = 0
    low_value: float | None = None
    high_value: float | None = None
    for value in sorted(distribution):
        next_cumulative = cumulative + distribution[value]
        if low_value is None and target_low < next_cumulative:
            low_value = value
        if target_high < next_cumulative:
            high_value = value
            break
        cumulative = next_cumulative
    assert low_value is not None and high_value is not None
    return (low_value + high_value) / 2


def extract_priors(data_dir: Path) -> dict[str, Any]:
    """Return the checked-in lookup and full provenance metadata."""
    paths = {name: data_dir / name for name in REQUIRED_FILES}
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing Instacart source files: {', '.join(missing)}")

    department_names: dict[int, str] = {}
    with paths["departments.csv"].open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            department_names[int(row["department_id"])] = row["department"]

    department_to_category = {
        department: category
        for category, departments in CATEGORY_DEPARTMENTS.items()
        for department in departments
    }
    department_ids = {
        department_id: department_to_category[name]
        for department_id, name in department_names.items()
        if name in department_to_category
    }

    product_categories = array("b", [0])
    category_codes = {
        category: code for code, category in enumerate(CATEGORY_DEPARTMENTS, start=1)
    }
    code_categories = {code: category for category, code in category_codes.items()}
    with paths["products.csv"].open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            product_id = int(row["product_id"])
            _grow(product_categories, product_id, 0)
            category = department_ids.get(int(row["department_id"]))
            if category:
                product_categories[product_id] = category_codes[category]

    order_intervals = array("f", [math.nan])
    with paths["orders.csv"].open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            order_id = int(row["order_id"])
            _grow(order_intervals, order_id, math.nan)
            raw_interval = row["days_since_prior_order"]
            if raw_interval:
                order_intervals[order_id] = float(raw_interval)

    counts = Counter({category: 0 for category in CATEGORY_DEPARTMENTS})
    totals = Counter({category: 0.0 for category in CATEGORY_DEPARTMENTS})
    distributions = {
        category: Counter() for category in CATEGORY_DEPARTMENTS
    }
    with paths["order_products__prior.csv"].open(
        newline="", encoding="utf-8"
    ) as source:
        for row in csv.DictReader(source):
            if row["reordered"] != "1":
                continue
            product_id = int(row["product_id"])
            if product_id >= len(product_categories):
                continue
            category_code = product_categories[product_id]
            if category_code == 0:
                continue
            order_id = int(row["order_id"])
            if order_id >= len(order_intervals):
                continue
            interval = float(order_intervals[order_id])
            if math.isnan(interval):
                continue
            category = code_categories[category_code]
            counts[category] += 1
            totals[category] += interval
            distributions[category][interval] += 1

    statistics: dict[str, dict[str, float | int | list[str]]] = {}
    lookup: dict[str, float] = {}
    for category, departments in CATEGORY_DEPARTMENTS.items():
        count = counts[category]
        if count == 0:
            raise ValueError(f"no reordered rows found for category {category!r}")
        median = _weighted_median(distributions[category], count)
        average = totals[category] / count
        lookup[category] = round(median, 2)
        statistics[category] = {
            "departments": sorted(departments),
            "sample_count": count,
            "average_days": round(average, 4),
            "median_days": round(median, 2),
        }

    return {
        "_source": (
            "Kaggle dataset mirror "
            f"{DATASET_REF}, version {DATASET_VERSION}; data card lists CC0-1.0"
        ),
        "_method": (
            "For each prior-order line with reordered=1, aggregate that order's "
            "days_since_prior_order by mapped product department. This is a "
            "basket-interval proxy, not an exact same-SKU reorder interval."
        ),
        "_input_sha256": {
            name: _sha256(path) for name, path in sorted(paths.items())
        },
        "_statistics": statistics,
        **lookup,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "data_dir",
        type=Path,
        help="Directory containing the four unmodified Instacart CSV files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("triggers/category_priors.json"),
    )
    args = parser.parse_args()
    result = extract_priors(args.data_dir)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                category: result["_statistics"][category]
                for category in CATEGORY_DEPARTMENTS
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
