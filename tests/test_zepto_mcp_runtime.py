from pathlib import Path

import pytest

from merchant import zepto_mcp


ROOT = Path(__file__).resolve().parents[1]


def test_mcp_remote_is_exactly_pinned_in_stdio_command(monkeypatch) -> None:
    captured = {}

    class CaptureParameters:
        def __init__(self, *, command, args):
            captured.update(command=command, args=args)

    def stop_before_network(*_args, **_kwargs):
        raise OSError("stop before spawning npx")

    monkeypatch.setattr(zepto_mcp, "StdioServerParameters", CaptureParameters)
    monkeypatch.setattr(zepto_mcp, "stdio_client", stop_before_network)
    monkeypatch.setattr(
        zepto_mcp, "resolve_mcp_remote_binary", lambda: zepto_mcp.MCP_REMOTE_BINARY
    )

    client = zepto_mcp.ZeptoMCPClient()
    try:
        client.call("list_saved_addresses")
    except zepto_mcp.ZeptoMCPError:
        pass

    assert zepto_mcp.MCP_REMOTE_VERSION == "0.1.38"
    assert zepto_mcp.MCP_REMOTE_PACKAGE == "mcp-remote@0.1.38"
    assert zepto_mcp.MCP_REMOTE_BINARY == "/opt/zepto-mcp/node_modules/.bin/mcp-remote"
    assert captured == {
        "command": "/opt/zepto-mcp/node_modules/.bin/mcp-remote",
        "args": [zepto_mcp.ZEPTO_MCP_URL],
    }


def test_development_can_use_absolute_locked_local_binary(tmp_path, monkeypatch) -> None:
    binary = tmp_path / "mcp-remote"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o700)
    monkeypatch.setenv("RESTOCK_ENV", "development")
    monkeypatch.setenv("MCP_REMOTE_BINARY", str(binary))

    assert zepto_mcp.resolve_mcp_remote_binary() == str(binary)


def test_development_prefers_repo_local_locked_install(tmp_path, monkeypatch) -> None:
    binary = tmp_path / "node_modules" / ".bin" / "mcp-remote"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o700)
    monkeypatch.setenv("RESTOCK_ENV", "development")
    monkeypatch.delenv("MCP_REMOTE_BINARY", raising=False)
    monkeypatch.setattr(zepto_mcp, "MCP_REMOTE_REPO_BINARY", binary)

    assert zepto_mcp.resolve_mcp_remote_binary() == str(binary)


def test_development_rejects_relative_binary_override(monkeypatch) -> None:
    monkeypatch.setenv("RESTOCK_ENV", "development")
    monkeypatch.setenv("MCP_REMOTE_BINARY", "merchant/mcp-runtime/mcp-remote")

    with pytest.raises(zepto_mcp.ZeptoMCPError, match="must be absolute"):
        zepto_mcp.resolve_mcp_remote_binary()


def test_production_rejects_binary_override(tmp_path, monkeypatch) -> None:
    binary = tmp_path / "mcp-remote"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o700)
    monkeypatch.setenv("RESTOCK_ENV", "production")
    monkeypatch.setenv("MCP_REMOTE_BINARY", str(binary))

    with pytest.raises(zepto_mcp.ZeptoMCPError, match="immutable production"):
        zepto_mcp.resolve_mcp_remote_binary()


def test_mcp_authorization_verification_is_recent_and_expires(monkeypatch) -> None:
    now = {"value": 100.0}
    monkeypatch.setattr(zepto_mcp.time, "monotonic", lambda: now["value"])
    monkeypatch.setenv("MCP_AUTHORIZATION_VERIFICATION_TTL_SECONDS", "10")
    zepto_mcp.clear_mcp_authorization_verification()

    assert zepto_mcp.mcp_authorization_verified_recently() is False
    zepto_mcp.record_mcp_authorization_success()
    assert zepto_mcp.mcp_authorization_verified_recently() is True

    now["value"] = 111.0
    assert zepto_mcp.mcp_authorization_verified_recently() is False
    zepto_mcp.clear_mcp_authorization_verification()


def test_mcp_call_failure_clears_recent_authorization(monkeypatch) -> None:
    zepto_mcp.record_mcp_authorization_success()
    assert zepto_mcp.mcp_authorization_verified_recently() is True
    monkeypatch.setattr(
        zepto_mcp,
        "resolve_mcp_remote_binary",
        lambda: (_ for _ in ()).throw(zepto_mcp.ZeptoMCPError("unavailable")),
    )

    with pytest.raises(zepto_mcp.ZeptoMCPError):
        zepto_mcp.ZeptoMCPClient().call("list_saved_addresses")

    assert zepto_mcp.mcp_authorization_verified_recently() is False


def test_temporary_zepto_529_is_not_reported_as_an_auth_failure() -> None:
    assert zepto_mcp._is_transient_provider_failure("HTTP 529 overloaded") is True
    assert zepto_mcp._is_rate_limited("HTTP 529 overloaded") is False


def test_429_remains_a_rate_limit_not_a_temporary_auth_failure() -> None:
    assert zepto_mcp._is_rate_limited("HTTP 429 Too Many Requests") is True
    assert zepto_mcp._is_transient_provider_failure("HTTP 429 Too Many Requests") is False


def test_container_includes_node_and_non_root_runtime_verification() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    workflow = (ROOT / ".github/workflows/tests.yml").read_text()
    verifier = (ROOT / "scripts/verify_zepto_mcp_runtime.sh").read_text()

    assert "FROM node:24-slim AS node-runtime" in dockerfile
    assert "merchant/mcp-runtime/package-lock.json" in dockerfile
    assert "npm ci --omit=dev --ignore-scripts" in dockerfile
    assert "COPY --from=node-runtime /usr/local/bin/node" in dockerfile
    assert "npm/bin/npx-cli.js" not in dockerfile
    assert "/usr/local/lib/node_modules" not in dockerfile
    assert "COPY --from=node-runtime /opt/zepto-mcp /opt/zepto-mcp" in dockerfile
    assert dockerfile.index("USER 10001:10001") > dockerfile.index("node --version")
    assert "verify_zepto_mcp_runtime.sh" in workflow
    assert "npm view" not in verifier
    assert "npx " not in verifier
    assert "--network none" in workflow
    assert zepto_mcp.ZEPTO_MCP_URL not in verifier


def test_secret_and_runtime_caches_are_excluded_from_build_context() -> None:
    ignored = set((ROOT / ".dockerignore").read_text().splitlines())

    assert {
        ".mcp-auth",
        "**/.mcp-auth",
        ".npm",
        "**/.npm",
        ".mcp-cache",
        "**/.mcp-cache",
        "runtime-cache",
        "**/runtime-cache",
    } <= ignored
    assert "**/node_modules" in ignored
