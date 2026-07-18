"""Offline EWMA benchmark for consented Restock observation exports.

Input CSV columns: category,actual_interval_days,user_acted. The tool does not
download public datasets or train a production model.
"""

import argparse
import csv
from pathlib import Path

from forecasting.evaluation import ForecastCase, evaluate_predictions, ewma_predictions
from forecasting.priors import cadence_prior_days


def benchmark(path: Path) -> dict[str, float | int]:
    rows = list(csv.DictReader(path.open(newline="")))
    actual = [float(row["actual_interval_days"]) for row in rows]
    initial = cadence_prior_days(rows[0]["category"]) if rows else 30.0
    predicted = ewma_predictions(actual, initial)
    metrics = evaluate_predictions(
        ForecastCase(prediction, observed, user_acted=row["user_acted"].lower() == "true")
        for prediction, observed, row in zip(predicted, actual, rows, strict=True)
    )
    return metrics.__dict__


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    args = parser.parse_args()
    print(benchmark(args.csv))


if __name__ == "__main__":
    main()
