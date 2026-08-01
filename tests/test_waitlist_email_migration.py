from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from storage import Database


ROOT = Path(__file__).resolve().parents[1]


def test_waitlist_welcome_outbox_migration_backfills_and_downgrades(
    tmp_path, monkeypatch
) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(config, "20260801_10")

    database = Database(database_url)
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO waitlist_leads "
                "(lead_id, email_normalized, display_name, track_interest, "
                "first_use_category, preferred_channel, status, "
                "pilot_email_consent_at, research_opt_in, privacy_notice_version, "
                "landing_variant, entry_demo_track, utm_source, utm_medium, "
                "utm_campaign, referrer_host, created_at, updated_at) VALUES "
                "('lead-1', 'person@example.com', 'Person', NULL, NULL, 'email', "
                "'joined', '2026-08-01 00:00:00', 0, 'v1', NULL, NULL, NULL, "
                "NULL, NULL, NULL, '2026-08-01 00:00:00', '2026-08-01 00:00:00')"
            )
        )

    command.upgrade(config, "head")

    assert "waitlist_welcome_emails" in inspect(database.engine).get_table_names()
    with database.engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT lead_id, status, attempts, last_error, created_at "
                "FROM waitlist_welcome_emails"
            )
        ).one()
        assert row.lead_id == "lead-1"
        assert row.status == "pending"
        assert row.attempts == 0
        assert row.last_error is None
        assert row.created_at is not None
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "20260801_11"

    command.downgrade(config, "20260801_10")

    assert "waitlist_welcome_emails" not in inspect(
        database.engine
    ).get_table_names()
    with database.engine.connect() as connection:
        assert connection.execute(
            text("SELECT email_normalized FROM waitlist_leads")
        ).scalar_one() == "person@example.com"
