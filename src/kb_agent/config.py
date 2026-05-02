from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
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

        return cls(
            telegram_bot_token=token,
            database_path=os.getenv("KB_DATABASE_PATH", cls.database_path),
            timezone=os.getenv("KB_TIMEZONE", cls.timezone),
            daily_digest_hour=_env_int("KB_DAILY_DIGEST_HOUR", cls.daily_digest_hour),
            weekly_digest_day=os.getenv("KB_WEEKLY_DIGEST_DAY", cls.weekly_digest_day),
            weekly_digest_hour=_env_int("KB_WEEKLY_DIGEST_HOUR", cls.weekly_digest_hour),
            ai_provider=os.getenv("KB_AI_PROVIDER", cls.ai_provider),
        )


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)
