from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DigestJob:
    name: str
    user_id: str
    hour: int
    day: str | None = None


def build_digest_jobs(
    *,
    user_id: str,
    daily_hour: int,
    weekly_day: str,
    weekly_hour: int,
) -> list[DigestJob]:
    return [
        DigestJob(name="daily_digest", user_id=user_id, hour=daily_hour),
        DigestJob(
            name="weekly_digest",
            user_id=user_id,
            hour=weekly_hour,
            day=weekly_day,
        ),
    ]
