"""Constant-time authentication for narrowly scoped internal service routes."""

from __future__ import annotations

import hmac


class ServiceAuthError(ValueError):
    pass


def verify_bearer(authorization: str | None, expected_token: str) -> None:
    if len(expected_token) < 32:
        raise RuntimeError("service token is not configured securely")
    if not authorization or not authorization.startswith("Bearer "):
        raise ServiceAuthError("invalid service authentication")
    provided = authorization.removeprefix("Bearer ")
    if not hmac.compare_digest(provided, expected_token):
        raise ServiceAuthError("invalid service authentication")
