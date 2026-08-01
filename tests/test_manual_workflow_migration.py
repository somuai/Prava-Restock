from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
import pytest

from storage import Database


ROOT = Path(__file__).resolve().parents[1]


def test_manual_workflow_migration_makes_payment_proposal_fields_nullable(
    tmp_path, monkeypatch
) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)

    command.upgrade(config, "20260730_09")

    database = Database(database_url)
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users "
                "(user_id, display_name, prava_account_ref, monthly_cap, "
                "per_item_cap, per_transaction_cap, created_at) "
                "VALUES ('user-1', 'Asha', 'prava-user', 5000, 1000, 1000, "
                "'2026-08-01 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO tracked_items "
                "(item_id, user_id, tenant_id, payload, updated_at) "
                "VALUES ('item-1', 'user-1', NULL, '{}', "
                "'2026-08-01 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO workflow_runs "
                "(run_id, user_id, tenant_id, item_id, state, active_item_key, "
                "trigger_reason, proposed_amount, currency, merchant, "
                "proposed_action, quote, prava_intent_ref, mandate_ref, "
                "idempotency_key, modes, error_code, version, created_at, updated_at) "
                "VALUES ('run-1', 'user-1', NULL, 'item-1', 'notified', "
                "'item-1', 'known_renewal_date', 900, 'USD', "
                "'mock_subscription_billing', 'renew_as_is', NULL, NULL, NULL, "
                "'key-1', '{}', NULL, 1, '2026-08-01 00:00:00', "
                "'2026-08-01 00:00:00')"
            )
        )

    command.upgrade(config, "head")

    columns = {
        column["name"]: column
        for column in inspect(database.engine).get_columns("workflow_runs")
    }
    assert columns["proposed_amount"]["nullable"] is True
    assert columns["merchant"]["nullable"] is True
    constraints = {
        constraint["name"]
        for constraint in inspect(database.engine).get_check_constraints(
            "workflow_runs"
        )
    }
    assert "ck_workflow_payment_proposal_shape" in constraints
    with database.engine.connect() as connection:
        preserved = connection.execute(
            text(
                "SELECT proposed_amount, merchant FROM workflow_runs "
                "WHERE run_id = 'run-1'"
            )
        ).one()
        assert str(preserved.proposed_amount) == "900"
        assert preserved.merchant == "mock_subscription_billing"
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "20260801_11"
        )

    with pytest.raises(IntegrityError):
        with database.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE workflow_runs SET proposed_amount = NULL "
                    "WHERE run_id = 'run-1'"
                )
            )

    with database.engine.begin() as connection:
        connection.execute(
                text(
                    "UPDATE workflow_runs SET proposed_action = "
                    "'flag_for_manual_renewal', proposed_amount = NULL, merchant = NULL "
                    "WHERE run_id = 'run-1'"
                )
        )

    with pytest.raises(
        RuntimeError,
        match="cannot downgrade while notification-only workflows are present",
    ):
        command.downgrade(config, "20260730_09")
