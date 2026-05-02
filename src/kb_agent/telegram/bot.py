from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from inspect import isawaitable
from typing import Any

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from kb_agent.telegram.formatter import (
    format_archive_recommendations,
    format_daily_digest,
    format_retrieval_response,
    format_save_confirmation,
    format_weekly_digest,
)
from kb_agent.telegram.parser import (
    ArchiveCommand,
    AskCommand,
    DigestCommand,
    ParseCommand,
    ReviewArchiveCommand,
    SaveCommand,
    ShowCommand,
    parse_message,
)

Reply = Callable[[str], Any]

_HELP_TEXT = "Send a link to save it, or ask a question about your knowledge base."
_DIGEST_UNAVAILABLE = "Digest service is not available right now."
_ARCHIVE_REVIEW_UNAVAILABLE = "Archive review is not available right now."
_ARCHIVE_MISSING_ID = "Tell me which item to archive, like: archive <item_id>."


class TelegramMessageHandler:
    def __init__(
        self,
        *,
        knowledge: Any,
        retrieval: Any,
        digest_service: Any | None,
        archive_review_service: Any | None,
    ) -> None:
        self.knowledge = knowledge
        self.retrieval = retrieval
        self.digest_service = digest_service
        self.archive_review_service = archive_review_service

    async def handle_text(self, *, user_id: str, text: str, reply: Reply) -> None:
        command = parse_message(text)

        if isinstance(command, SaveCommand):
            item = await _maybe_await(
                self.knowledge.save_link(
                    user_id=user_id,
                    url=command.url,
                    note=command.note,
                    priority=command.priority,
                ),
            )
            await _send(reply, format_save_confirmation(item))
            return

        if isinstance(command, AskCommand):
            if not command.question:
                await _send(reply, _HELP_TEXT)
                return
            response = await _maybe_await(
                self.retrieval.answer(
                    user_id=user_id,
                    question=command.question,
                    include_archived=command.include_archived,
                ),
            )
            await _send(reply, format_retrieval_response(response))
            return

        if isinstance(command, DigestCommand):
            await self._handle_digest(user_id=user_id, command=command, reply=reply)
            return

        if isinstance(command, ReviewArchiveCommand):
            await self._handle_review_archive(user_id=user_id, reply=reply)
            return

        if isinstance(command, ArchiveCommand):
            await self._handle_archive(user_id=user_id, command=command, reply=reply)
            return

        if isinstance(command, ShowCommand):
            await self._handle_show(user_id=user_id, command=command, reply=reply)
            return

        if isinstance(command, ParseCommand):
            await _send(reply, _HELP_TEXT)

    async def _handle_digest(
        self,
        *,
        user_id: str,
        command: DigestCommand,
        reply: Reply,
    ) -> None:
        if self.digest_service is None:
            await _send(reply, _DIGEST_UNAVAILABLE)
            return

        if command.kind == "today":
            digest = await _maybe_await(self.digest_service.daily(user_id=user_id))
            await _send(reply, format_daily_digest(digest))
            return

        digest = await _maybe_await(self.digest_service.weekly(user_id=user_id))
        await _send(reply, format_weekly_digest(digest))

    async def _handle_review_archive(self, *, user_id: str, reply: Reply) -> None:
        if self.archive_review_service is None:
            await _send(reply, _ARCHIVE_REVIEW_UNAVAILABLE)
            return

        recommendations = await _maybe_await(
            self.archive_review_service.recommend(user_id=user_id, now=datetime.now(UTC)),
        )
        await _send(reply, format_archive_recommendations(recommendations))

    async def _handle_archive(
        self,
        *,
        user_id: str,
        command: ArchiveCommand,
        reply: Reply,
    ) -> None:
        if not command.item_id:
            await _send(reply, _ARCHIVE_MISSING_ID)
            return

        item = await _maybe_await(
            self.knowledge.archive_item(user_id=user_id, item_id=command.item_id),
        )
        title = item.title or item.url
        await _send(reply, f"Archived: {title}")

    async def _handle_show(
        self,
        *,
        user_id: str,
        command: ShowCommand,
        reply: Reply,
    ) -> None:
        if not command.query:
            await _send(reply, _HELP_TEXT)
            return

        response = await _maybe_await(
            self.retrieval.answer(
                user_id=user_id,
                question=command.query,
                include_archived=False,
            ),
        )
        await _send(reply, format_retrieval_response(response))


def build_application(handler: TelegramMessageHandler, token: str) -> Application:
    async def handle_update(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if (
            update.effective_user is None
            or update.effective_chat is None
            or update.message is None
            or update.message.text is None
        ):
            return

        user_id = _chat_scoped_user_id(update)
        await handler.handle_text(
            user_id=user_id,
            text=update.message.text,
            reply=update.message.reply_text,
        )

    application = Application.builder().token(token).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_update))
    return application


def _chat_scoped_user_id(update: Update) -> str:
    return f"telegram:{update.effective_chat.id}"


async def _send(reply: Reply, text: str) -> None:
    await _maybe_await(reply(text))


async def _maybe_await[T](value: T | Awaitable[T]) -> T:
    if isawaitable(value):
        return await value
    return value
