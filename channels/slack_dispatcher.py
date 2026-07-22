"""Durable fail-closed Slack outbox dispatcher."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any
from uuid import uuid4

from channels.slack_app import notification_blocks
from storage import Database, RestockRepository


LOGGER = logging.getLogger("restock.slack.dispatcher")


def dispatch_once(
    repository: RestockRepository,
    client: Any,
    *,
    channel_id: str,
    owner_id: str,
) -> bool:
    delivery = repository.claim_slack_delivery(owner_id=owner_id)
    if delivery is None:
        return False
    try:
        notification = delivery["notification"]
        result = client.chat_postMessage(
            channel=channel_id,
            text=notification["message"],
            blocks=notification_blocks(notification),
            client_msg_id=delivery["delivery_id"],
        )
        repository.complete_slack_delivery(
            delivery_id=delivery["delivery_id"],
            owner_id=owner_id,
            slack_message_ts=str(result["ts"]),
        )
    except Exception as exc:
        # A timeout may occur after Slack accepted a message. Never blind-retry
        # that ambiguous result; an operator may reconcile it using delivery_id.
        repository.fail_slack_delivery(
            delivery_id=delivery["delivery_id"],
            owner_id=owner_id,
            error_code=type(exc).__name__,
        )
        LOGGER.exception("Slack delivery entered failed_ambiguous state")
    return True


def run_dispatch_loop(client: Any, stop: threading.Event) -> None:
    channel_id = os.getenv("SLACK_CHANNEL_ID", "")
    if not channel_id:
        raise RuntimeError("SLACK_CHANNEL_ID is required for Slack dispatch")
    interval = max(1, int(os.getenv("SLACK_DISPATCH_INTERVAL_SECONDS", "5")))
    repository = RestockRepository(Database())
    owner_id = f"slack-{uuid4().hex}"
    while not stop.is_set():
        while dispatch_once(
            repository,
            client,
            channel_id=channel_id,
            owner_id=owner_id,
        ):
            if stop.is_set():
                return
        stop.wait(interval)
