"""WhatsApp Cloud API template sender and signed webhook helpers."""

import hashlib
import hmac
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any


GRAPH_API_VERSION = os.getenv("WHATSAPP_GRAPH_API_VERSION", "v24.0")


def template_payload(*, recipient: str, template_name: str, run_id: str) -> dict[str, Any]:
    return {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "en"},
            "components": [
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": str(index),
                    "parameters": [{"type": "payload", "payload": f"{action}:{run_id}"}],
                }
                for index, action in enumerate(("approve", "adjust", "skip"))
            ],
        },
    }


def send_template(*, recipient: str, template_name: str, run_id: str, opted_in: bool) -> str:
    if not opted_in:
        raise PermissionError("WhatsApp proactive messaging requires recorded opt-in")
    token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    if not token or not phone_number_id:
        raise RuntimeError("WhatsApp Cloud API credentials are not configured")
    request = Request(
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages",
        data=json.dumps(template_payload(recipient=recipient, template_name=template_name, run_id=run_id)).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"WhatsApp API returned HTTP {exc.code}") from exc
    except (TimeoutError, URLError) as exc:
        raise RuntimeError("WhatsApp API could not be reached") from exc
    messages = result.get("messages") or []
    if not messages or not messages[0].get("id"):
        raise RuntimeError("WhatsApp API response did not include a message id")
    return str(messages[0]["id"])


def verify_signature(body: bytes, signature_header: str | None) -> bool:
    secret = os.getenv("WHATSAPP_APP_SECRET", "")
    if not secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header.removeprefix("sha256="), expected)


def extract_actions(payload: dict[str, Any]) -> list[dict[str, str]]:
    actions = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for message in change.get("value", {}).get("messages", []):
                button = message.get("button") or {}
                value = button.get("payload") or button.get("text")
                if not value or ":" not in value:
                    continue
                action, run_id = value.split(":", 1)
                if action in {"approve", "adjust", "skip"}:
                    actions.append({"action": action, "run_id": run_id, "from": str(message.get("from", ""))})
    return actions
