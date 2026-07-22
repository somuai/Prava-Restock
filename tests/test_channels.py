import hashlib
import hmac
import json

import pytest

from channels import slack_app, whatsapp
from ui.api import app
from fastapi.testclient import TestClient


def test_slack_blocks_expose_explicit_teams_actions() -> None:
    blocks = slack_app.notification_blocks(
        {
            "run_id": "run-1",
            "message": "TeamTool renews tomorrow.",
            "actions": ["renew_as_is", "switch_plan", "skip"],
        }
    )
    buttons = blocks[1]["elements"]
    assert [button["action_id"] for button in buttons] == [
        "restock_renew_as_is",
        "restock_switch_plan",
        "restock_skip",
    ]
    assert all(button["value"] == "run-1" for button in buttons)


def test_slack_resolved_blocks_remove_buttons_and_show_terminal_state() -> None:
    blocks = slack_app.resolved_blocks("TeamTool renews tomorrow.", "skip", "skipped")

    assert [block["type"] for block in blocks] == ["section", "context"]
    assert "Recorded: *Skip*" in blocks[1]["elements"][0]["text"]
    assert "`skipped`" in blocks[1]["elements"][0]["text"]
    assert all(block["type"] != "actions" for block in blocks)


def test_whatsapp_template_contains_three_quick_reply_buttons() -> None:
    payload = whatsapp.template_payload(
        recipient="910000000000",
        template_name="restock_reorder_approval",
        run_id="run-1",
    )
    buttons = payload["template"]["components"]
    assert [button["parameters"][0]["payload"] for button in buttons] == [
        "approve:run-1",
        "adjust:run-1",
        "skip:run-1",
    ]


def test_whatsapp_proactive_send_requires_opt_in() -> None:
    with pytest.raises(PermissionError, match="opt-in"):
        whatsapp.send_template(
            recipient="910000000000",
            template_name="restock_reorder_approval",
            run_id="run-1",
            opted_in=False,
        )


def test_whatsapp_webhook_rejects_bad_signature(monkeypatch) -> None:
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "test-secret")
    payload = json.dumps({"entry": []}).encode("utf-8")
    signature = hmac.new(b"different", payload, hashlib.sha256).hexdigest()
    response = TestClient(app).post(
        "/webhooks/whatsapp",
        content=payload,
        headers={"X-Hub-Signature-256": f"sha256={signature}"},
    )
    assert response.status_code == 401


def test_whatsapp_webhook_verification(monkeypatch) -> None:
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "verify-me")
    response = TestClient(app).get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-me",
            "hub.challenge": "challenge-value",
        },
    )
    assert response.status_code == 200
    assert response.json() == "challenge-value"
