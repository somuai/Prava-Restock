import pytest

from common import session_auth


SECRET = "a-production-shape-secret-that-is-long-enough"


def test_signed_session_round_trip() -> None:
    token = session_auth.mint("user-1", SECRET)
    assert session_auth.verify(token, SECRET) == "user-1"


def test_tampered_and_expired_sessions_are_rejected() -> None:
    token = session_auth.mint("user-1", SECRET)
    with pytest.raises(ValueError, match="invalid or expired"):
        session_auth.verify(token + "x", SECRET)
    expired = session_auth.mint("user-1", SECRET, ttl_seconds=-1)
    with pytest.raises(ValueError, match="invalid or expired"):
        session_auth.verify(expired, SECRET)
