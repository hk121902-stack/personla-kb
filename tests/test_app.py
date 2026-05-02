import asyncio
from types import SimpleNamespace

import kb_agent.app as app_module
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
        self.post_init = None
        self.post_shutdown = None

    def run_polling(self) -> None:
        async def run_lifecycle() -> None:
            assert self.post_init is not None
            assert self.post_shutdown is not None
            await self.post_init(self)
            await self.post_shutdown(self)

        asyncio.run(run_lifecycle())


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


def test_main_starts_and_stops_scheduler_from_application_lifecycle(monkeypatch) -> None:
    scheduler = LoopCheckingScheduler()
    application = FakeApplication()
    http_client = FakeHttpClient()
    runtime = SimpleNamespace(
        scheduler=scheduler,
        application=application,
        http_client=http_client,
    )

    monkeypatch.setattr(
        app_module.Settings,
        "from_env",
        classmethod(lambda cls: Settings(telegram_bot_token="token", telegram_chat_id="123")),
    )
    monkeypatch.setattr(app_module, "build_runtime", lambda settings: runtime)

    app_module.main()

    assert scheduler.events == ["start", ("shutdown", False)]
    assert http_client.closed
    assert http_client.close_count == 1


class LoopCheckingScheduler:
    def __init__(self) -> None:
        self.events = []
        self.running = False

    def start(self) -> None:
        asyncio.get_running_loop()
        self.events.append("start")
        self.running = True

    def shutdown(self, *, wait: bool) -> None:
        self.events.append(("shutdown", wait))
        self.running = False


class FakeHttpClient:
    def __init__(self) -> None:
        self.closed = False
        self.close_count = 0

    @property
    def is_closed(self) -> bool:
        return self.closed

    async def aclose(self) -> None:
        self.close_count += 1
        self.closed = True
