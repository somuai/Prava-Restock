import importlib
import json


def _email_module():
    return importlib.import_module("common.waitlist_email")


class FakeResponse:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"id":"email_123"}'


def test_resend_request_has_curated_copy_and_deterministic_idempotency(
    monkeypatch,
) -> None:
    waitlist_email = _email_module()
    requests = []

    def fake_urlopen(request, *, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setenv("RESTOCK_WAITLIST_EMAIL_MODE", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "secret-resend-key")
    monkeypatch.setenv(
        "RESTOCK_WAITLIST_FROM_EMAIL", "Soumyajit from Restock <hello@restock.example>"
    )
    monkeypatch.setattr(waitlist_email.urllib.request, "urlopen", fake_urlopen)

    assert waitlist_email.send_waitlist_welcome(
        "priya@example.com", "Priya"
    ) is True
    assert waitlist_email.send_waitlist_welcome(
        "priya@example.com", "Priya"
    ) is True

    assert len(requests) == 2
    first_request, timeout = requests[0]
    second_request, _ = requests[1]
    body = json.loads(first_request.data)
    assert first_request.full_url == "https://api.resend.com/emails"
    assert first_request.get_method() == "POST"
    assert first_request.get_header("Authorization") == "Bearer secret-resend-key"
    assert first_request.get_header("Content-type") == "application/json"
    assert timeout == 5.0
    assert body == {
        "from": "Soumyajit from Restock <hello@restock.example>",
        "to": ["priya@example.com"],
        "subject": "You’re on the Restock waitlist",
        "text": (
            "Hi Priya,\n\n"
            "Thanks for joining Restock. We’re building a calmer way to keep "
            "everyday essentials and recurring tools from becoming last-minute chores.\n\n"
            "You’ll hear from us when your place is ready. Until then, no daily "
            "drip campaign and no inbox clutter.\n\n"
            "— Soumyajit\nRestock"
        ),
    }
    assert first_request.get_header("Idempotency-key").startswith(
        "restock-waitlist-welcome-"
    )
    assert (
        first_request.get_header("Idempotency-key")
        == second_request.get_header("Idempotency-key")
    )
    assert "priya" not in first_request.get_header("Idempotency-key")


def test_disabled_mode_performs_no_network_request(monkeypatch) -> None:
    waitlist_email = _email_module()
    monkeypatch.setenv("RESTOCK_WAITLIST_EMAIL_MODE", "disabled")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESTOCK_WAITLIST_FROM_EMAIL", raising=False)
    monkeypatch.setattr(
        waitlist_email.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("network must stay disabled")
        ),
    )

    assert waitlist_email.send_waitlist_welcome("person@example.com") is False


def test_provider_failure_is_raised_without_secret_or_recipient(monkeypatch) -> None:
    waitlist_email = _email_module()
    monkeypatch.setenv("RESTOCK_WAITLIST_EMAIL_MODE", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "secret-resend-key")
    monkeypatch.setenv("RESTOCK_WAITLIST_FROM_EMAIL", "hello@restock.example")

    class ProviderFailure(Exception):
        pass

    def fail(*_args, **_kwargs):
        raise ProviderFailure("upstream body contains person@example.com")

    monkeypatch.setattr(waitlist_email.urllib.request, "urlopen", fail)

    try:
        waitlist_email.send_waitlist_welcome("person@example.com")
    except waitlist_email.WaitlistEmailError as exc:
        message = str(exc)
    else:
        raise AssertionError("provider failure must be explicit")

    assert message == "waitlist welcome email delivery failed"
    assert "person@example.com" not in message
    assert "secret-resend-key" not in message


def test_delivery_batch_settings_cap_size_and_cover_timeout_budget(
    monkeypatch,
) -> None:
    waitlist_email = _email_module()
    monkeypatch.setenv("RESTOCK_WAITLIST_EMAIL_TIMEOUT_SECONDS", "4")

    assert waitlist_email.bounded_delivery_settings(
        configured_batch=100,
        configured_lease_seconds=1,
    ) == (5, 50)
