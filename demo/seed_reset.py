"""Load stable demo fixtures and reset mutable demo state."""

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import UUID

from common import audit_store, notification_store
from payments.models import TrackedItem, TriggerType, User
from storage import Database, RestockRepository


def _project_root() -> Path:
    """Locate checked-in fixtures in source and installed-container runs.

    Editable local installs resolve this module inside the repository. The
    production image installs the package and also keeps the checked-in source
    under the current working directory, so package-relative fixture paths are
    not available there.
    """
    package_root = Path(__file__).resolve().parents[1]
    if (package_root / "triggers" / "seed_data.json").is_file():
        return package_root
    working_root = Path.cwd()
    if (working_root / "triggers" / "seed_data.json").is_file():
        return working_root
    return package_root


ROOT = _project_root()
SEED_PATH = ROOT / "triggers" / "seed_data.json"
AUDIT_LOG_PATH = audit_store.AUDIT_STORE_PATH


def demo_user() -> User:
    return User(
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        display_name="Restock Demo User",
        prava_account_ref="prava_demo_account",
        monthly_cap="20000.00",
        per_item_cap="3000.00",
        per_transaction_cap="3000.00",
        created_at=datetime.now(timezone.utc),
    )


def load_seed_items(today: date | None = None) -> list[TrackedItem]:
    """Load all five fixtures, keeping every trigger exactly two days away."""
    effective_today = today or date.today()
    records = json.loads(SEED_PATH.read_text())
    for record in records:
        if record["trigger_type"] == TriggerType.PREDICTED.value:
            cadence = float(record["typical_cadence_days"])
            record["last_purchased_at"] = (
                effective_today - timedelta(days=cadence - 2)
            ).isoformat()
        else:
            record["renewal_date"] = (effective_today + timedelta(days=2)).isoformat()
    return [TrackedItem.model_validate(record) for record in records]


def reset_demo_state(today: date | None = None) -> list[TrackedItem]:
    audit_store.reset(AUDIT_LOG_PATH)
    notification_store.reset()
    return load_seed_items(today)


def reset_database(today: date | None = None) -> list[TrackedItem]:
    items = reset_demo_state(today)
    database = Database()
    database.reset_schema()
    repository = RestockRepository(database)
    repository.upsert_user(demo_user())
    for item in items:
        repository.upsert_item(item)
    return items


if __name__ == "__main__":
    items = reset_database()
    print(f"Reset Restock demo database with {len(items)} seeded items.")
