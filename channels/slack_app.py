"""Single-workspace Slack adapter using Bolt and Socket Mode."""

import os
from typing import Any
from urllib.request import Request, urlopen
import json

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler


def notification_blocks(notification: dict[str, Any]) -> list[dict[str, Any]]:
    actions = []
    labels = {
        "approve": "Approve",
        "adjust": "Adjust",
        "skip": "Skip",
        "renew_as_is": "Renew as-is",
        "switch_plan": "Switch plan",
    }
    for action in notification.get("actions", []):
        actions.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": labels.get(action, action)},
                "action_id": f"restock_{action}",
                "value": str(notification["run_id"]),
                "style": "primary" if action in {"approve", "renew_as_is"} else None,
            }
        )
    for action in actions:
        if action.get("style") is None:
            action.pop("style")
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": notification["message"]}},
        {"type": "actions", "elements": actions},
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "Restock Teams · sandbox/disclosure status visible in the dashboard"}],
        },
    ]


def build_app() -> App:
    token = os.getenv("SLACK_BOT_TOKEN", "")
    signing_secret = os.getenv("SLACK_SIGNING_SECRET", "")
    if not token or not signing_secret:
        raise RuntimeError("SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET are required")
    app = App(token=token, signing_secret=signing_secret)

    def register(action: str) -> None:
        @app.action(f"restock_{action}")
        def handle(ack, body, logger):
            ack()
            run_id = body["actions"][0]["value"]
            api_url = os.getenv("RESTOCK_PUBLIC_API_URL", "http://localhost:8000").rstrip("/")
            api_token = os.getenv("RESTOCK_API_TOKEN", "")
            request = Request(
                f"{api_url}/api/v1/workflows/{run_id}/actions",
                data=json.dumps({"action": action}).encode("utf-8"),
                headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=10) as response:
                    response.read()
            except Exception:
                logger.exception("Restock Slack action failed after acknowledgement")

    for action_name in ("approve", "skip", "renew_as_is", "switch_plan"):
        register(action_name)
    return app


def send_notification(notification: dict[str, Any], channel_id: str) -> str:
    app = build_app()
    result = app.client.chat_postMessage(
        channel=channel_id,
        text=notification["message"],
        blocks=notification_blocks(notification),
    )
    return str(result["ts"])


def main() -> int:
    app = build_app()
    app_token = os.getenv("SLACK_APP_TOKEN", "")
    if not app_token:
        raise RuntimeError("SLACK_APP_TOKEN is required for Socket Mode")
    SocketModeHandler(app, app_token).start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
