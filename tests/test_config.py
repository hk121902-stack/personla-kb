import pytest

from kb_agent.config import Settings


def test_settings_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("KB_DATABASE_PATH", "./tmp/kb.sqlite3")
    monkeypatch.setenv("KB_TELEGRAM_CHAT_ID", "123")

    settings = Settings.from_env()

    assert settings.telegram_bot_token == "token"
    assert settings.database_path == "./tmp/kb.sqlite3"
    assert settings.telegram_chat_id == "123"
    assert settings.ai_provider == "heuristic"


def test_settings_requires_telegram_chat_id(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.delenv("KB_TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(ValueError, match="KB_TELEGRAM_CHAT_ID is required"):
        Settings.from_env()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("KB_DAILY_DIGEST_HOUR", "24"),
        ("KB_WEEKLY_DIGEST_HOUR", "-1"),
        ("KB_WEEKLY_DIGEST_DAY", "someday"),
        ("KB_TIMEZONE", "No/Such_Zone"),
    ],
)
def test_settings_rejects_invalid_schedule_config(monkeypatch, name: str, value: str) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("KB_TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError):
        Settings.from_env()


def test_settings_rejects_non_integer_digest_hour_with_config_error(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("KB_TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("KB_DAILY_DIGEST_HOUR", "morning")

    with pytest.raises(ValueError, match="KB_DAILY_DIGEST_HOUR must be an integer hour"):
        Settings.from_env()
