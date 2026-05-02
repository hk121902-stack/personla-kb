from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application

from kb_agent.ai.providers import HeuristicAIProvider
from kb_agent.config import Settings
from kb_agent.core.archive_review import ArchiveReviewService
from kb_agent.core.digests import DigestService
from kb_agent.core.retrieval import RetrievalService
from kb_agent.core.service import KnowledgeService, SystemClock
from kb_agent.extraction.extractors import WebpageExtractor
from kb_agent.scheduler.jobs import DigestJob, build_digest_jobs
from kb_agent.storage.sqlite import SQLiteItemRepository
from kb_agent.telegram.bot import TelegramMessageHandler, build_application
from kb_agent.telegram.formatter import format_daily_digest, format_weekly_digest


@dataclass(frozen=True)
class Runtime:
    settings: Settings
    http_client: httpx.AsyncClient
    application: Application
    scheduler: AsyncIOScheduler | None = None


def build_runtime(settings: Settings) -> Runtime:
    if settings.ai_provider != "heuristic":
        raise ValueError(f"Unsupported AI provider: {settings.ai_provider}")

    repository = SQLiteItemRepository(settings.database_path)
    http_client = httpx.AsyncClient()
    extractor = WebpageExtractor(http_client)
    ai_provider = HeuristicAIProvider()
    clock = SystemClock()

    knowledge = KnowledgeService(
        repository=repository,
        extractor=extractor,
        ai_provider=ai_provider,
        clock=clock,
    )
    retrieval = RetrievalService(repository, ai_provider)
    digest_service = DigestService(repository)
    archive_review_service = ArchiveReviewService(repository)
    handler = TelegramMessageHandler(
        knowledge=knowledge,
        retrieval=retrieval,
        digest_service=digest_service,
        archive_review_service=archive_review_service,
    )
    application = build_application(
        handler,
        settings.telegram_bot_token,
        allowed_chat_id=settings.telegram_chat_id,
    )
    scheduler = None
    if settings.telegram_chat_id is not None:
        scheduler = AsyncIOScheduler(timezone=settings.timezone)
        register_digest_jobs(
            application=application,
            digest_service=digest_service,
            scheduler=scheduler,
            settings=settings,
        )

    return Runtime(
        settings=settings,
        http_client=http_client,
        application=application,
        scheduler=scheduler,
    )


def register_digest_jobs(
    *,
    application: Any,
    digest_service: DigestService,
    scheduler: Any,
    settings: Settings,
) -> None:
    if settings.telegram_chat_id is None:
        return

    user_id = f"telegram:{settings.telegram_chat_id}"
    for job in build_digest_jobs(
        user_id=user_id,
        daily_hour=settings.daily_digest_hour,
        weekly_day=settings.weekly_digest_day,
        weekly_hour=settings.weekly_digest_hour,
        timezone=settings.timezone,
    ):
        scheduler.add_job(
            _build_digest_callback(
                application=application,
                digest_service=digest_service,
                job=job,
                chat_id=settings.telegram_chat_id,
            ),
            _build_trigger(job),
            id=job.name,
            name=job.name,
            replace_existing=True,
        )


def _build_digest_callback(
    *,
    application: Any,
    digest_service: DigestService,
    job: DigestJob,
    chat_id: str,
) -> Callable[[], Any]:
    async def send_digest() -> None:
        if job.kind == "today":
            text = format_daily_digest(digest_service.daily(user_id=job.user_id))
        else:
            text = format_weekly_digest(digest_service.weekly(user_id=job.user_id))
        await application.bot.send_message(chat_id=chat_id, text=text)

    return send_digest


def _build_trigger(job: DigestJob) -> CronTrigger:
    if job.kind == "week":
        return CronTrigger(
            day_of_week=job.day,
            hour=job.hour,
            minute=0,
            timezone=job.timezone,
        )

    return CronTrigger(hour=job.hour, minute=0, timezone=job.timezone)


def install_runtime_lifecycle(runtime: Any) -> None:
    previous_post_init = runtime.application.post_init
    previous_post_stop = runtime.application.post_stop
    previous_post_shutdown = runtime.application.post_shutdown

    async def post_init(application: Application) -> None:
        if previous_post_init is not None:
            await previous_post_init(application)
        if runtime.scheduler is not None and not runtime.scheduler.running:
            runtime.scheduler.start()

    async def post_stop(application: Application) -> None:
        if runtime.scheduler is not None and runtime.scheduler.running:
            runtime.scheduler.shutdown(wait=False)
            await asyncio.sleep(0)
        if previous_post_stop is not None:
            await previous_post_stop(application)

    async def post_shutdown(application: Application) -> None:
        await _close_http_client(runtime.http_client)
        if previous_post_shutdown is not None:
            await previous_post_shutdown(application)

    runtime.application.post_init = post_init
    runtime.application.post_stop = post_stop
    runtime.application.post_shutdown = post_shutdown


def main() -> None:
    settings = Settings.from_env()
    runtime = build_runtime(settings)
    install_runtime_lifecycle(runtime)
    try:
        runtime.application.run_polling()
    finally:
        if runtime.scheduler is not None and runtime.scheduler.running:
            runtime.scheduler.shutdown(wait=False)
        if not _is_http_client_closed(runtime.http_client):
            asyncio.run(_close_http_client(runtime.http_client))


async def _close_http_client(http_client: httpx.AsyncClient) -> None:
    if not _is_http_client_closed(http_client):
        await http_client.aclose()


def _is_http_client_closed(http_client: httpx.AsyncClient) -> bool:
    return bool(getattr(http_client, "is_closed", False))


if __name__ == "__main__":
    main()
