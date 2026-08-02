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
        )
    finally:
        api.app.dependency_overrides.pop(api.get_repository, None)

    assert response.status_code == 200
    assert response.json() == {
        "run_id": "sandbox-review-run",
        "state": "passkey_pending",
        "approval_url": "https://sandbox.pay.prava.space/session/reviewer-demo",
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
        )
    finally:
        api.app.dependency_overrides.pop(api.get_repository, None)

    assert response.status_code == 503
    assert response.json() == {"detail": "Prava sandbox approval is unavailable"}
