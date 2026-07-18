"""Small signed bearer-session format for deployments without an external IdP.

Tokens contain only a user identifier and expiry. Production must configure a
high-entropy RESTOCK_SESSION_SECRET and issue tokens after its chosen login
flow; the API never accepts an unsigned user header in production.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def mint(user_id: str, secret: str, ttl_seconds: int = 3600) -> str:
    if len(secret) < 32:
        raise ValueError("session secret must be at least 32 characters")
    payload = _b64(json.dumps(
        {"sub": user_id, "exp": int(time.time()) + ttl_seconds, "v": 1},
        separators=(",", ":"),
        sort_keys=True,
    ).encode())
    signature = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"rst1.{payload}.{signature}"


def verify(token: str, secret: str) -> str:
    try:
        prefix, payload, signature = token.split(".")
        if prefix != "rst1" or len(secret) < 32:
            raise ValueError
        expected = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        claims = json.loads(_unb64(payload))
        if claims.get("v") != 1 or int(claims["exp"]) <= int(time.time()):
            raise ValueError
        return str(claims["sub"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid or expired session") from exc
