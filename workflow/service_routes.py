"""Least-privilege trigger endpoint used by the leased scheduler worker."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status

from common.service_auth import ServiceAuthError, verify_bearer
from payments.models import User
from storage import Database, RestockRepository
from triggers import consumption_model, renewal_model
from workflow import WorkflowService


router = APIRouter(prefix="/api/v1/service/worker", tags=["worker-service"])
REPOSITORY: RestockRepository | None = None


def get_repository() -> RestockRepository:
    global REPOSITORY
    if REPOSITORY is None:
        REPOSITORY = RestockRepository(Database())
    return REPOSITORY


def require_worker_service(authorization: str | None) -> None:
    try:
        verify_bearer(authorization, os.getenv("RESTOCK_WORKER_SERVICE_TOKEN", ""))
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="worker service authentication is not configured",
        ) from exc
    except ServiceAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/items/{item_id}/trigger")
def trigger_item(
    item_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_worker_service(authorization)
    repository = get_repository()
    try:
        item = repository.get_item(item_id)
        if item.status.value != "active":
            raise HTTPException(status_code=409, detail="tracked item is not active")
        should_fire = (
            consumption_model.should_fire(item)
            if item.trigger_type.value == "predicted"
            else renewal_model.should_fire(item)
        )
        if not should_fire:
            raise HTTPException(status_code=409, detail="tracked item is not due")
        user_data = repository.get_user(str(item.user_id))
        if user_data is None:
            raise KeyError("unknown user")
        run = WorkflowService(repository).begin(User.model_validate(user_data), item)
        return {"status": "created", "run_id": run["run_id"], "item_id": item_id}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="tracked item not found") from exc
    except ValueError as exc:
        if "active workflow" in str(exc):
            return {"status": "duplicate_suppressed", "item_id": item_id}
        raise HTTPException(status_code=409, detail=str(exc)) from exc
