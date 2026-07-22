"""Least-privilege API surface used only by the Slack callback service."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from common.service_auth import ServiceAuthError, verify_bearer
from storage import Database, RestockRepository
from workflow import WorkflowService


router = APIRouter(prefix="/api/v1/service/slack", tags=["slack-service"])
REPOSITORY: RestockRepository | None = None


class SlackWorkflowAction(BaseModel):
    action: str


def get_repository() -> RestockRepository:
    global REPOSITORY
    if REPOSITORY is None:
        REPOSITORY = RestockRepository(Database())
    return REPOSITORY


def require_slack_service(authorization: str | None = Header(default=None)) -> None:
    try:
        verify_bearer(authorization, os.getenv("RESTOCK_SLACK_SERVICE_TOKEN", ""))
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Slack service authentication is not configured",
        ) from exc
    except ServiceAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


@router.post("/workflows/{run_id}/actions")
def slack_workflow_action(
    run_id: str,
    body: SlackWorkflowAction,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_slack_service(authorization)
    if body.action not in {"approve", "skip", "renew_as_is", "switch_plan"}:
        raise HTTPException(status_code=400, detail="unsupported Slack action")
    repository = get_repository()
    try:
        run = repository.get_workflow(run_id)
        return WorkflowService(repository).act(
            run_id,
            user_id=run["user_id"],
            action=body.action,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="workflow not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
