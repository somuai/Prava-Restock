"""Small, explicit encryption boundary for third-party OAuth tokens.

The key is deployment-only.  It is intentionally separate from the session
signing secret so leaking or rotating one does not expose the other role.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


ENCRYPTION_KEY_ENV = "RESTOCK_MERCHANT_TOKEN_ENCRYPTION_KEY"


class SecretEncryptionConfigurationError(RuntimeError):
    """The deployment is not configured to protect merchant tokens."""


class SecretDecryptionError(RuntimeError):
    """Stored protected data cannot be read with this deployment key."""


def _fernet() -> Fernet:
    value = os.getenv(ENCRYPTION_KEY_ENV, "").strip()
    if not value:
        raise SecretEncryptionConfigurationError(
            f"{ENCRYPTION_KEY_ENV} is not configured"
        )
    try:
        return Fernet(value.encode("ascii"))
    except (TypeError, ValueError) as exc:
        raise SecretEncryptionConfigurationError(
            f"{ENCRYPTION_KEY_ENV} is invalid"
        ) from exc


def encrypt_secret(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("secret value must be a non-empty string")
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise SecretDecryptionError("stored secret is missing")
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
        raise SecretDecryptionError("stored secret cannot be decrypted") from exc
