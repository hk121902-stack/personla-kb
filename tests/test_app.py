from kb_agent.app import register_digest_jobs
from kb_agent.config import Settings
from kb_agent.core.digests import Digest


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs = []

    def add_job(self, func, trigger, **kwargs) -> None:
        self.jobs.append({"func": func, "trigger": trigger, **kwargs})


class FakeBot:
    def __init__(self) -> None:
        self.messages = []

    async def send_message(self, *, chat_id: str, text: str) -> None:
        self.messages.append({"chat_id": chat_id, "text": text})


class FakeApplication:
    def __init__(self) -> None:
        self.bot = FakeBot()


class FakeDigestService:
    def __init__(self) -> None:
        self.daily_user_ids = []
        self.weekly_user_ids = []

    def daily(self, *, user_id: str) -> Digest:
        self.daily_user_ids.append(user_id)
        return Digest(text="Daily body", items=[])

    def weekly(self, *, user_id: str) -> Digest:
        self.weekly_user_ids.append(user_id)
        return Digest(text="Weekly body", items=[])


def test_register_digest_jobs_adds_daily_and_weekly_cron_jobs() -> None:
    scheduler = FakeScheduler()
    settings = Settings(
        telegram_bot_token="token",
        telegram_chat_id="123",
        daily_digest_hour=9,
        weekly_digest_day="sun",
        weekly_digest_hour=10,
        timezone="Asia/Kolkata",
    )

    register_digest_jobs(
        application=FakeApplication(),
        digest_service=FakeDigestService(),
        scheduler=scheduler,
        settings=settings,
    )

    assert [job["name"] for job in scheduler.jobs] == ["daily_digest", "weekly_digest"]
    assert [job["trigger"].fields[5].expressions[0].first for job in scheduler.jobs] == [9, 10]
    assert scheduler.jobs[0]["trigger"].fields[4].expressions[0].__str__() == "*"
    assert scheduler.jobs[1]["trigger"].fields[4].expressions[0].__str__() == "sun"


async def test_registered_digest_callback_sends_digest_message() -> None:
    scheduler = FakeScheduler()
    application = FakeApplication()
    digest_service = FakeDigestService()
    settings = Settings(
        telegram_bot_token="token",
        telegram_chat_id="123",
        daily_digest_hour=9,
        timezone="Asia/Kolkata",
    )

    register_digest_jobs(
        application=application,
        digest_service=digest_service,
        scheduler=scheduler,
        settings=settings,
    )
    await scheduler.jobs[0]["func"]()

    assert digest_service.daily_user_ids == ["telegram:123"]
    assert application.bot.messages == [{"chat_id": "123", "text": "Daily body"}]
