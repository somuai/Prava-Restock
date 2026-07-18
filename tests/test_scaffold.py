from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_phase_zero_scaffold_is_complete() -> None:
    expected = {
        "agent",
        "triggers",
        "payments",
        "merchant",
        "ui",
        "logs",
        "demo",
        "tests",
    }
    assert expected <= {path.name for path in ROOT.iterdir() if path.is_dir()}
    assert (ROOT / "PRD.md").is_file()
    assert (ROOT / "TECHNICAL_PRD.md").is_file()
    assert (ROOT / "SKILL.md").is_file()


def test_example_environment_contains_placeholders_only() -> None:
    lines = (ROOT / ".env.example").read_text().splitlines()
    assert "OPENAI_API_KEY=" in lines
    assert "PRAVA_API_KEY=" in lines
    assert "PRAVA_SANDBOX_URL=" in lines
    assert "HOME_MERCHANT_MODE=disclosed_mock" in lines
    assert "ZEPTO_REAL_PAYMENT_ENABLED=0" in lines
    assert all("sk_" not in line and "secret" not in line.lower() for line in lines)
