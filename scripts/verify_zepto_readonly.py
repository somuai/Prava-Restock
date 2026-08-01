"""Safely verify Zepto OAuth and optional catalog search without printing PII."""

from __future__ import annotations

import argparse

from merchant.zepto_checkout import list_saved_address_summaries, search_catalog
from merchant.zepto_mcp import ZeptoRateLimitError


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="")
    args = parser.parse_args()

    addresses = list_saved_address_summaries()
    print(f"PASS Zepto OAuth saved_address_count={len(addresses)}")
    if not addresses:
        return 1
    if not args.query.strip():
        return 0
    try:
        products = search_catalog(
            args.query.strip(), address_ref=addresses[0].reference
        )
    except ZeptoRateLimitError as exc:
        retry = int(exc.retry_after_seconds or 0)
        print(f"BLOCKED Zepto provider rate_limit retry_after_seconds={retry}")
        return 75
    print(f"PASS Zepto catalog exact_result_count={len(products)}")
    if products:
        product = products[0]
        print(
            "PASS Zepto quote "
            f"amount_present={product.amount > 0} "
            f"stock={product.stock_status.value} "
            f"mode={product.execution_mode.value}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
