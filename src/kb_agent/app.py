from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
from telegram.ext import Application

from kb_agent.ai.providers import HeuristicAIProvider
from kb_agent.config import Settings
from kb_agent.core.archive_review import ArchiveReviewService
from kb_agent.core.digests import DigestService
from kb_agent.core.retrieval import RetrievalService
from kb_agent.core.service import KnowledgeService, SystemClock
from kb_agent.extraction.extractors import WebpageExtractor
from kb_agent.storage.sqlite import SQLiteItemRepository
from kb_agent.telegram.bot import TelegramMessageHandler, build_application


@dataclass(frozen=True)
class Runtime:
    settings: Settings
    http_client: httpx.AsyncClient
    application: Application


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
    application = build_application(handler, settings.telegram_bot_token)

    return Runtime(
        settings=settings,
        http_client=http_client,
        application=application,
    )


def main() -> None:
    settings = Settings.from_env()
    runtime = build_runtime(settings)
    try:
        runtime.application.run_polling()
    finally:
        asyncio.run(runtime.http_client.aclose())


if __name__ == "__main__":
    main()
