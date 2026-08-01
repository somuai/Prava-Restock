"""Verify Google Identity Services ID tokens against Restock's web client.

The browser sends only the short-lived Google ID token.  Restock verifies its
signature, issuer, audience, and expiry through Google's supported library
before treating the stable ``sub`` claim as an authentication identity.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests
from google.oauth2 import id_token


class GoogleIdentityConfigurationError(RuntimeError):
    """Google sign-in is enabled without a usable OAuth web client ID."""


class GoogleIdentityError(ValueError):
    """The presented token is invalid or lacks required identity claims."""


@dataclass(frozen=True)
class GoogleIdentityClaims:
    subject: str
    email: str
    display_name: str


def verify_google_identity(credential: str) -> GoogleIdentityClaims:
    """Verify and normalize a GIS credential without trusting browser claims."""

    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        raise GoogleIdentityConfigurationError("Google sign-in is not configured")
    if not credential or len(credential) > 16_384:
        raise GoogleIdentityError("invalid Google credential")
    try:
        claims: dict[str, Any] = id_token.verify_oauth2_token(
            credential,
            requests.Request(),
            client_id,
        )
    except (GoogleAuthError, ValueError, OSError) as exc:
        raise GoogleIdentityError("invalid Google credential") from exc

    subject = str(claims.get("sub", "")).strip()
    email = str(claims.get("email", "")).strip().lower()
    display_name = str(claims.get("name", "")).strip()
    if (
        not subject
        or len(subject) > 255
        or not email
        or len(email) > 320
        or claims.get("email_verified") is not True
    ):
        raise GoogleIdentityError("Google credential lacks required verified claims")
    # ``name`` is standard profile metadata but is not a reliable account key
    # and can be absent.  Keep a usable display label without rejecting an
    # otherwise valid, verified Google identity.
    if not display_name:
        display_name = email.split("@", 1)[0]
    if not display_name or len(display_name) > 200:
        raise GoogleIdentityError("Google credential lacks required verified claims")
    return GoogleIdentityClaims(
        subject=subject,
        email=email,
        display_name=display_name,
    )
