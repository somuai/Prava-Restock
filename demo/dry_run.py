"""Run deterministic or explicitly interactive Restock workflow demos."""

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import sys
import webbrowser

from demo.seed_reset import demo_user, load_seed_items
from payments import prava_client
from payments.models import TriggerType
from storage import Database, RestockRepository
from triggers import consumption_model, renewal_model
from workflow import WorkflowService


class OfflinePrava:
    def __init__(self) -> None:
        self.intents: dict[str, dict] = {}
        self._INTENTS: dict[str, dict] = {}

    def create_intent(self, merchant, amount, item_description, constraints):
        reference = f"offline-intent-{len(self.intents) + 1}"
        self.intents[reference] = {"merchant": merchant, "amount": str(amount)}
        self._INTENTS[reference] = {"iframe_url": f"https://offline.invalid/{reference}"}
        return reference

    def await_mandate(self, intent_ref):
        intent = self.intents[intent_ref]
        return {
            "status": "approved",
            "mandate_id": f"offline-mandate-{intent_ref}",
            "credential_reference": f"offline-credential-{intent_ref}",
            "scope": {"merchant": intent["merchant"], "max_amount": intent["amount"]},
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }


class OfflineCheckout:
    def __init__(self) -> None:
        self.results: dict[str, dict] = {}

    def complete_checkout(self, credential_reference, merchant_sku_id, amount, idempotency_key):
        self.results.setdefault(
            idempotency_key,
            {
                "status": "completed",
                "merchant_order_id": f"offline-order-{len(self.results) + 1}",
                "charged_amount": str(Decimal(str(amount))),
                "execution_mode": "disclosed_mock",
            },
        )
        return self.results[idempotency_key]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("offline", "integration"), default="offline")
    parser.add_argument("--item", help="Item name fragment for an interactive integration run")
    parser.add_argument("--all", action="store_true", help="Run every item interactively")
    return parser


def _trigger_explanation(item) -> str:
    """Return the deterministic reason the seeded item enters the workflow."""

    if item.trigger_type is TriggerType.PREDICTED:
        proposal = consumption_model.propose(item)
        return proposal["message"].rsplit(" Reorder from ", 1)[0]
    proposal = renewal_model.propose(item)
    return proposal["message"].rsplit(" Approve, adjust, or skip?", 1)[0]


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv or [])
    items = load_seed_items()
    if args.item:
        items = [item for item in items if args.item.lower() in item.name.lower()]
        if not items:
            print(f"No seeded item matched {args.item!r}.")
            return 2
    if args.mode == "integration" and not args.all and not args.item:
        items = items[:1]

    repository = RestockRepository(Database("sqlite:///:memory:"))
    repository.create_schema()
    if args.mode == "offline":
        boundary = OfflineCheckout()
        service = WorkflowService(
            repository,
            prava=OfflinePrava(),
            home_checkout=boundary,
            teams_checkout=boundary,
        )
    else:
        service = WorkflowService(repository, prava=prava_client)

    print(f"Restock dry run — {args.mode.upper()}")
    print("=" * 42)
    completed = 0
    for index, item in enumerate(items, start=1):
        print(f"\n[{index}/{len(items)}] {item.name} ({item.track.value})")
        should_fire = (
            consumption_model.should_fire(item)
            if item.trigger_type is TriggerType.PREDICTED
            else renewal_model.should_fire(item)
        )
        if not should_fire:
            print("  outcome: not fired — no trigger condition is currently met")
            continue
        print(f"  outcome: fired — {_trigger_explanation(item)}")
        run = service.begin(demo_user(), item)
        print("  1. triggered and intent created")
        print("  2. proactive notification persisted")
        action = "switch_plan" if run.get("proposed_action") == "switch_to_alternate" else "approve"
        service.act(run["run_id"], user_id=str(item.user_id), action=action)
        print(f"  3. user action: {action}")
        if args.mode == "integration":
            approval_url = service.approval_url(run["run_id"])
            print("  4. opening the short-lived Prava approval page")
            webbrowser.open(approval_url)
        final = service.resume_after_passkey(run["run_id"])
        print(f"  5. result: {final['state']}")
        if final["state"] == "completed":
            completed += 1

    print("\n" + "=" * 42)
    print(f"Summary: {completed}/{len(items)} items completed.")
    return 0 if completed == len(items) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
