import pytest

from hh_relay.config import MonitorSettings


def test_monitor_settings_use_repository_openai_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://database")
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_DAILY_TOKEN_BUDGET", raising=False)

    settings = MonitorSettings.from_env()

    assert settings.openai_model == "gpt-5.4-mini"
    assert settings.daily_token_budget == 250_000
