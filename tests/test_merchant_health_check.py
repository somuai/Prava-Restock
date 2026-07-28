from io import BytesIO
from urllib.error import HTTPError, URLError

from merchant import health_check


class FakeResponse:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_reachable_merchant_is_available(monkeypatch) -> None:
    monkeypatch.setattr(health_check, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    assert health_check.check_merchant_availability("https://merchant.example") is True


def test_client_error_still_proves_merchant_is_reachable(monkeypatch) -> None:
    def client_error(*_args, **_kwargs):
        raise HTTPError(
            "https://merchant.example",
            404,
            "not found",
            {},
            BytesIO(),
        )

    monkeypatch.setattr(health_check, "urlopen", client_error)

    assert health_check.check_merchant_availability("https://merchant.example") is True


def test_server_error_marks_merchant_unavailable(monkeypatch) -> None:
    def server_error(*_args, **_kwargs):
        raise HTTPError(
            "https://merchant.example",
            503,
            "unavailable",
            {},
            BytesIO(),
        )

    monkeypatch.setattr(health_check, "urlopen", server_error)

    assert health_check.check_merchant_availability("https://merchant.example") is False


def test_transport_error_marks_merchant_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        health_check,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")),
    )

    assert health_check.check_merchant_availability("https://merchant.example") is False


def test_timeout_marks_merchant_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        health_check,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("slow")),
    )

    assert health_check.check_merchant_availability("https://merchant.example") is False
