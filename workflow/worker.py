"""Single-purpose scheduler process with a database lease."""

from datetime import datetime, timedelta, timezone
import os
import time
from uuid import uuid4

from demo.seed_reset import demo_user, load_seed_items
from storage import Database, RestockRepository
from triggers import consumption_model, renewal_model
from workflow import WorkflowService


def run_tick(service: WorkflowService) -> int:
    user = demo_user()
    created = 0
    for item in load_seed_items():
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


def main() -> int:
    database = Database()
    repository = RestockRepository(database)
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
            run_tick(WorkflowService(repository))
        if one_shot:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
