"""Run every seeded Restock item through the fully offline stub pipeline."""

from datetime import datetime, timezone
from uuid import UUID

from agent.orchestrator import OrchestratorContext, RestockOrchestrator
from demo.seed_reset import AUDIT_LOG_PATH, reset_demo_state
from payments.models import User


def demo_user() -> User:
    return User(
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        display_name="Restock Demo User",
        prava_account_ref="stub_prava_demo_account",
        monthly_cap="20000.00",
        per_item_cap="3000.00",
        per_transaction_cap="3000.00",
        created_at=datetime.now(timezone.utc),
    )


def main() -> int:
    items = reset_demo_state()
    context = OrchestratorContext(
        user=demo_user(), items=items, audit_log_path=AUDIT_LOG_PATH
    )
    orchestrator = RestockOrchestrator(context)

    print("Restock dry run — OFFLINE STUBS ONLY")
    print("=" * 42)
    completed = 0
    for index, item in enumerate(items, start=1):
        print(
            f"\n[{index}/{len(items)}] {item.name} "
            f"({item.track.value}, {item.trigger_type.value})"
        )
        trace = orchestrator.run_cycle(item)
        for step_number, step in enumerate(trace["steps"], start=1):
            print(f"  {step_number}. {step.replace('_', ' ')}")
        print(f"  result: {trace['status']}")
        if trace["status"] == "completed":
            completed += 1
            print(f"  checkout: {trace['merchant']} · {trace['amount']}")

    print("\n" + "=" * 42)
    print(f"Summary: {completed}/{len(items)} items completed against fakes.")
    print(f"Audit log: {AUDIT_LOG_PATH}")
    return 0 if completed == len(items) else 1


if __name__ == "__main__":
    raise SystemExit(main())
