"""OAuth 2.1 + PKCE helpers for user-owned Zepto MCP access.

This uses Zepto's published OAuth authorization server directly.  It avoids
``mcp-remote``'s localhost callback/cache model, which is appropriate for one
person's desktop but not for a multi-user web service.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
import os
import secrets
from urllib.parse import urlencode, urlsplit

import httpx


ZEPTO_AUTHORIZATION_ENDPOINT = "https://auth.zepto.co.in/authorize"
ZEPTO_TOKEN_ENDPOINT = "https://auth.zepto.co.in/token"
ZEPTO_MCP_RESOURCE = "https://mcp.zepto.co.in"
ZEPTO_SCOPES = "tools:read tools:write"
CALLBACK_PATH = "/api/v1/integrations/zepto/callback"
OAUTH_STATE_TTL = timedelta(minutes=10)
TOKEN_REFRESH_SKEW = timedelta(seconds=60)


class ZeptoOAuthConfigurationError(RuntimeError):
    pass


class ZeptoOAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class ZeptoOAuthToken:
    access_token: str
    refresh_token: str
    expires_at: datetime
    scope: str

    def is_expiring(self, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        return self.expires_at <= current + TOKEN_REFRESH_SKEW

    def to_encrypted_payload(self) -> str:
        return json.dumps(
            {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expires_at": self.expires_at.isoformat(),
                "scope": self.scope,
            },
            separators=(",", ":"),
        )

    @classmethod
    def from_encrypted_payload(cls, raw: str) -> "ZeptoOAuthToken":
        try:
            value = json.loads(raw)
            expires_at = datetime.fromisoformat(str(value["expires_at"]))
            if expires_at.tzinfo is None:
                raise ValueError("expiry requires timezone")
            access_token = str(value["access_token"])
            refresh_token = str(value["refresh_token"])
            scope = str(value.get("scope") or ZEPTO_SCOPES)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ZeptoOAuthError("stored Zepto connection is invalid") from exc
        if not access_token or not refresh_token:
            raise ZeptoOAuthError("stored Zepto connection is invalid")
        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at.astimezone(timezone.utc),
            scope=scope,
        )


def oauth_is_configured() -> bool:
    try:
        _client_id()
        callback_url()
    except ZeptoOAuthConfigurationError:
        return False
    return True


def _client_id() -> str:
    value = os.getenv("ZEPTO_OAUTH_CLIENT_ID", "").strip()
    if not value:
        raise ZeptoOAuthConfigurationError("ZEPTO_OAUTH_CLIENT_ID is not configured")
    return value


def callback_url() -> str:
    base = os.getenv("RESTOCK_PUBLIC_API_URL", "").strip().rstrip("/")
    parsed = urlsplit(base)
    development = os.getenv("RESTOCK_ENV", "development") != "production"
    if not parsed.scheme or not parsed.netloc:
        raise ZeptoOAuthConfigurationError("RESTOCK_PUBLIC_API_URL is invalid")
    if parsed.scheme != "https" and not development:
        raise ZeptoOAuthConfigurationError("RESTOCK_PUBLIC_API_URL must use HTTPS")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ZeptoOAuthConfigurationError("RESTOCK_PUBLIC_API_URL is invalid")
    return f"{base}{CALLBACK_PATH}"


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def begin_authorization() -> tuple[str, str, str, datetime]:
    """Return opaque state, PKCE verifier, authorization URL, and expiry."""

    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    parameters = {
        "response_type": "code",
        "client_id": _client_id(),
        "redirect_uri": callback_url(),
        "scope": ZEPTO_SCOPES,
        "state": state,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
        "resource": ZEPTO_MCP_RESOURCE,
        "prompt": "consent",
    }
    url = f"{ZEPTO_AUTHORIZATION_ENDPOINT}?{urlencode(parameters)}"
    return state, verifier, url, datetime.now(timezone.utc) + OAUTH_STATE_TTL


def _token_request(payload: dict[str, str]) -> ZeptoOAuthToken:
    request_data = {**payload, "client_id": _client_id()}
    client_secret = os.getenv("ZEPTO_OAUTH_CLIENT_SECRET", "").strip()
    if client_secret:
        request_data["client_secret"] = client_secret
    try:
        response = httpx.post(
            ZEPTO_TOKEN_ENDPOINT,
            data=request_data,
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ZeptoOAuthError("Zepto authorization could not be completed") from exc
    try:
        access_token = str(body["access_token"])
        refresh_token = str(body["refresh_token"])
        expires_in = int(body.get("expires_in", 3600))
        scope = str(body.get("scope") or ZEPTO_SCOPES)
    except (KeyError, TypeError, ValueError) as exc:
        raise ZeptoOAuthError("Zepto returned an invalid authorization response") from exc
    if not access_token or not refresh_token or expires_in <= 0:
        raise ZeptoOAuthError("Zepto returned an invalid authorization response")
    return ZeptoOAuthToken(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=min(expires_in, 86_400)),
        scope=scope,
    )


def exchange_authorization_code(*, code: str, verifier: str) -> ZeptoOAuthToken:
    if not code or not verifier:
        raise ZeptoOAuthError("Zepto authorization response is incomplete")
    return _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": callback_url(),
        }
    )


def refresh_access_token(token: ZeptoOAuthToken) -> ZeptoOAuthToken:
    refreshed = _token_request(
        {
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
        }
    )
    return refreshed
