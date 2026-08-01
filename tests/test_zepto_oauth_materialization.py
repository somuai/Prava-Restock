from __future__ import annotations

import base64
import json
import stat

import pytest

from scripts.materialize_zepto_oauth_cache import (
    OAuthCacheMaterializationError,
    materialize,
)


HASH = "9b36d85502a1fef918a5db7d2b8d830b"


def _bundle(files: dict[str, bytes]) -> str:
    payload = {
        name: base64.b64encode(content).decode("ascii")
        for name, content in files.items()
    }
    return base64.b64encode(json.dumps(payload).encode()).decode("ascii")


def _valid_files() -> dict[str, bytes]:
    return {
        f"{HASH}_client_info.json": b'{"client_id":"redacted"}',
        f"{HASH}_code_verifier.txt": b"redacted-verifier",
        f"{HASH}_tokens.json": b'{"access_token":"redacted"}',
    }


def test_materializes_only_expected_files_with_private_permissions(tmp_path) -> None:
    environment = {
        "RESTOCK_ENV": "production",
        "HOME_MERCHANT_MODE": "real",
        "MCP_REMOTE_CONFIG_DIR": str(tmp_path),
        "ZEPTO_MCP_AUTH_CACHE_B64": _bundle(_valid_files()),
    }

    assert materialize(environment) is True
    cache = tmp_path / "mcp-remote-0.1.37"
    assert {path.name for path in cache.iterdir()} == set(_valid_files())
    assert stat.S_IMODE(cache.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in cache.iterdir())


def test_production_real_catalog_fails_without_bundle(tmp_path) -> None:
    with pytest.raises(OAuthCacheMaterializationError, match="sealed OAuth cache"):
        materialize(
            {
                "RESTOCK_ENV": "production",
                "HOME_MERCHANT_MODE": "real",
                "MCP_REMOTE_CONFIG_DIR": str(tmp_path),
            }
        )


def test_rejects_path_traversal_without_writing(tmp_path) -> None:
    files = _valid_files()
    files["../tokens.json"] = files.pop(f"{HASH}_tokens.json")
    with pytest.raises(OAuthCacheMaterializationError, match="exactly three|unexpected filename"):
        materialize(
            {
                "MCP_REMOTE_CONFIG_DIR": str(tmp_path),
                "ZEPTO_MCP_AUTH_CACHE_B64": _bundle(files),
            }
        )
    assert list(tmp_path.iterdir()) == []


def test_error_never_contains_secret_content(tmp_path) -> None:
    secret = "must-not-appear"
    with pytest.raises(OAuthCacheMaterializationError) as raised:
        materialize(
            {
                "MCP_REMOTE_CONFIG_DIR": str(tmp_path),
                "ZEPTO_MCP_AUTH_CACHE_B64": _bundle(
                    {f"{HASH}_tokens.json": secret.encode()}
                ),
            }
        )
    assert secret not in str(raised.value)
