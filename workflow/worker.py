"""Single-purpose scheduler process with a database lease."""

from datetime import datetime, timedelta, timezone
import os
import time
from urllib.request import Request, urlopen
import json
from uuid import uuid4

from demo.seed_reset import demo_user, load_seed_items
from storage import Database, RestockRepository
from triggers import consumption_model, renewal_model
from workflow import WorkflowService


def _development_candidates():
    user = demo_user()
    return [(user, item) for item in load_seed_items()]


def run_tick(service: WorkflowService) -> int:
    """Run the deterministic local harness; production never uses this path."""

    if os.getenv("RESTOCK_ENV", "development") == "production":
        raise RuntimeError("production worker must trigger items through the API service")
    created = 0
    for user, item in _development_candidates():
        should_fire = (
            consumption_model.should_fire(item)
            if item.trigger_type.value == "predicted"
            else renewal_model.should_fire(item)
        )
        if not should_fire:
            continue
        try:
            service.begin(user, item)
        except ValueError as exc:
            if "active workflow" not in str(exc):
                raise
        else:
            created += 1
    return created


def triggered_item_ids(repository: RestockRepository) -> list[str]:
    result = []
    for _, item in repository.list_schedulable_items():
        should_fire = (
            consumption_model.should_fire(item)
            if item.trigger_type.value == "predicted"
            else renewal_model.should_fire(item)
        )
        if should_fire:
            result.append(str(item.item_id))
    return result


def request_trigger(item_id: str) -> dict:
    api_url = os.environ["RESTOCK_PUBLIC_API_URL"].rstrip("/")
    service_token = os.environ["RESTOCK_WORKER_SERVICE_TOKEN"]
    request = Request(
        f"{api_url}/api/v1/service/worker/items/{item_id}/trigger",
        data=b"{}",
        headers={
            "Authorization": f"Bearer {service_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def run_production_tick(repository: RestockRepository) -> int:
    created = 0
    for item_id in triggered_item_ids(repository):
        result = request_trigger(item_id)
        if result.get("status") == "created":
            created += 1
    return created


def main() -> int:
    database = Database()
    repository = RestockRepository(database)
    if os.getenv("RESTOCK_ENV", "development") != "production":
        repository.create_schema()
    owner = f"worker-{uuid4().hex}"
    interval = int(os.getenv("RESTOCK_SCHEDULER_INTERVAL_SECONDS", "60"))
    one_shot = os.getenv("RESTOCK_WORKER_ONCE") == "1"
    while True:
        expires = datetime.now(timezone.utc) + timedelta(seconds=max(10, interval))
        if repository.acquire_lease(
            lease_name="trigger-scan",
            owner_id=owner,
            expires_at=expires,
        ):
            if os.getenv("RESTOCK_ENV", "development") == "production":
                run_production_tick(repository)
            else:
                run_tick(WorkflowService(repository))
        if one_shot:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
