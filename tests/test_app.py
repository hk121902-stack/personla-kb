import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import kb_agent.app as app_module
from kb_agent.app import install_runtime_lifecycle, register_digest_jobs
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

    async def send_message(self, *, chat_id: str, text: str, **kwargs) -> None:
        self.messages.append({"chat_id": chat_id, "text": text, **kwargs})


class FakeApplication:
    def __init__(self) -> None:
        self.bot = FakeBot()
        self.post_init = None
        self.post_stop = None
        self.post_shutdown = None

    def run_polling(self) -> None:
        async def run_lifecycle() -> None:
            assert self.post_init is not None
            assert self.post_stop is not None
            assert self.post_shutdown is not None
            await self.post_init(self)
            await self.post_stop(self)
            await self.post_shutdown(self)

        asyncio.run(run_lifecycle())


class FakeHttpClient:
    def __init__(self, events: list | None = None) -> None:
        self.events = events
        self.closed = False
        self.close_count = 0

    @property
    def is_closed(self) -> bool:
        return self.closed

    async def aclose(self) -> None:
        self.close_count += 1
        if self.events is not None:
            self.events.append("http_close")
        self.closed = True


class FakeDigestService:
    def __init__(self) -> None:
        self.daily_user_ids = []
        self.weekly_user_ids = []

    def daily(self, *, user_id: str) -> Digest:
        self.daily_user_ids.append(user_id)
        return Digest(text="Daily body", items=[], item_aliases={}, kind="today")

    def weekly(self, *, user_id: str) -> Digest:
        self.weekly_user_ids.append(user_id)
        return Digest(text="Weekly body", items=[], item_aliases={}, kind="week")


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
    fixed_now = datetime(2026, 5, 2, 8, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    next_fire_times = [
        job["trigger"].get_next_fire_time(None, fixed_now)
        for job in scheduler.jobs
    ]
    assert next_fire_times == [
        datetime(2026, 5, 2, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        datetime(2026, 5, 3, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    ]


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
    await scheduler.jobs[1]["func"]()

    assert digest_service.daily_user_ids == ["telegram:123"]
    assert digest_service.weekly_user_ids == ["telegram:123"]
    assert application.bot.messages == [
        {
            "chat_id": "123",
            "text": "<b>Daily tiny nudge</b>",
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        {
            "chat_id": "123",
            "text": "<b>Weekly synthesis</b>",
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
    ]


def test_build_runtime_passes_configured_chat_id_to_application(monkeypatch) -> None:
    captured = {}

    def fake_build_application(handler, token, *, allowed_chat_id=None):
        captured["handler"] = handler
        captured["token"] = token
        captured["allowed_chat_id"] = allowed_chat_id
        return FakeApplication()

    monkeypatch.setattr(app_module.httpx, "AsyncClient", FakeHttpClient)
    monkeypatch.setattr(app_module, "build_application", fake_build_application)

    runtime = app_module.build_runtime(
        Settings(
            telegram_bot_token="token",
            telegram_chat_id="123",
            ai_provider_chain="heuristic",
            ai_sync_wait_seconds=4.0,
        ),
    )

    assert runtime.application.bot.messages == []
    assert captured["token"] == "token"
    assert captured["allowed_chat_id"] == "123"
    assert captured["handler"].ai_router.status().chain == ["heuristic:heuristic"]
    assert captured["handler"].ai_sync_wait_seconds == 4.0


async def test_build_runtime_registers_ai_retry_job(monkeypatch, tmp_path) -> None:
    scheduler = FakeScheduler()
    captured = {}

    class FakeKnowledgeService:
        def __init__(self, **kwargs) -> None:
            self.retry_calls = []
            captured["knowledge"] = self

        async def retry_pending_ai(self, *, limit: int, max_attempts: int):
            self.retry_calls.append({"limit": limit, "max_attempts": max_attempts})
            return []

    def fake_build_application(handler, token, *, allowed_chat_id=None):
        return FakeApplication()

    monkeypatch.setattr(app_module.httpx, "AsyncClient", FakeHttpClient)
    monkeypatch.setattr(app_module, "AsyncIOScheduler", lambda timezone: scheduler)
    monkeypatch.setattr(app_module, "KnowledgeService", FakeKnowledgeService)
    monkeypatch.setattr(app_module, "build_application", fake_build_application)

    runtime = app_module.build_runtime(
        Settings(
            telegram_bot_token="token",
            telegram_chat_id="123",
            database_path=str(tmp_path / "kb.sqlite3"),
            ai_provider_chain="heuristic",
            ai_retry_interval_minutes=12,
        ),
    )

    assert runtime.scheduler is scheduler
    assert [job["name"] for job in scheduler.jobs] == [
        "daily_digest",
        "weekly_digest",
        "ai_retry",
    ]
    assert scheduler.jobs[2]["id"] == "ai_retry"
    assert scheduler.jobs[2]["trigger"].interval.total_seconds() == 12 * 60

    await scheduler.jobs[2]["func"]()

    assert captured["knowledge"].retry_calls == [{"limit": 10, "max_attempts": 3}]


def test_main_starts_and_stops_scheduler_from_application_lifecycle(monkeypatch) -> None:
    scheduler = LoopCheckingScheduler()
    application = FakeApplication()
    http_client = FakeHttpClient(scheduler.events)
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

    assert scheduler.events == ["start", ("shutdown", False), "http_close"]
    assert http_client.closed
    assert http_client.close_count == 1


async def test_scheduler_stops_in_post_stop_before_http_client_closes() -> None:
    events = []
    scheduler = LoopCheckingScheduler(events)
    application = FakeApplication()
    http_client = FakeHttpClient(events)

    async def previous_post_stop(_application) -> None:
        events.append("previous_post_stop")

    application.post_stop = previous_post_stop
    runtime = SimpleNamespace(
        scheduler=scheduler,
        application=application,
        http_client=http_client,
    )

    install_runtime_lifecycle(runtime)
    await application.post_init(application)
    await application.post_stop(application)
    await application.post_shutdown(application)

    assert events == ["start", ("shutdown", False), "previous_post_stop", "http_close"]


async def test_post_stop_waits_for_real_scheduler_to_stop() -> None:
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    application = FakeApplication()
    http_client = FakeHttpClient()
    runtime = SimpleNamespace(
        scheduler=scheduler,
        application=application,
        http_client=http_client,
    )

    install_runtime_lifecycle(runtime)
    await application.post_init(application)
    assert scheduler.running

    await application.post_stop(application)

    assert not scheduler.running
    await application.post_shutdown(application)
    assert http_client.closed


class LoopCheckingScheduler:
    def __init__(self, events: list | None = None) -> None:
        self.events = events if events is not None else []
        self.running = False

    def start(self) -> None:
        asyncio.get_running_loop()
        self.events.append("start")
        self.running = True

    def shutdown(self, *, wait: bool) -> None:
        self.events.append(("shutdown", wait))
        self.running = False
