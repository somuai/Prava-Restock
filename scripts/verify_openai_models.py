#!/usr/bin/env python3
"""Verify that Restock's configured OpenAI model is usable by this account.

This is a local, credentialed preflight check. It is intentionally not part of
CI and never prints model responses or account-identifying response data.
"""

from __future__ import annotations

from pathlib import Path
import sys

from dotenv import dotenv_values
from openai import OpenAI

from agent.orchestrator import ORCHESTRATOR_MODEL


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = ORCHESTRATOR_MODEL


def _safe_error(error: Exception, api_key: str) -> str:
    """Return the SDK's error while defensively redacting the API key."""
    return f"{type(error).__name__}: {error}".replace(api_key, "[REDACTED]")


def main() -> int:
    api_key = dotenv_values(PROJECT_ROOT / ".env").get("OPENAI_API_KEY")
    if not api_key or api_key.startswith("<"):
        print(f"FAIL {MODEL_ID}: OPENAI_API_KEY is missing from .env")
        return 1

    client = OpenAI(api_key=api_key)

    try:
        listed_model_ids = {model.id for model in client.models.list().data}
    except Exception as error:  # SDK exceptions vary by transport/status.
        message = _safe_error(error, api_key)
        print(f"FAIL {MODEL_ID}: models-list request failed: {message}")
        return 1

    listed = MODEL_ID in listed_model_ids
    invocation_error: Exception | None = None

    try:
        client.responses.create(
            model=MODEL_ID,
            input="Reply only with OK.",
            reasoning={"effort": "none"},
            max_output_tokens=16,
            store=False,
        )
    except Exception as error:  # SDK exceptions vary by transport/status.
        invocation_error = error

    if listed and invocation_error is None:
        print(f"PASS {MODEL_ID}: listed and invocation succeeded")
        return 0

    problems: list[str] = []
    if not listed:
        problems.append("not present in models-list response")
    if invocation_error is not None:
        problems.append(f"invocation failed: {_safe_error(invocation_error, api_key)}")
    print(f"FAIL {MODEL_ID}: {'; '.join(problems)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
