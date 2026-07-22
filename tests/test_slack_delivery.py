from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from channels import slack_routes
from channels.slack_dispatcher import dispatch_once
from demo.seed_reset import demo_user, load_seed_items
from storage import Database, RestockRepository
from ui.api import app


ROOT = Path(__file__).resolve().parents[1]
SERVICE_TOKEN = "slack-service-token-with-more-than-32-characters"


def create_notification(repository: RestockRepository, *, teams: bool = True):
    user = demo_user()
    item = next(
        item for item in load_seed_items()
        if (item.track.value == "teams") is teams
    )
    repository.upsert_user(user)
    repository.upsert_item(item)
    run = repository.create_workflow(
        user_id=str(user.user_id),
        item_id=str(item.item_id),
        trigger_reason="known_renewal_date" if teams else "predicted_depletion",
        proposed_amount=item.current_plan_amount if teams else item.last_purchase_amount,
        currency=item.currency,
        merchant=str(item.preferred_merchant.value),
        proposed_action="renew_as_is" if teams else None,
        quote=None,
        modes={"slack": "real"},
        idempotency_key=f"slack-test-{uuid4().hex}",
    )
    notification = repository.create_notification(
        run_id=run["run_id"],
        user_id=str(user.user_id),
        message=f"{item.name} needs a decision.",
        actions=["renew_as_is", "switch_plan", "skip"] if teams else ["approve", "adjust", "skip"],
    )
    repository.transition(run["run_id"], expected={"triggered"}, state="notified")
    return run, notification


class RecordingSlackClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def chat_postMessage(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise TimeoutError("ambiguous network result")
        return {"ts": "123.456"}


def test_teams_notification_creates_one_outbox_row_but_home_does_not(tmp_path) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'outbox.db'}"))
    repository.create_schema()
    _, teams_notification = create_notification(repository, teams=True)
    _, home_notification = create_notification(repository, teams=False)

    delivery = repository.slack_delivery_for_notification(teams_notification["notification_id"])
    assert delivery is not None
    assert delivery["status"] == "pending"
    assert repository.slack_delivery_for_notification(home_notification["notification_id"]) is None


def test_dispatch_is_durable_and_cannot_send_same_notification_twice(tmp_path) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'outbox.db'}"))
    repository.create_schema()
    _, notification = create_notification(repository)
    client = RecordingSlackClient()

    assert dispatch_once(repository, client, channel_id="C123", owner_id="dispatcher-1") is True
    assert dispatch_once(repository, client, channel_id="C123", owner_id="dispatcher-2") is False

    assert len(client.calls) == 1
    delivery = repository.slack_delivery_for_notification(notification["notification_id"])
    assert delivery["status"] == "sent"
    assert delivery["attempts"] == 1
    assert client.calls[0]["client_msg_id"] == delivery["delivery_id"]


def test_ambiguous_slack_failure_is_terminal_and_not_blind_retried(tmp_path) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'outbox.db'}"))
    repository.create_schema()
    _, notification = create_notification(repository)
    client = RecordingSlackClient(fail=True)

    assert dispatch_once(repository, client, channel_id="C123", owner_id="dispatcher-1") is True
    assert dispatch_once(repository, client, channel_id="C123", owner_id="dispatcher-2") is False

    delivery = repository.slack_delivery_for_notification(notification["notification_id"])
    assert delivery["status"] == "failed_ambiguous"
    assert delivery["last_error"] == "TimeoutError"
    assert len(client.calls) == 1


def test_slack_service_route_uses_dedicated_token_and_only_action_scope(
    tmp_path, monkeypatch
) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'service.db'}"))
    repository.create_schema()
    run, _ = create_notification(repository)
    monkeypatch.setattr(slack_routes, "REPOSITORY", repository)
    monkeypatch.setenv("RESTOCK_SLACK_SERVICE_TOKEN", SERVICE_TOKEN)
    client = TestClient(app)
    path = f"/api/v1/service/slack/workflows/{run['run_id']}/actions"

    assert client.post(path, json={"action": "skip"}).status_code == 401
    response = client.post(
        path,
        headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
        json={"action": "skip"},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "skipped"
    assert client.get(
        "/api/v1/workflows",
        headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
    ).status_code != 200


def test_slack_service_route_fails_closed_without_secure_token(monkeypatch) -> None:
    monkeypatch.delenv("RESTOCK_SLACK_SERVICE_TOKEN", raising=False)

    response = TestClient(app).post(
        "/api/v1/service/slack/workflows/unknown/actions",
        headers={"Authorization": "Bearer any-value"},
        json={"action": "skip"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Slack service authentication is not configured"}


def test_slack_outbox_migration_reaches_new_head(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)

    command.upgrade(config, "head")

    database = Database(database_url)
    table_names = inspect(database.engine).get_table_names()
    assert "slack_deliveries" in table_names
    assert "auth_login_throttles" in table_names
    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260722_06"
