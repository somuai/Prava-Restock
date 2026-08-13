from types import SimpleNamespace

from fastapi.testclient import TestClient

from demo.seed_reset import demo_user
from payments import prava_client
from storage import Database, RestockRepository
from ui import api


AUTH_HEADERS = {
    "Authorization": "Bearer restock-local-demo-token",
    "Origin": "http://testserver",
}


class SandboxWorkflow:
    def __init__(self) -> None:
        self.item = None
        self.quote = None
        self.actions: list[str] = []

    def begin(self, user, item, *, quote):
        self.item = item
        self.quote = quote
        return {"run_id": "sandbox-review-run", "state": "notified"}

    def act(self, run_id, *, user_id, action):
        assert run_id == "sandbox-review-run"
        assert user_id == str(demo_user().user_id)
        self.actions.append(action)
        return {"run_id": run_id, "state": "passkey_pending"}

    def approval_url(self, run_id):
        assert run_id == "sandbox-review-run"
        return "https://sandbox.pay.prava.space/session/reviewer-demo"


def test_preview_approve_creates_a_sandbox_passkey_handoff(tmp_path, monkeypatch) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'reviewer-demo.db'}"))
    repository.create_schema()
    repository.upsert_user(demo_user())
    workflow = SandboxWorkflow()
    api.app.dependency_overrides[api.get_repository] = lambda: repository
    monkeypatch.setattr(api, "WorkflowService", lambda _repository: workflow)
    monkeypatch.setattr(prava_client, "configured_mode", lambda: "sandbox")
    monkeypatch.setenv("PRAVA_API_KEY", "sandbox-key-placeholder")
    monkeypatch.setenv("PRAVA_API_URL", "https://sandbox.api.prava.space")
    monkeypatch.delenv("RESTOCK_ENV", raising=False)

    try:
        response = TestClient(api.app).post(
            "/api/v1/reviewer/sandbox-approval",
            headers=AUTH_HEADERS,
            json={"track": "home", "action": "approve"},
        )
    finally:
        api.app.dependency_overrides.pop(api.get_repository, None)

    assert response.status_code == 200
    assert response.json() == {
        "run_id": "sandbox-review-run",
        "state": "passkey_pending",
        "approval_url": "https://sandbox.pay.prava.space/session/reviewer-demo",
        "sandbox_otp": "456789",
        "track": "home",
        "action": "approve",
    }
    assert workflow.actions == ["approve"]
    assert workflow.item.user_id == demo_user().user_id
    assert workflow.item.merchant_sku_id == "zepto-arabica-coffee-500g"
    assert workflow.quote.execution_mode.value == "disclosed_mock"


def test_sandbox_passkey_handoff_is_unavailable_without_sandbox_credentials(
    tmp_path, monkeypatch
) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'no-sandbox.db'}"))
    repository.create_schema()
    repository.upsert_user(demo_user())
    api.app.dependency_overrides[api.get_repository] = lambda: repository
    monkeypatch.setattr(prava_client, "configured_mode", lambda: "unconfigured")
    monkeypatch.delenv("PRAVA_API_KEY", raising=False)
    monkeypatch.delenv("PRAVA_API_URL", raising=False)
    monkeypatch.delenv("PRAVA_SANDBOX_URL", raising=False)
    monkeypatch.delenv("RESTOCK_ENV", raising=False)

    try:
        response = TestClient(api.app).post(
            "/api/v1/reviewer/sandbox-approval",
            headers=AUTH_HEADERS,
            json={"track": "home", "action": "approve"},
        )
    finally:
        api.app.dependency_overrides.pop(api.get_repository, None)

    assert response.status_code == 503
    assert response.json() == {"detail": "Prava sandbox approval is unavailable"}


def test_teams_preview_decisions_create_real_sandbox_handoffs(tmp_path, monkeypatch) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'teams-reviewer.db'}"))
    repository.create_schema()
    repository.upsert_user(demo_user())
    api.app.dependency_overrides[api.get_repository] = lambda: repository
    monkeypatch.setattr(prava_client, "configured_mode", lambda: "sandbox")
    monkeypatch.setenv("PRAVA_API_KEY", "sandbox-key-placeholder")
    monkeypatch.setenv("PRAVA_API_URL", "https://sandbox.api.prava.space")
    monkeypatch.delenv("RESTOCK_ENV", raising=False)

    try:
        for action in ("renew_as_is", "switch_plan"):
            workflow = SandboxWorkflow()
            monkeypatch.setattr(api, "WorkflowService", lambda _repository, current=workflow: current)
            response = TestClient(api.app).post(
                "/api/v1/reviewer/sandbox-approval",
                headers=AUTH_HEADERS,
                json={"track": "teams", "action": action},
            )
            assert response.status_code == 200
            assert response.json()["sandbox_otp"] == "456789"
            assert response.json()["track"] == "teams"
            assert response.json()["action"] == action
            assert workflow.actions == [action]
            assert workflow.item.track.value == "teams"
            assert workflow.item.merchant_sku_id.startswith("reviewer-github-copilot-")
            assert workflow.quote.execution_mode.value == "disclosed_mock"
            assert str(workflow.quote.amount) == (
                "39.00" if action == "renew_as_is" else "32.00"
            )
    finally:
        api.app.dependency_overrides.pop(api.get_repository, None)


def test_payment_status_is_sanitized_before_it_reaches_the_browser(tmp_path, monkeypatch) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'payment-status.db'}"))
    repository.create_schema()
    repository.upsert_user(demo_user())
    item = api.build_starter_item("coffee", user_id=str(demo_user().user_id))
    repository.upsert_item(item)
    run = repository.create_workflow(
        user_id=str(demo_user().user_id),
        item_id=str(item.item_id),
        trigger_reason="predicted_depletion",
        proposed_amount="380.00",
        currency="INR",
        merchant="zepto",
        proposed_action=None,
        quote=None,
        idempotency_key="reviewer-status-key",
        modes={"prava": "sandbox", "home_payment": "disclosed_mock"},
    )
    repository.transition(
        run["run_id"],
        expected={"triggered"},
        state="passkey_pending",
        prava_intent_ref="prava-session-123",
    )
    api.app.dependency_overrides[api.get_repository] = lambda: repository
    monkeypatch.setattr(
        prava_client,
        "get_payment_result",
        lambda _session_id: {
            "status": "awaiting_result",
            "transactions": [{"line_items": [{"token": "must-not-leak", "dynamic_cvv": "999"}]}],
        },
    )

    try:
        response = TestClient(api.app).get(
            f"/api/v1/workflows/{run['run_id']}/payment-status",
            headers=AUTH_HEADERS,
        )
    finally:
        api.app.dependency_overrides.pop(api.get_repository, None)

    assert response.status_code == 200
    assert response.json() == {
        "run_id": run["run_id"],
        "workflow_state": "passkey_pending",
        "provider_status": "awaiting_result",
        "resumable": True,
    }
    assert "must-not-leak" not in response.text
    assert "999" not in response.text


def test_provider_expiry_becomes_a_durable_expired_workflow(tmp_path, monkeypatch) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'payment-expired.db'}"))
    repository.create_schema()
    repository.upsert_user(demo_user())
    item = api.build_starter_item("coffee", user_id=str(demo_user().user_id))
    repository.upsert_item(item)
    run = repository.create_workflow(
        user_id=str(demo_user().user_id),
        item_id=str(item.item_id),
        trigger_reason="predicted_depletion",
        proposed_amount="380.00",
        currency="INR",
        merchant="zepto",
        proposed_action=None,
        quote=None,
        idempotency_key="reviewer-expired-key",
        modes={"prava": "sandbox", "home_payment": "disclosed_mock"},
    )
    repository.transition(
        run["run_id"],
        expected={"triggered"},
        state="passkey_pending",
        prava_intent_ref="expired-session-123",
    )
    api.app.dependency_overrides[api.get_repository] = lambda: repository
    monkeypatch.setattr(
        prava_client,
        "get_payment_result",
        lambda _session_id: (_ for _ in ()).throw(
            prava_client.MandateExpiredError(message="Session expired")
        ),
    )

    try:
        response = TestClient(api.app).get(
            f"/api/v1/workflows/{run['run_id']}/payment-status",
            headers=AUTH_HEADERS,
        )
    finally:
        api.app.dependency_overrides.pop(api.get_repository, None)

    assert response.status_code == 200
    assert response.json() == {
        "run_id": run["run_id"],
        "workflow_state": "expired",
        "provider_status": "expired",
        "resumable": False,
    }
    assert repository.get_workflow(run["run_id"])["state"] == "expired"
    audit = repository.list_audit(str(demo_user().user_id))
    assert any(entry["event_type"] == "mandate_expired" for entry in audit)
