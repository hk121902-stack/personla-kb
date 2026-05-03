from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

_VALID_WEEKLY_DAYS = frozenset({"mon", "tue", "wed", "thu", "fri", "sat", "sun"})


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str | None = None
    database_path: str = "./data/kb.sqlite3"
    timezone: str = "Asia/Kolkata"
    daily_digest_hour: int = 9
    weekly_digest_day: str = "sun"
    weekly_digest_hour: int = 10
    ai_provider_chain: str = (
        "gemini:gemini-2.5-flash-lite,gemini:gemini-2.5-flash,"
        "ollama:qwen3:8b,heuristic"
    )
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ai_sync_wait_seconds: float = 6.0
    ai_retry_interval_minutes: int = 30

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()

        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")

        telegram_chat_id = _optional_env("KB_TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_ID")
        if telegram_chat_id is None:
            raise ValueError("KB_TELEGRAM_CHAT_ID is required")

        timezone = os.getenv("KB_TIMEZONE", cls.timezone)
        _validate_timezone(timezone)
        daily_digest_hour = _env_hour("KB_DAILY_DIGEST_HOUR", cls.daily_digest_hour)
        weekly_digest_hour = _env_hour("KB_WEEKLY_DIGEST_HOUR", cls.weekly_digest_hour)
        weekly_digest_day = os.getenv("KB_WEEKLY_DIGEST_DAY", cls.weekly_digest_day).lower()
        if weekly_digest_day not in _VALID_WEEKLY_DAYS:
            raise ValueError("KB_WEEKLY_DIGEST_DAY must be one of mon/tue/wed/thu/fri/sat/sun")

        return cls(
            telegram_bot_token=token,
            telegram_chat_id=telegram_chat_id,
            database_path=os.getenv("KB_DATABASE_PATH", cls.database_path),
            timezone=timezone,
            daily_digest_hour=daily_digest_hour,
            weekly_digest_day=weekly_digest_day,
            weekly_digest_hour=weekly_digest_hour,
            ai_provider_chain=os.getenv("KB_AI_PROVIDER_CHAIN", cls.ai_provider_chain),
            gemini_api_key=os.getenv("KB_GEMINI_API_KEY", ""),
            gemini_model=os.getenv("KB_GEMINI_MODEL", cls.gemini_model),
            ollama_base_url=os.getenv("KB_OLLAMA_BASE_URL", cls.ollama_base_url),
            ollama_model=os.getenv("KB_OLLAMA_MODEL", cls.ollama_model),
            ai_sync_wait_seconds=_env_float(
                "KB_AI_SYNC_WAIT_SECONDS",
                cls.ai_sync_wait_seconds,
            ),
            ai_retry_interval_minutes=int(
                _env_float(
                    "KB_AI_RETRY_INTERVAL_MINUTES",
                    float(cls.ai_retry_interval_minutes),
                ),
            ),
        )


def _optional_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _env_hour(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        hour = int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer hour between 0 and 23") from error
    if hour < 0 or hour > 23:
        raise ValueError(f"{name} must be between 0 and 23")
    return hour


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error
    if parsed < 0:
        raise ValueError(f"{name} must be zero or greater")
    return parsed


def _validate_timezone(timezone: str) -> None:
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"KB_TIMEZONE is not valid: {timezone}") from error
