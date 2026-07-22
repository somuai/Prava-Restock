"""Scrypt password hashing for the production solo-owner login."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets


SCRYPT_N = 1 << 14
SCRYPT_R = 8
SCRYPT_P = 1
DKLEN = 32
FORMAT_PREFIX = "scrypt"


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if not password:
        raise ValueError("password must not be empty")
    effective_salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=effective_salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=DKLEN,
    )
    return "$".join(
        (
            FORMAT_PREFIX,
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            _b64(effective_salt),
            _b64(digest),
        )
    )


def is_supported_hash(encoded_hash: str) -> bool:
    try:
        prefix, raw_n, raw_r, raw_p, raw_salt, raw_digest = encoded_hash.split("$")
        salt, digest = _unb64(raw_salt), _unb64(raw_digest)
        return (
            prefix == FORMAT_PREFIX
            and int(raw_n) == SCRYPT_N
            and int(raw_r) == SCRYPT_R
            and int(raw_p) == SCRYPT_P
            and len(salt) >= 16
            and len(digest) == DKLEN
        )
    except (ValueError, TypeError):
        return False


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify a configured hash with a constant-time digest comparison."""
    try:
        prefix, raw_n, raw_r, raw_p, raw_salt, raw_digest = encoded_hash.split("$")
        n, r, p = int(raw_n), int(raw_r), int(raw_p)
        salt, expected = _unb64(raw_salt), _unb64(raw_digest)
        if (
            prefix != FORMAT_PREFIX
            or n != SCRYPT_N
            or r != SCRYPT_R
            or p != SCRYPT_P
            or len(salt) < 16
            or len(expected) != DKLEN
        ):
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)
