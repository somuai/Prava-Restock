from pathlib import Path
import shutil
import subprocess

import pytest

from scripts import install_git_hooks, secret_scan


def _joined(*parts: str) -> str:
    """Build credential-shaped fixtures without checking one into Git verbatim."""

    return "".join(parts)


@pytest.mark.parametrize(
    "value",
    [
        lambda: _joined("sk-", "proj-", "A" * 28),
        lambda: _joined("sk_", "test_", "A" * 24),
        lambda: _joined("sk_", "live_", "B" * 24),
        lambda: _joined("xoxb-", "1" * 12, "-", "A" * 24),
        lambda: _joined("xapp-", "1-", "A" * 40),
        lambda: _joined("EAA", "A" * 40),
        lambda: _joined("ghp_", "A" * 36),
        lambda: _joined("github_pat_", "A" * 40),
    ],
)
def test_provider_tokens_are_detected(value) -> None:
    assert secret_scan._contains_secret(value())


@pytest.mark.parametrize(
    "line",
    [
        lambda: _joined("DATABASE_", "PASSWORD=correct-horse-battery-staple"),
        lambda: _joined(
            "export PROVIDER_CLIENT_", "SECRET='private-value-12345'"
        ),
        lambda: _joined(
            '"SERVICE_ACCESS_', 'TOKEN": "production-value-12345",'
        ),
        lambda: _joined("PAYMENT_", "CREDENTIAL: merchant-value-12345"),
    ],
)
def test_generic_credential_assignments_are_detected(line) -> None:
    assert secret_scan._contains_secret(line())


@pytest.mark.parametrize(
    "line",
    [
        "OPENAI_API_KEY=",
        "PRAVA_API_KEY=sk_test_placeholder",
        "SLACK_BOT_TOKEN=xoxb-placeholder",
        "WHATSAPP_ACCESS_TOKEN=<set-in-platform-secrets>",
        "CLIENT_SECRET=${CLIENT_SECRET}",
        'RESTOCK_SESSION_SECRET="a-high-entropy-placeholder-at-least-32-chars"',
        'SERVICE_TOKEN = "worker-service-token-with-more-than-32-characters"',
        'LOCAL_DEMO_TOKEN = "restock-local-demo-token"',
    ],
)
def test_documented_and_test_placeholders_are_allowed(line: str) -> None:
    assert not secret_scan._contains_secret(line)


def test_tracked_hook_installer_sets_repository_local_hooks_path(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    hook_directory = repository / ".githooks"
    hook_directory.mkdir(parents=True)
    (hook_directory / "pre-commit").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repository)], check=True)

    install_git_hooks.install(repository)

    configured = subprocess.run(
        ["git", "config", "--local", "--get", "core.hooksPath"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert configured == ".githooks"


def test_tracked_pre_commit_hook_invokes_staged_secret_scan() -> None:
    hook = (
        Path(__file__).resolve().parents[1] / ".githooks" / "pre-commit"
    ).read_text(encoding="utf-8")

    assert "scripts/secret_scan.py" in hook
    assert "--staged" in hook


def test_fresh_clone_hook_blocks_a_staged_provider_secret(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1]
    repository = tmp_path / "fresh-clone"
    (repository / "scripts").mkdir(parents=True)
    (repository / ".githooks").mkdir()
    shutil.copy2(source_root / "scripts" / "secret_scan.py", repository / "scripts")
    shutil.copy2(source_root / ".githooks" / "pre-commit", repository / ".githooks")
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    install_git_hooks.install(repository)

    candidate = _joined("xoxb-", "1" * 12, "-", "A" * 24)
    (repository / "unsafe.env").write_text(
        f"SLACK_BOT_TOKEN={candidate}\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "unsafe.env"], cwd=repository, check=True)

    result = subprocess.run(
        [str(repository / ".githooks" / "pre-commit")],
        cwd=repository,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "commit blocked" in result.stdout
