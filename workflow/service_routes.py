"""Least-privilege trigger endpoint used by the leased scheduler worker."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, status

from common.service_auth import ServiceAuthError, verify_bearer
from merchant.quote_provider import HomeQuoteError, build_home_quote_provider
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
        latest = repository.latest_workflow_for_item(item_id)
        if latest and latest.get("error_code") == "HOME_QUOTE_FAILED":
            updated_at = latest["updated_at"]
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            cooldown_seconds = max(
                30, int(os.getenv("RESTOCK_QUOTE_FAILURE_COOLDOWN_SECONDS", "300"))
            )
            if updated_at + timedelta(seconds=cooldown_seconds) > datetime.now(timezone.utc):
                return {
                    "status": "quote_cooldown",
                    "item_id": item_id,
                    "retry_after_seconds": cooldown_seconds,
                }
        user_data = repository.get_user(str(item.user_id))
        if user_data is None:
            raise KeyError("unknown user")
        quote_provider = None
        if item.trigger_type.value == "predicted":
            quote_provider = build_home_quote_provider(repository)
        run = WorkflowService(
            repository,
            quote_provider=quote_provider,
        ).begin(User.model_validate(user_data), item)
        return {"status": "created", "run_id": run["run_id"], "item_id": item_id}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="tracked item not found") from exc
    except ValueError as exc:
        if "active workflow" in str(exc):
            return {"status": "duplicate_suppressed", "item_id": item_id}
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HomeQuoteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/scan")
def scan_due_items(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Run one leased trigger scan without requiring a paid worker process.

    A scheduled HTTPS caller can invoke this endpoint. The database lease keeps
    concurrent or delayed scheduler invocations from producing duplicate work,
    while the per-item route still rechecks every trigger and active-workflow
    constraint before creating a Prava intent.
    """

    require_worker_service(authorization)
    repository = get_repository()
    owner_id = f"http-scan-{uuid4().hex}"
    lease_seconds = max(30, int(os.getenv("RESTOCK_SCAN_LEASE_SECONDS", "120")))
    acquired = repository.acquire_lease(
        lease_name="trigger-scan",
        owner_id=owner_id,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=lease_seconds),
    )
    if not acquired:
        return {
            "status": "lease_busy",
            "due": 0,
            "created": 0,
            "duplicate_suppressed": 0,
            "failed": 0,
        }

    results: list[dict[str, Any]] = []
    try:
        WorkflowService(repository).repair_pending_completion_effects()
        for _, item in repository.list_schedulable_items():
            should_fire = (
                consumption_model.should_fire(item)
                if item.trigger_type.value == "predicted"
                else renewal_model.should_fire(item)
            )
            if not should_fire:
                continue
            try:
                results.append(trigger_item(str(item.item_id), authorization))
            except HTTPException as exc:
                results.append(
                    {
                        "status": "failed",
                        "item_id": str(item.item_id),
                        "status_code": exc.status_code,
                    }
                )
    finally:
        repository.release_lease(lease_name="trigger-scan", owner_id=owner_id)

    return {
        "status": "completed",
        "due": len(results),
        "created": sum(result.get("status") == "created" for result in results),
        "duplicate_suppressed": sum(
            result.get("status") == "duplicate_suppressed" for result in results
        ),
        "failed": sum(result.get("status") == "failed" for result in results),
        "results": results,
    }
