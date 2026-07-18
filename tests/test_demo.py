from datetime import date

from demo import dry_run
from demo.seed_reset import load_seed_items
from payments import prava_client


def test_seed_data_contains_four_home_and_one_teams_item() -> None:
    today = date(2026, 7, 14)
    items = load_seed_items(today)
    assert len(items) == 5
    assert sum(item.track.value == "home" for item in items) == 4
    assert sum(item.track.value == "teams" for item in items) == 1
    teams_item = next(item for item in items if item.track.value == "teams")
    assert (teams_item.renewal_date - today).days == 2
    assert teams_item.alternate_plan_amount < teams_item.current_plan_amount


def test_dry_run_completes_all_seeded_items(capsys, tmp_path, monkeypatch) -> None:
    intents: dict[str, dict] = {}

    def create_intent(merchant, amount, item_description, constraints):
        intent_ref = f"offline_demo_intent_{len(intents) + 1}"
        intents[intent_ref] = {"merchant": merchant, "amount": str(amount)}
        return intent_ref

    def await_mandate(intent_ref):
        intent = intents[intent_ref]
        return {
            "status": "approved",
            "mandate_id": f"offline_demo_mandate_{intent_ref}",
            "credential_reference": f"offline_demo_credential_{intent_ref}",
            "scope": {
                "merchant": intent["merchant"],
                "max_amount": intent["amount"],
            },
            "approved_at": "2026-07-14T09:00:00+00:00",
        }

    monkeypatch.setattr(prava_client, "create_intent", create_intent)
    monkeypatch.setattr(prava_client, "await_mandate", await_mandate)
    monkeypatch.setattr(dry_run, "AUDIT_LOG_PATH", tmp_path / "audit.json")
    assert dry_run.main() == 0
    output = capsys.readouterr().out
    assert "[1/5]" in output
    assert "[5/5]" in output
    assert "Summary: 5/5 items completed against fakes." in output
