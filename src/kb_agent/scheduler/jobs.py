from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DigestJob:
    name: str
    kind: str
    user_id: str
    timezone: str
    hour: int
    day: str | None = None


@dataclass(frozen=True)
class AIRetryJob:
    name: str
    kind: str
    interval_minutes: int


def build_digest_jobs(
    *,
    user_id: str,
    daily_hour: int,
    weekly_day: str,
    weekly_hour: int,
    timezone: str,
) -> list[DigestJob]:
    return [
        DigestJob(
            name="daily_digest",
            kind="today",
            user_id=user_id,
            timezone=timezone,
            hour=daily_hour,
        ),
        DigestJob(
            name="weekly_digest",
            kind="week",
            user_id=user_id,
            timezone=timezone,
            hour=weekly_hour,
            day=weekly_day,
        ),
    ]


def build_ai_retry_job(*, interval_minutes: int) -> AIRetryJob:
    return AIRetryJob(name="ai_retry", kind="ai_retry", interval_minutes=interval_minutes)
