import pytest

import kb_agent.config as config_module
from kb_agent.config import Settings


@pytest.fixture(autouse=True)
def ignore_dotenv(monkeypatch) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: False)


def test_settings_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("KB_DATABASE_PATH", "./tmp/kb.sqlite3")
    monkeypatch.setenv("KB_TELEGRAM_CHAT_ID", "123")

    settings = Settings.from_env()

    assert settings.telegram_bot_token == "token"
    assert settings.database_path == "./tmp/kb.sqlite3"
    assert settings.telegram_chat_id == "123"
    assert (
        settings.ai_provider_chain
        == "gemini:gemini-2.5-flash-lite,gemini:gemini-2.5-flash,ollama:qwen3:8b,heuristic"
    )


def test_settings_reads_phase_two_ai_config(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("KB_TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("KB_AI_PROVIDER_CHAIN", "gemini:lite,ollama:qwen3:8b,heuristic")
    monkeypatch.setenv("KB_GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("KB_GEMINI_MODEL", "lite")
    monkeypatch.setenv("KB_OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("KB_OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.setenv("KB_AI_SYNC_WAIT_SECONDS", "4")
    monkeypatch.setenv("KB_AI_RETRY_INTERVAL_MINUTES", "15")

    settings = Settings.from_env()

    assert settings.ai_provider_chain == "gemini:lite,ollama:qwen3:8b,heuristic"
    assert settings.gemini_api_key == "gemini-key"
    assert settings.gemini_model == "lite"
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.ollama_model == "qwen3:8b"
    assert settings.ai_sync_wait_seconds == 4.0
    assert settings.ai_retry_interval_minutes == 15


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
