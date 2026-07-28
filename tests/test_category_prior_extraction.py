import csv
from scripts.extract_category_priors import extract_priors


def _write_csv(path, fieldnames, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_extract_category_priors_is_reproducible_and_records_provenance(
    tmp_path,
) -> None:
    _write_csv(
        tmp_path / "departments.csv",
        ["department_id", "department"],
        [
            {"department_id": 7, "department": "beverages"},
            {"department_id": 11, "department": "personal care"},
        ],
    )
    _write_csv(
        tmp_path / "products.csv",
        ["product_id", "product_name", "aisle_id", "department_id"],
        [
            {
                "product_id": 1,
                "product_name": "Coffee",
                "aisle_id": 1,
                "department_id": 7,
            },
            {
                "product_id": 2,
                "product_name": "Filter",
                "aisle_id": 2,
                "department_id": 11,
            },
        ],
    )
    _write_csv(
        tmp_path / "orders.csv",
        [
            "order_id",
            "user_id",
            "eval_set",
            "order_number",
            "order_dow",
            "order_hour_of_day",
            "days_since_prior_order",
        ],
        [
            {
                "order_id": 1,
                "user_id": 1,
                "eval_set": "prior",
                "order_number": 2,
                "order_dow": 1,
                "order_hour_of_day": 8,
                "days_since_prior_order": "10.0",
            },
            {
                "order_id": 2,
                "user_id": 1,
                "eval_set": "prior",
                "order_number": 3,
                "order_dow": 1,
                "order_hour_of_day": 8,
                "days_since_prior_order": "14.0",
            },
            {
                "order_id": 3,
                "user_id": 2,
                "eval_set": "prior",
                "order_number": 2,
                "order_dow": 1,
                "order_hour_of_day": 8,
                "days_since_prior_order": "20.0",
            },
        ],
    )
    _write_csv(
        tmp_path / "order_products__prior.csv",
        ["order_id", "product_id", "add_to_cart_order", "reordered"],
        [
            {
                "order_id": 1,
                "product_id": 1,
                "add_to_cart_order": 1,
                "reordered": 1,
            },
            {
                "order_id": 2,
                "product_id": 1,
                "add_to_cart_order": 1,
                "reordered": 1,
            },
            {
                "order_id": 3,
                "product_id": 2,
                "add_to_cart_order": 1,
                "reordered": 1,
            },
        ],
    )

    first = extract_priors(tmp_path)
    second = extract_priors(tmp_path)

    assert first == second
    assert first["grocery"] == 12.0
    assert first["health"] == 20.0
    assert first["_statistics"]["grocery"] == {
        "departments": ["beverages", "pantry", "snacks"],
        "sample_count": 2,
        "average_days": 12.0,
        "median_days": 12.0,
    }
    assert set(first["_input_sha256"]) == {
        "departments.csv",
        "order_products__prior.csv",
        "orders.csv",
        "products.csv",
    }
    assert all(len(value) == 64 for value in first["_input_sha256"].values())
