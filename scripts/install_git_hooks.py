#!/usr/bin/env python3
"""Install Restock's tracked Git hooks into the current clone."""

from __future__ import annotations

import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOOKS_PATH = ".githooks"


def install(repository: Path = PROJECT_ROOT) -> None:
    repository = repository.resolve()
    hook = repository / HOOKS_PATH / "pre-commit"
    if not hook.is_file():
        raise FileNotFoundError(f"tracked pre-commit hook is missing: {hook}")
    subprocess.run(
        ["git", "config", "--local", "core.hooksPath", HOOKS_PATH],
        cwd=repository,
        check=True,
    )


def main() -> int:
    install()
    print("PASS installed tracked Git hooks from .githooks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
