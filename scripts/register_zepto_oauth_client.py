#!/usr/bin/env python3
"""Register Restock's public OAuth client with Zepto's OAuth server.

Zepto publishes a Dynamic Client Registration endpoint.  This command creates
an OAuth client configured for Restock's fixed callback URL; it never asks for
or handles a user's Zepto password or OTP.  Use ``--configure-railway`` only
from an already linked Railway project: it stores the returned client details
directly in Railway variables instead of printing any client secret.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any
from urllib.parse import urlsplit

import httpx

from merchant.zepto_oauth import (
    CALLBACK_PATH,
    ZEPTO_AUTHORIZATION_ENDPOINT,
    ZEPTO_SCOPES,
)


REGISTRATION_ENDPOINT = "https://auth.zepto.co.in/register"


class RegistrationError(RuntimeError):
    """A non-sensitive failure while registering a public OAuth client."""


def validate_callback_url(value: str) -> str:
    base = value.strip().rstrip("/")
    parsed = urlsplit(base)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise RegistrationError("callback base must be a public HTTPS origin")
    return f"{base}{CALLBACK_PATH}"


def register_client(*, callback_url: str, client_name: str = "Restock") -> dict[str, str]:
    """Perform RFC 7591 registration and return only configuration values."""

    payload = {
        "client_name": client_name,
        "redirect_uris": [callback_url],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": ZEPTO_SCOPES,
    }
    try:
        response = httpx.post(
            REGISTRATION_ENDPOINT,
            json=payload,
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        if response.status_code >= 400:
            try:
                error_code = str(response.json().get("error") or "")
            except (ValueError, AttributeError):
                error_code = ""
            if error_code == "invalid_redirect_uri":
                raise RegistrationError(
                    "Zepto has not allowlisted this public callback domain; request allowlisting before retrying"
                )
            response.raise_for_status()
        body: Any = response.json()
    except RegistrationError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise RegistrationError("Zepto OAuth client registration failed") from exc
    if not isinstance(body, dict) or not isinstance(body.get("client_id"), str):
        raise RegistrationError("Zepto registration response did not include a client id")
    result = {"ZEPTO_OAUTH_CLIENT_ID": body["client_id"].strip()}
    if not result["ZEPTO_OAUTH_CLIENT_ID"]:
        raise RegistrationError("Zepto registration response contained an empty client id")
    client_secret = body.get("client_secret")
    if isinstance(client_secret, str) and client_secret:
        result["ZEPTO_OAUTH_CLIENT_SECRET"] = client_secret
    return result


def set_railway_variables(values: dict[str, str]) -> None:
    """Set opaque values without echoing them in the command or output."""

    for key, value in values.items():
        try:
            subprocess.run(
                ["railway", "variables", "set", f"{key}={value}"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RegistrationError("could not save OAuth configuration to Railway") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--public-api-url",
        default=os.getenv("RESTOCK_PUBLIC_API_URL", ""),
        help="Public API origin, e.g. https://restock.example.app",
    )
    parser.add_argument("--client-name", default="Restock")
    parser.add_argument(
        "--configure-railway",
        action="store_true",
        help="Save returned OAuth client values into the linked Railway service.",
    )
    args = parser.parse_args(argv)
    try:
        callback_url = validate_callback_url(args.public_api_url)
        values = register_client(callback_url=callback_url, client_name=args.client_name)
        if args.configure_railway:
            set_railway_variables(values)
            print("Registered Zepto OAuth client and saved it in Railway variables.")
        else:
            # Client IDs are public, but a client secret (if issued) must not
            # be copied to a terminal transcript or chat.  Demand direct
            # platform-secret storage in that uncommon case.
            if "ZEPTO_OAUTH_CLIENT_SECRET" in values:
                raise RegistrationError(
                    "Zepto issued a client secret; rerun with --configure-railway to store it safely"
                )
            print(f"ZEPTO_OAUTH_CLIENT_ID={values['ZEPTO_OAUTH_CLIENT_ID']}")
            print(f"Callback URL: {callback_url}")
    except RegistrationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
