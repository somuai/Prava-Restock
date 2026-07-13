"""Load stable demo fixtures and reset mutable demo state."""

from datetime import date, timedelta
import json
from pathlib import Path

from payments.models import TrackedItem, TriggerType


ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "triggers" / "seed_data.json"
AUDIT_LOG_PATH = ROOT / "logs" / "audit_log.json"


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
    AUDIT_LOG_PATH.write_text("[]\n")
    return load_seed_items(today)


if __name__ == "__main__":
    items = reset_demo_state()
    print(f"Reset Restock demo state with {len(items)} seeded items.")
