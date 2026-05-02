from kb_agent.scheduler.jobs import build_digest_jobs


def test_build_digest_jobs_returns_daily_and_weekly_jobs() -> None:
    jobs = build_digest_jobs(
        user_id="telegram:123",
        daily_hour=9,
        weekly_day="sun",
        weekly_hour=10,
    )

    assert [job.name for job in jobs] == ["daily_digest", "weekly_digest"]
