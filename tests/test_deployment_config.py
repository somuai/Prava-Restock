from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_container_runs_migrations_as_non_root_with_healthcheck() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "USER 10001:10001" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "alembic upgrade head" in dockerfile
    assert "python scripts/provision_reviewer.py" in dockerfile
    assert "exec uvicorn ui.api:app" in dockerfile


def test_runtime_state_and_native_projects_are_outside_build_context() -> None:
    ignored = set((ROOT / ".dockerignore").read_text().splitlines())

    assert {".env*", "logs", "ui/web/android", "ui/web/ios"} <= ignored


def test_hosting_platforms_gate_traffic_on_readiness() -> None:
    assert '"healthcheckPath": "/ready"' in (ROOT / "railway.json").read_text()
    assert "healthCheckPath: /ready" in (ROOT / "render.yaml").read_text()
