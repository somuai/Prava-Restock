from __future__ import annotations

import httpx
import pytest

from scripts import register_zepto_oauth_client as registration


def test_callback_url_is_fixed_to_our_endpoint() -> None:
    assert registration.validate_callback_url("https://restock.example.test/") == (
        "https://restock.example.test/api/v1/integrations/zepto/callback"
    )
    with pytest.raises(registration.RegistrationError):
        registration.validate_callback_url("http://restock.example.test")


def test_registration_requests_pkce_public_client(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(*_args, **kwargs):
        captured.update(kwargs)
        return httpx.Response(
            201,
            json={"client_id": "zepto-public-client"},
            request=httpx.Request("POST", registration.REGISTRATION_ENDPOINT),
        )

    monkeypatch.setattr(registration.httpx, "post", fake_post)
    result = registration.register_client(
        callback_url="https://restock.example.test/api/v1/integrations/zepto/callback"
    )

    assert result == {"ZEPTO_OAUTH_CLIENT_ID": "zepto-public-client"}
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["token_endpoint_auth_method"] == "none"
    assert payload["grant_types"] == ["authorization_code", "refresh_token"]
    assert payload["redirect_uris"] == [
        "https://restock.example.test/api/v1/integrations/zepto/callback"
    ]


def test_registration_explains_provider_callback_allowlisting(monkeypatch) -> None:
    def fake_post(*_args, **_kwargs):
        return httpx.Response(
            400,
            json={"error": "invalid_redirect_uri"},
            request=httpx.Request("POST", registration.REGISTRATION_ENDPOINT),
        )

    monkeypatch.setattr(registration.httpx, "post", fake_post)
    with pytest.raises(registration.RegistrationError, match="allowlisted"):
        registration.register_client(
            callback_url="https://restock.example.test/api/v1/integrations/zepto/callback"
        )
