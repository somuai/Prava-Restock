"""Deterministic cross-component proof for every seeded Restock workflow."""

import json
from datetime import datetime, timezone

from demo.seed_reset import demo_user, load_seed_items
from storage import Database, RestockRepository
from workflow import WorkflowService


class DeterministicPrava:
    def __init__(self) -> None:
        self.intents: dict[str, dict] = {}
        self._INTENTS: dict[str, dict] = {}

    def create_intent(self, merchant, amount, item_description, constraints):
        reference = f"deterministic-intent-{len(self.intents) + 1}"
        self.intents[reference] = {"merchant": merchant, "amount": str(amount)}
        self._INTENTS[reference] = {"iframe_url": f"https://approval.test/{reference}"}
        return reference

    def await_mandate(self, intent_ref):
        value = self.intents[intent_ref]
        return {
            "status": "approved",
            "mandate_id": f"mandate-{intent_ref}",
            "credential_reference": f"credential-{intent_ref}",
            "scope": {"merchant": value["merchant"], "max_amount": value["amount"]},
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }


class DeterministicCheckout:
    def __init__(self) -> None:
        self.by_key: dict[str, dict] = {}

    def complete_checkout(self, credential_reference, merchant_sku_id, amount, idempotency_key):
        self.by_key.setdefault(
            idempotency_key,
            {
                "status": "completed",
                "merchant_order_id": f"order-{len(self.by_key) + 1}",
                "charged_amount": str(amount),
                "currency": "INR",
                "execution_mode": "disclosed_mock",
            },
        )
        return self.by_key[idempotency_key]


def test_all_five_seeded_items_complete_with_disclosure_and_restart(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'full.db'}"
    repository = RestockRepository(Database(database_url))
    repository.create_schema()
    prava = DeterministicPrava()
    checkout = DeterministicCheckout()
    service = WorkflowService(
        repository,
        prava=prava,
        home_checkout=checkout,
        teams_checkout=checkout,
    )
    user = demo_user()
    runs = []
    for item in load_seed_items():
        run = service.begin(user, item)
        action = "switch_plan" if run.get("proposed_action") == "switch_to_alternate" else "approve"
        service.act(run["run_id"], user_id=str(user.user_id), action=action)
        final = service.resume_after_passkey(run["run_id"])
        assert final["state"] == "completed"
        runs.append(final)

    assert len(runs) == 5
    assert len(prava.intents) == 5
    assert len(checkout.by_key) == 5
    restarted = RestockRepository(Database(database_url))
    assert len(restarted.list_workflows(str(user.user_id))) == 5
    audits = restarted.list_audit(str(user.user_id))
    assert audits
    assert all(entry["modes"] for entry in audits)
    serialized = json.dumps(audits, default=str).lower()
    for forbidden in ("dynamic_cvv", "card_number", "credential_reference", "approval_url"):
        assert forbidden not in serialized
