"""Materialize Zepto's MCP OAuth cache from a runtime-only secret.

Railway injects ``ZEPTO_MCP_AUTH_CACHE_B64`` at runtime.  The value is a
base64-encoded JSON object whose keys are the three mcp-remote cache filenames
and whose values are base64-encoded file contents.  Nothing is written into the
image, repository, database, or application logs.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from pathlib import Path
import re
import tempfile


SECRET_ENV = "ZEPTO_MCP_AUTH_CACHE_B64"
MAX_BUNDLE_BYTES = 128 * 1024
MAX_FILE_BYTES = 64 * 1024
ALLOWED_NAME = re.compile(
    r"^[0-9a-f]{32}_(?:client_info\.json|code_verifier\.txt|tokens\.json)$"
)
REQUIRED_SUFFIXES = frozenset(
    {"client_info.json", "code_verifier.txt", "tokens.json"}
)


class OAuthCacheMaterializationError(RuntimeError):
    """The runtime secret cannot be safely materialized."""


def _decode(value: str, *, label: str, maximum: int) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise OAuthCacheMaterializationError(f"{label} is not valid base64") from exc
    if len(decoded) > maximum:
        raise OAuthCacheMaterializationError(f"{label} is too large")
    return decoded


def _cache_directory(environment: dict[str, str]) -> Path:
    root = Path(
        environment.get("MCP_REMOTE_CONFIG_DIR", "~/.mcp-auth")
    ).expanduser()
    return root / "mcp-remote-0.1.37"


def materialize(environment: dict[str, str] | None = None) -> bool:
    """Write the authenticated cache atomically and return whether it existed."""

    env = os.environ if environment is None else environment
    encoded_bundle = env.get(SECRET_ENV, "").strip()
    production_real_catalog = (
        env.get("RESTOCK_ENV") == "production"
        and env.get("HOME_MERCHANT_MODE") == "real"
    )
    if not encoded_bundle:
        if production_real_catalog:
            raise OAuthCacheMaterializationError(
                "live Zepto catalog requires its sealed OAuth cache"
            )
        return False

    raw_bundle = _decode(
        encoded_bundle, label="Zepto OAuth bundle", maximum=MAX_BUNDLE_BYTES
    )
    try:
        payload = json.loads(raw_bundle)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OAuthCacheMaterializationError(
            "Zepto OAuth bundle is not valid JSON"
        ) from exc
    if not isinstance(payload, dict) or len(payload) != 3:
        raise OAuthCacheMaterializationError(
            "Zepto OAuth bundle must contain exactly three files"
        )

    suffixes: set[str] = set()
    decoded_files: dict[str, bytes] = {}
    for filename, encoded_content in payload.items():
        if not isinstance(filename, str) or not ALLOWED_NAME.fullmatch(filename):
            raise OAuthCacheMaterializationError(
                "Zepto OAuth bundle contains an unexpected filename"
            )
        if not isinstance(encoded_content, str):
            raise OAuthCacheMaterializationError(
                "Zepto OAuth bundle contains a non-string file"
            )
        suffix = filename.split("_", 1)[1]
        suffixes.add(suffix)
        decoded_files[filename] = _decode(
            encoded_content,
            label=f"Zepto OAuth {suffix}",
            maximum=MAX_FILE_BYTES,
        )
    if suffixes != REQUIRED_SUFFIXES:
        raise OAuthCacheMaterializationError(
            "Zepto OAuth bundle is missing a required cache file"
        )

    destination = _cache_directory(env)
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(destination, 0o700)
    for filename, content in decoded_files.items():
        with tempfile.NamedTemporaryFile(
            dir=destination, prefix=".oauth-", delete=False
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fchmod(temporary.fileno(), 0o600)
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, destination / filename)
        os.chmod(destination / filename, 0o600)
    return True


def main() -> int:
    materialized = materialize()
    print(
        "PASS Zepto OAuth cache materialized"
        if materialized
        else "PASS Zepto OAuth cache not requested"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
