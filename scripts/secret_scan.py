#!/usr/bin/env python3
"""Fail safely when staged changes or Git history contain likely credentials.

The detector deliberately combines provider-specific token shapes with
environment/config-style credential assignments.  Empty values and explicit
test/example placeholders remain safe so this repository can document its
configuration contract without teaching the hook to ignore real provider keys.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROVIDER_TOKENS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk_(?:test|live)_[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bxoxb-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\bxapp-[A-Za-z0-9-]{20,}\b"),
    # Meta long-lived user/system-user access tokens use the EAA prefix.
    re.compile(r"\bEAA[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
)
GENERIC_ASSIGNMENT = re.compile(
    r"""(?mx)
    ^[+-]?[ \t]*
    (?:export[ \t]+)?
    ["']?
    (?P<name>
        [A-Z][A-Z0-9_]*
        (?:API_KEY|ACCESS_TOKEN|AUTH_TOKEN|BOT_TOKEN|APP_TOKEN|SIGNING_SECRET|
           CLIENT_SECRET|PRIVATE_KEY|PASSWORD|CREDENTIAL|SECRET)
        [A-Z0-9_]*
    )
    ["']?[ \t]*[:=][ \t]*
    (?P<quote>["']?)
    (?P<value>[^"' \t\r\n,#}]+)
    """
)

_PLACEHOLDER_MARKERS = (
    "placeholder",
    "example",
    "changeme",
    "change-me",
    "replace-me",
    "replace_me",
    "not-a-real",
    "configured-",
    "local-demo",
    "with-more-than",
)


def _is_placeholder(value: str) -> bool:
    """Return whether a value is visibly documentation/test-only."""

    normalized = value.strip().strip("\"'").lower()
    if not normalized:
        return True
    for provider_prefix in ("sk_test_", "sk_live_", "xoxb-", "xapp-"):
        if normalized.startswith(provider_prefix):
            remainder = normalized.removeprefix(provider_prefix)
            if remainder.startswith(
                ("placeholder", "example", "invalid", "test", "fake", "dummy", "key")
            ):
                return True
    if normalized.startswith(("<", "${", "$(", "os.getenv(", "environ.get(")):
        return True
    if normalized.endswith("("):
        # A source-code expression such as ``PaymentCredential(`` or
        # ``password_auth.hash_password(``, not an assigned scalar value.
        return True
    if normalized.startswith("scrypt$"):
        parts = normalized.split("$")
        if (
            len(parts) != 6
            or len(parts[4]) < 22
            or len(parts[5]) < 43
            or len(set(parts[5])) == 1
        ):
            # Deployment-contract tests use deliberately malformed or
            # all-one-character digests. Generated hashes have a 16-byte salt
            # and a 32-byte high-entropy digest.
            return True
    if normalized in {
        "none",
        "null",
        "dummy",
        "fake",
        "invalid",
        "short",
        "test",
        "test-secret",
        "bot-token",
        "app-token",
    }:
        return True
    if normalized.startswith(("your-", "your_")):
        return True
    return any(marker in normalized for marker in _PLACEHOLDER_MARKERS)


def _git_output(arguments: list[str]) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _contains_secret(text: str) -> bool:
    for pattern in PROVIDER_TOKENS:
        for match in pattern.finditer(text):
            if not _is_placeholder(match.group(0)):
                return True
    for match in GENERIC_ASSIGNMENT.finditer(text):
        if not _is_placeholder(match.group("value")):
            return True
    return False


def scan_staged() -> int:
    diff = _git_output(["diff", "--cached", "--no-ext-diff", "--unified=0"])
    added_lines = "\n".join(
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    if _contains_secret(added_lines):
        print("FAIL staged secret scan: likely API credential detected; commit blocked")
        return 1
    print("PASS staged secret scan")
    return 0


def scan_history() -> int:
    history = _git_output(
        ["log", "--all", "-p", "--full-history", "--no-ext-diff", "--"]
    )
    if _contains_secret(history):
        print("FAIL history secret scan: likely API credential detected")
        return 1
    print("PASS history secret scan")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true")
    mode.add_argument("--history", action="store_true")
    arguments = parser.parse_args()

    try:
        return scan_staged() if arguments.staged else scan_history()
    except subprocess.CalledProcessError as error:
        print(f"FAIL secret scan: git exited with status {error.returncode}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
