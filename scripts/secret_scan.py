#!/usr/bin/env python3
"""Fail safely when staged changes or Git history contain likely API secrets."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OPENAI_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")
PRAVA_KEY = re.compile(
    r"(?m)^[+-]?(?:export[ \t]+)?PRAVA_API_KEY[ \t]*=[ \t]*"
    r"[\"']?([A-Za-z0-9_-]{8,})[\"']?[ \t]*$"
)


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
    return OPENAI_KEY.search(text) is not None or PRAVA_KEY.search(text) is not None


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
