from kb_agent.scheduler.jobs import build_digest_jobs


def test_build_digest_jobs_returns_daily_and_weekly_jobs() -> None:
    jobs = build_digest_jobs(
        user_id="telegram:123",
        daily_hour=9,
        weekly_day="sun",
        weekly_hour=10,
        timezone="Asia/Kolkata",
    )

    assert [job.name for job in jobs] == ["daily_digest", "weekly_digest"]
    assert [job.kind for job in jobs] == ["today", "week"]
    assert [job.timezone for job in jobs] == ["Asia/Kolkata", "Asia/Kolkata"]
    assert jobs[1].day == "sun"
