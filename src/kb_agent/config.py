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
    ai_provider: str = "heuristic"

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
            ai_provider=os.getenv("KB_AI_PROVIDER", cls.ai_provider),
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


def _validate_timezone(timezone: str) -> None:
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"KB_TIMEZONE is not valid: {timezone}") from error
