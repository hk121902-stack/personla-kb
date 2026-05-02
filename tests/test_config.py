from kb_agent.config import Settings


def test_settings_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("KB_DATABASE_PATH", "./tmp/kb.sqlite3")

    settings = Settings.from_env()

    assert settings.telegram_bot_token == "token"
    assert settings.database_path == "./tmp/kb.sqlite3"
    assert settings.ai_provider == "heuristic"
