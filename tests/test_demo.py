from datetime import date

from demo import dry_run
from demo.seed_reset import load_seed_items


def test_seed_data_contains_four_home_and_one_teams_item() -> None:
    today = date(2026, 7, 14)
    items = load_seed_items(today)
    assert len(items) == 5
    assert sum(item.track.value == "home" for item in items) == 4
    assert sum(item.track.value == "teams" for item in items) == 1
    teams_item = next(item for item in items if item.track.value == "teams")
    assert (teams_item.renewal_date - today).days == 2
    assert teams_item.alternate_plan_amount < teams_item.current_plan_amount


def test_dry_run_completes_all_seeded_items(capsys) -> None:
    assert dry_run.main() == 0
    output = capsys.readouterr().out
    assert "[1/5]" in output
    assert "[5/5]" in output
    assert output.count("outcome: fired —") == 5
    assert "run out" in output
    assert "renews in" in output
    assert "Summary: 5/5 items completed." in output
