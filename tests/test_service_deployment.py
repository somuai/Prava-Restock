import json
from pathlib import Path

from scripts.validate_service_env import REQUIRED_VARIABLES, validate


ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = ROOT / "deploy" / "railway"


def load_config(service: str) -> dict:
    return json.loads((CONFIG_ROOT / f"{service}.json").read_text())


def test_railway_service_configs_use_one_replica_and_distinct_commands() -> None:
    api = load_config("api")
    worker = load_config("worker")
    slack = load_config("slack")

    for config in (api, worker, slack):
        assert config["build"] == {
            "builder": "DOCKERFILE",
            "dockerfilePath": "Dockerfile",
        }
        assert config["deploy"]["numReplicas"] == 1
        assert config["deploy"]["restartPolicyType"] == "ALWAYS"
        assert config["deploy"]["sleepApplication"] is False

    assert api["deploy"]["healthcheckPath"] == "/ready"
    assert "alembic upgrade head" in api["deploy"]["preDeployCommand"][0]
    assert "uvicorn ui.api:app" in api["deploy"]["startCommand"]
    assert "workflow.worker" in worker["deploy"]["startCommand"]
    assert "channels.slack_app" in slack["deploy"]["startCommand"]
    assert "preDeployCommand" not in worker["deploy"]
    assert "preDeployCommand" not in slack["deploy"]


def test_api_and_worker_contracts_reject_demo_or_sqlite() -> None:
    unsafe = {
        "DATABASE_URL": "sqlite:///logs/restock.db",
        "PRAVA_API_KEY": "invalid",
        "PRAVA_API_URL": "https://wrong.example",
        "RESTOCK_ENV": "development",
        "RESTOCK_DEMO_MODE": "1",
        "RESTOCK_SESSION_SECRET": "short",
    }

    assert validate("api", unsafe) == [
        "DATABASE_URL_POSTGRES_REQUIRED",
        "PRAVA_API_KEY_INVALID_PREFIX",
        "RESTOCK_DEMO_MODE_MUST_BE_DISABLED",
        "RESTOCK_ENV_MUST_BE_PRODUCTION",
        "RESTOCK_SESSION_SECRET_TOO_SHORT",
        "RESTOCK_SLACK_SERVICE_TOKEN",
        "RESTOCK_WORKER_SERVICE_TOKEN",
    ]
    assert validate("worker", unsafe) == [
        "DATABASE_URL_POSTGRES_REQUIRED",
        "RESTOCK_DEMO_MODE_MUST_BE_DISABLED",
        "RESTOCK_ENV_MUST_BE_PRODUCTION",
        "RESTOCK_PUBLIC_API_URL",
        "RESTOCK_WORKER_SERVICE_TOKEN",
    ]


def test_all_service_contracts_accept_safe_shaped_values() -> None:
    values = {
        "DATABASE_URL": "postgresql://restock:secret@postgres/restock",
        "RESTOCK_ENV": "production",
        "RESTOCK_DEMO_MODE": "0",
        "RESTOCK_SESSION_SECRET": "a-high-entropy-placeholder-at-least-32-chars",
        "PRAVA_API_KEY": "sk_test_placeholder",
        "PRAVA_API_URL": "https://sandbox.api.prava.space",
        "SLACK_BOT_TOKEN": "xoxb-placeholder",
        "SLACK_APP_TOKEN": "xapp-placeholder",
        "SLACK_CHANNEL_ID": "C0123456789",
        "SLACK_SIGNING_SECRET": "a-signing-secret-placeholder-32-chars",
        "RESTOCK_PUBLIC_API_URL": "https://restock.example",
        "RESTOCK_PUBLIC_APP_URL": "https://restock.example/app",
        "RESTOCK_SLACK_SERVICE_TOKEN": "a-dedicated-service-token-over-32-characters",
        "RESTOCK_WORKER_SERVICE_TOKEN": "a-worker-service-token-over-32-characters",
    }

    assert set(REQUIRED_VARIABLES) == {"api", "worker", "slack"}
    assert all(validate(service, values) == [] for service in REQUIRED_VARIABLES)


def test_missing_service_variables_are_reported_by_name() -> None:
    for service, required in REQUIRED_VARIABLES.items():
        expected = set(required)
        if service == "api":
            expected.add("PRAVA_API_URL_OR_SANDBOX_URL_REQUIRED")
        assert validate(service, {}) == sorted(expected)


def test_slack_contract_rejects_wrong_token_shapes_and_insecure_api_url() -> None:
    values = {
        "SLACK_BOT_TOKEN": "bot-token",
        "SLACK_APP_TOKEN": "app-token",
        "SLACK_CHANNEL_ID": "C0123456789",
        "SLACK_SIGNING_SECRET": "short",
        "RESTOCK_PUBLIC_API_URL": "http://restock.example",
        "RESTOCK_PUBLIC_APP_URL": "http://restock.example/app",
        "RESTOCK_SLACK_SERVICE_TOKEN": "short",
        "DATABASE_URL": "sqlite:///logs/restock.db",
        "RESTOCK_ENV": "development",
        "RESTOCK_DEMO_MODE": "1",
    }

    assert validate("slack", values) == [
        "DATABASE_URL_POSTGRES_REQUIRED",
        "RESTOCK_DEMO_MODE_MUST_BE_DISABLED",
        "RESTOCK_ENV_MUST_BE_PRODUCTION",
        "RESTOCK_PUBLIC_API_URL_HTTPS_REQUIRED",
        "RESTOCK_PUBLIC_APP_URL_HTTPS_REQUIRED",
        "RESTOCK_SLACK_SERVICE_TOKEN_TOO_SHORT",
        "SLACK_APP_TOKEN_INVALID_PREFIX",
        "SLACK_BOT_TOKEN_INVALID_PREFIX",
        "SLACK_SIGNING_SECRET_TOO_SHORT",
    ]


def test_api_contract_requires_correctly_paired_prava_environment() -> None:
    base = {
        "DATABASE_URL": "postgresql://restock:secret@postgres/restock",
        "RESTOCK_ENV": "production",
        "RESTOCK_DEMO_MODE": "0",
    }
    shared = {
        **base,
        "RESTOCK_SESSION_SECRET": "session-secret-placeholder-over-32-characters",
        "RESTOCK_SLACK_SERVICE_TOKEN": "slack-service-placeholder-over-32-characters",
        "RESTOCK_WORKER_SERVICE_TOKEN": "worker-service-placeholder-over-32-characters",
    }
    assert validate("api", {**shared, "PRAVA_API_KEY": "sk_test_key"}) == [
        "PRAVA_API_URL_OR_SANDBOX_URL_REQUIRED"
    ]
    assert validate(
        "api",
        {
            **shared,
            "PRAVA_API_KEY": "sk_live_key",
            "PRAVA_API_URL": "https://api.prava.space",
        },
    ) == ["PRAVA_PRODUCTION_GATE_REQUIRED"]
