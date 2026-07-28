"""Regression coverage for safe migration of pre-outbox transactions."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "storage" / "migrations" / "versions" / "20260722_07_completion_effects.py"


def test_legacy_completion_effects_are_never_replayed() -> None:
    """A missing historical audit is ambiguous, so the migration must not replay it."""
    source = MIGRATION.read_text(encoding="utf-8")
    assert "SELECT run_id, 'completed', 0, completed_at, completed_at FROM transactions" in source
    assert "SELECT run_id, 'pending', 0, completed_at, completed_at FROM transactions" not in source
