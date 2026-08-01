#!/usr/bin/env python3
"""Fail closed on missing production service configuration without printing secrets."""

from __future__ import annotations

import argparse
import base64
import json
import os
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID


REQUIRED_VARIABLES: dict[str, tuple[str, ...]] = {
    "api": (
        "DATABASE_URL",
        "PRAVA_API_KEY",
        "RESTOCK_ENV",
        "RESTOCK_DEMO_MODE",
        "RESTOCK_SESSION_SECRET",
        "RESTOCK_SOLO_USER_ID",
        "RESTOCK_SOLO_PASSWORD_HASH",
        "RESTOCK_SLACK_SERVICE_TOKEN",
        "RESTOCK_WORKER_SERVICE_TOKEN",
    ),
    "worker": (
        "DATABASE_URL",
        "RESTOCK_ENV",
        "RESTOCK_DEMO_MODE",
        "RESTOCK_PUBLIC_API_URL",
        "RESTOCK_WORKER_SERVICE_TOKEN",
    ),
    "slack": (
        "DATABASE_URL",
        "RESTOCK_ENV",
        "RESTOCK_DEMO_MODE",
        "RESTOCK_SLACK_SERVICE_TOKEN",
        "SLACK_BOT_TOKEN",
        "SLACK_APP_TOKEN",
        "SLACK_CHANNEL_ID",
        "SLACK_SIGNING_SECRET",
        "RESTOCK_PUBLIC_API_URL",
        "RESTOCK_PUBLIC_APP_URL",
    ),
}


def _decoded_urlsafe(value: str) -> bytes:
    return base64.b64decode(
        value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
    )


def _valid_scrypt_hash(value: str) -> bool:
    try:
        parts = value.split("$")
        return (
            len(parts) == 6
            and parts[:4] == ["scrypt", "16384", "8", "1"]
            and len(_decoded_urlsafe(parts[4])) >= 16
            and len(_decoded_urlsafe(parts[5])) == 32
        )
    except (ValueError, TypeError):
        return False


def validate(service: str, environment: Mapping[str, str]) -> list[str]:
    if service not in REQUIRED_VARIABLES:
        raise ValueError(f"unknown service: {service}")
    auth_mode = environment.get("RESTOCK_AUTH_MODE", "solo").strip().lower()
    conditionally_optional: set[str] = set()
    if service == "api" and auth_mode == "google":
        conditionally_optional = {
            "RESTOCK_SOLO_USER_ID",
            "RESTOCK_SOLO_PASSWORD_HASH",
        }
    issues = [
        name
        for name in REQUIRED_VARIABLES[service]
        if name not in conditionally_optional and not environment.get(name)
    ]

    if service in {"api", "worker", "slack"}:
        database_url = environment.get("DATABASE_URL", "")
        if database_url and not database_url.startswith(
            ("postgres://", "postgresql://", "postgresql+psycopg://")
        ):
            issues.append("DATABASE_URL_POSTGRES_REQUIRED")
        if environment.get("RESTOCK_ENV") and environment.get("RESTOCK_ENV") != "production":
            issues.append("RESTOCK_ENV_MUST_BE_PRODUCTION")
        if (
            environment.get("RESTOCK_DEMO_MODE")
            and environment.get("RESTOCK_DEMO_MODE") != "0"
        ):
            issues.append("RESTOCK_DEMO_MODE_MUST_BE_DISABLED")

    if service == "api":
        if auth_mode not in {"solo", "hybrid", "google"}:
            issues.append("RESTOCK_AUTH_MODE_INVALID")
        elif auth_mode in {"hybrid", "google"}:
            google_client_id = environment.get("GOOGLE_CLIENT_ID", "").strip()
            if not google_client_id:
                issues.append("GOOGLE_CLIENT_ID")
            elif not google_client_id.endswith(".apps.googleusercontent.com"):
                issues.append("GOOGLE_CLIENT_ID_INVALID")
        secret = environment.get("RESTOCK_SESSION_SECRET", "")
        if secret and len(secret) < 32:
            issues.append("RESTOCK_SESSION_SECRET_TOO_SHORT")
        if auth_mode in {"solo", "hybrid"}:
            password_hash = environment.get("RESTOCK_SOLO_PASSWORD_HASH", "")
            if password_hash and not _valid_scrypt_hash(password_hash):
                issues.append("RESTOCK_SOLO_PASSWORD_HASH_INVALID_FORMAT")
            user_id = environment.get("RESTOCK_SOLO_USER_ID", "")
            if user_id:
                try:
                    UUID(user_id)
                except ValueError:
                    issues.append("RESTOCK_SOLO_USER_ID_INVALID")
        reviewer_names = (
            "RESTOCK_REVIEWER_PASSWORD_HASH",
            "RESTOCK_REVIEWER_USER_ID",
            "RESTOCK_REVIEWER_EXPIRES_AT",
        )
        reviewer_values = {
            name: environment.get(name, "").strip() for name in reviewer_names
        }
        if any(reviewer_values.values()):
            for name, value in reviewer_values.items():
                if not value:
                    issues.append(name)
            reviewer_hash = reviewer_values["RESTOCK_REVIEWER_PASSWORD_HASH"]
            if reviewer_hash and not _valid_scrypt_hash(reviewer_hash):
                issues.append("RESTOCK_REVIEWER_PASSWORD_HASH_INVALID_FORMAT")
            reviewer_id = reviewer_values["RESTOCK_REVIEWER_USER_ID"]
            if reviewer_id:
                try:
                    UUID(reviewer_id)
                except ValueError:
                    issues.append("RESTOCK_REVIEWER_USER_ID_INVALID")
            expires_at = reviewer_values["RESTOCK_REVIEWER_EXPIRES_AT"]
            if expires_at:
                try:
                    parsed_expiry = datetime.fromisoformat(
                        expires_at.replace("Z", "+00:00")
                    )
                    if parsed_expiry.tzinfo is None:
                        raise ValueError("timezone required")
                except ValueError:
                    issues.append("RESTOCK_REVIEWER_EXPIRES_AT_INVALID")
        for name in (
            "RESTOCK_DEFAULT_MONTHLY_CAP",
            "RESTOCK_DEFAULT_PER_ITEM_CAP",
            "RESTOCK_DEFAULT_PER_TRANSACTION_CAP",
        ):
            raw = environment.get(name, "").strip()
            if raw:
                try:
                    value = Decimal(raw)
                    if not value.is_finite() or value <= 0:
                        raise ValueError
                except (InvalidOperation, ValueError):
                    issues.append(f"{name}_INVALID")
        allowed_origins = [
            value.strip()
            for value in environment.get("RESTOCK_ALLOWED_ORIGINS", "").split(",")
            if value.strip()
        ]
        if "*" in allowed_origins:
            issues.append("RESTOCK_ALLOWED_ORIGINS_WILDCARD_FORBIDDEN")

    if service == "api":
        api_key = environment.get("PRAVA_API_KEY", "")
        api_url = (
            environment.get("PRAVA_API_URL", "")
            or environment.get("PRAVA_SANDBOX_URL", "")
        ).rstrip("/")
        if not api_url:
            issues.append("PRAVA_API_URL_OR_SANDBOX_URL_REQUIRED")
        elif api_key.startswith("sk_test_"):
            if api_url != "https://sandbox.api.prava.space":
                issues.append("PRAVA_SANDBOX_KEY_URL_MISMATCH")
            if environment.get("PRAVA_PRODUCTION_ENABLED") == "1":
                issues.append("PRAVA_SANDBOX_WITH_PRODUCTION_GATE")
        elif api_key.startswith("sk_live_"):
            if api_url != "https://api.prava.space":
                issues.append("PRAVA_LIVE_KEY_URL_MISMATCH")
            if environment.get("PRAVA_PRODUCTION_ENABLED") != "1":
                issues.append("PRAVA_PRODUCTION_GATE_REQUIRED")
        elif api_key:
            issues.append("PRAVA_API_KEY_INVALID_PREFIX")
        if environment.get("HOME_MERCHANT_MODE") == "real":
            if not environment.get("ZEPTO_DEVICE_ID", "").strip():
                issues.append("ZEPTO_DEVICE_ID_REQUIRED")
            if environment.get("ZEPTO_CART_PREPARATION_ENABLED") != "1":
                issues.append("ZEPTO_CART_PREPARATION_GATE_REQUIRED")
        payment_mode = environment.get("HOME_PAYMENT_MODE", "disclosed_mock")
        if payment_mode not in {"real", "sandbox", "disclosed_mock"}:
            issues.append("HOME_PAYMENT_MODE_INVALID")
        if payment_mode == "real":
            if environment.get("HOME_MERCHANT_MODE") != "real":
                issues.append("REAL_PAYMENT_REQUIRES_REAL_CATALOG")
            if environment.get("ZEPTO_REAL_PAYMENT_ENABLED") != "1":
                issues.append("ZEPTO_REAL_PAYMENT_GATE_REQUIRED")
            hosts = [
                host.strip()
                for host in environment.get("ZEPTO_PAYMENT_ALLOWED_HOSTS", "").split(",")
                if host.strip()
            ]
            if not hosts:
                issues.append("ZEPTO_PAYMENT_ALLOWED_HOSTS_REQUIRED")
            executable = environment.get("ZEPTO_PAYMENT_EXECUTOR_PATH", "").strip()
            if not executable:
                issues.append("ZEPTO_PAYMENT_EXECUTOR_PATH_REQUIRED")
            elif not Path(executable).is_absolute():
                issues.append("ZEPTO_PAYMENT_EXECUTOR_PATH_MUST_BE_ABSOLUTE")
            elif not Path(executable).is_file() or not os.access(executable, os.X_OK):
                issues.append("ZEPTO_PAYMENT_EXECUTOR_PATH_INVALID")
        teams_mode = environment.get("TEAMS_BILLING_MODE", "disclosed_mock")
        if teams_mode not in {"real", "disclosed_mock"}:
            issues.append("TEAMS_BILLING_MODE_INVALID")
        if teams_mode == "real":
            if environment.get("TEAMS_REAL_PAYMENT_ENABLED") != "1":
                issues.append("TEAMS_REAL_PAYMENT_GATE_REQUIRED")
            if environment.get("TEAMS_RECURRING_ENABLED") == "1":
                issues.append("TEAMS_RECURRING_MANDATE_UNCONFIRMED")
            teams_hosts = [
                host.strip()
                for host in environment.get("TEAMS_PAYMENT_ALLOWED_HOSTS", "").split(",")
                if host.strip()
            ]
            if not teams_hosts:
                issues.append("TEAMS_PAYMENT_ALLOWED_HOSTS_REQUIRED")
            teams_executable = environment.get(
                "TEAMS_PAYMENT_EXECUTOR_PATH", ""
            ).strip()
            if not teams_executable:
                issues.append("TEAMS_PAYMENT_EXECUTOR_PATH_REQUIRED")
            elif not Path(teams_executable).is_absolute():
                issues.append("TEAMS_PAYMENT_EXECUTOR_PATH_MUST_BE_ABSOLUTE")
            elif not Path(teams_executable).is_file() or not os.access(
                teams_executable, os.X_OK
            ):
                issues.append("TEAMS_PAYMENT_EXECUTOR_PATH_INVALID")
            raw_links = environment.get("TEAMS_HOSTED_INVOICE_LINKS_JSON", "").strip()
            try:
                links = json.loads(raw_links) if raw_links else None
            except json.JSONDecodeError:
                links = None
            if not isinstance(links, dict) or not links:
                issues.append("TEAMS_HOSTED_INVOICE_LINKS_JSON_REQUIRED")
            elif any(
                not isinstance(reference, str)
                or not isinstance(url, str)
                or urlsplit(url).scheme != "https"
                or not urlsplit(url).hostname
                or urlsplit(url).hostname not in teams_hosts
                or urlsplit(url).username is not None
                or urlsplit(url).password is not None
                for reference, url in links.items()
            ):
                issues.append("TEAMS_HOSTED_INVOICE_LINKS_JSON_INVALID")
        mcp_override = environment.get("MCP_REMOTE_BINARY", "").strip()
        if environment.get("RESTOCK_ENV") == "production" and mcp_override:
            if Path(mcp_override) != Path("/opt/zepto-mcp/node_modules/.bin/mcp-remote"):
                issues.append("MCP_REMOTE_BINARY_IMMUTABLE_IN_PRODUCTION")

    if service == "slack":
        if environment.get("SLACK_BOT_TOKEN") and not environment["SLACK_BOT_TOKEN"].startswith(
            "xoxb-"
        ):
            issues.append("SLACK_BOT_TOKEN_INVALID_PREFIX")
        if environment.get("SLACK_APP_TOKEN") and not environment["SLACK_APP_TOKEN"].startswith(
            "xapp-"
        ):
            issues.append("SLACK_APP_TOKEN_INVALID_PREFIX")
        signing_secret = environment.get("SLACK_SIGNING_SECRET", "")
        if signing_secret and len(signing_secret) < 32:
            issues.append("SLACK_SIGNING_SECRET_TOO_SHORT")
        api_url = environment.get("RESTOCK_PUBLIC_API_URL", "")
        if api_url and urlsplit(api_url).scheme != "https":
            issues.append("RESTOCK_PUBLIC_API_URL_HTTPS_REQUIRED")
        app_url = environment.get("RESTOCK_PUBLIC_APP_URL", "")
        if app_url and urlsplit(app_url).scheme != "https":
            issues.append("RESTOCK_PUBLIC_APP_URL_HTTPS_REQUIRED")
    if service in {"api", "slack"}:
        service_token = environment.get("RESTOCK_SLACK_SERVICE_TOKEN", "")
        if service_token and len(service_token) < 32:
            issues.append("RESTOCK_SLACK_SERVICE_TOKEN_TOO_SHORT")

    if service in {"api", "worker"}:
        worker_token = environment.get("RESTOCK_WORKER_SERVICE_TOKEN", "")
        if worker_token and len(worker_token) < 32:
            issues.append("RESTOCK_WORKER_SERVICE_TOKEN_TOO_SHORT")
    if service == "worker":
        api_url = environment.get("RESTOCK_PUBLIC_API_URL", "")
        if api_url and urlsplit(api_url).scheme != "https":
            issues.append("RESTOCK_PUBLIC_API_URL_HTTPS_REQUIRED")

    return sorted(set(issues))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("service", choices=sorted(REQUIRED_VARIABLES))
    args = parser.parse_args()
    issues = validate(args.service, os.environ)
    if issues:
        raise SystemExit(
            f"FAIL {args.service} configuration: " + ", ".join(issues)
        )
    print(f"PASS {args.service} configuration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
