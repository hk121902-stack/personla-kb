from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from inspect import isawaitable
from types import SimpleNamespace
from typing import Any

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from kb_agent.core.models import AIStatus, Status
from kb_agent.telegram.formatter import (
    format_ai_status,
    format_archive_recommendations,
    format_daily_digest,
    format_enrichment_retry_message,
    format_learning_brief,
    format_needs_text_prompt,
    format_pending_learning_brief,
    format_retrieval_response,
    format_save_confirmation,
    format_weekly_digest,
)
from kb_agent.telegram.parser import (
    AIStatusCommand,
    ArchiveCommand,
    AskCommand,
    DigestCommand,
    ModelCommand,
    ParseCommand,
    RefreshCommand,
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
_ARCHIVE_NOT_FOUND = "I could not find that saved item."
_ENRICHMENT_RETRY_MESSAGE = "Saved with basic enrichment. AI brief is pending retry."


class TelegramMessageHandler:
    def __init__(
        self,
        *,
        knowledge: Any,
        retrieval: Any,
        digest_service: Any | None,
        archive_review_service: Any | None,
        ai_router: Any | None = None,
        ai_sync_wait_seconds: float = 6.0,
    ) -> None:
        self.knowledge = knowledge
        self.retrieval = retrieval
        self.digest_service = digest_service
        self.archive_review_service = archive_review_service
        self.ai_router = ai_router
        self.ai_sync_wait_seconds = ai_sync_wait_seconds

    async def handle_text(self, *, user_id: str, text: str, reply: Reply) -> None:
        command = parse_message(text)

        if isinstance(command, SaveCommand):
            if command.note.strip():
                await self._handle_legacy_save(user_id=user_id, command=command, reply=reply)
                return

            if hasattr(self.knowledge, "create_link") and hasattr(
                self.knowledge,
                "enrich_saved_item",
            ):
                item = await _maybe_await(
                    self.knowledge.create_link(
                        user_id=user_id,
                        url=command.url,
                        note=command.note,
                        priority=command.priority,
                    ),
                )
                task = asyncio.create_task(
                    _enrich_saved_item(
                        self.knowledge,
                        user_id=user_id,
                        item_id=item.id,
                    ),
                )
                try:
                    enriched = await asyncio.wait_for(
                        asyncio.shield(task),
                        timeout=self.ai_sync_wait_seconds,
                    )
                except TimeoutError:
                    alias = self._item_alias(item)
                    await _send(reply, format_pending_learning_brief(item, alias=alias))
                    task.add_done_callback(
                        lambda done: asyncio.create_task(
                            _send_enrichment_follow_up(
                                done,
                                reply,
                                fallback_item=item,
                                fallback_alias=alias,
                                alias_for_item=self._item_alias,
                            ),
                        ),
                    )
                    return
                except Exception:
                    await _send(
                        reply,
                        format_enrichment_retry_message(item, alias=self._item_alias(item)),
                    )
                    return
                await _send_enrichment_result(
                    enriched,
                    reply,
                    alias=self._item_alias(enriched),
                )
                return

            await self._handle_legacy_save(user_id=user_id, command=command, reply=reply)
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

        if isinstance(command, AIStatusCommand):
            await self._handle_ai_status(reply=reply)
            return

        if isinstance(command, RefreshCommand):
            await self._handle_refresh(user_id=user_id, command=command, reply=reply)
            return

        if isinstance(command, ModelCommand):
            await self._handle_model(command=command, reply=reply)
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

    async def _handle_legacy_save(
        self,
        *,
        user_id: str,
        command: SaveCommand,
        reply: Reply,
    ) -> None:
        item = await _maybe_await(
            self.knowledge.save_link(
                user_id=user_id,
                url=command.url,
                note=command.note,
                priority=command.priority,
            ),
        )
        await _send(reply, format_save_confirmation(item, alias=self._item_alias(item)))
        if item.status is Status.NEEDS_TEXT:
            await _send(reply, format_needs_text_prompt(item))

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

    async def _handle_ai_status(self, *, reply: Reply) -> None:
        if self.ai_router is None:
            await _send(reply, "AI router is not available right now.")
            return

        pending_count = 0
        repository = getattr(self.knowledge, "repository", None)
        if repository is not None and hasattr(repository, "count_ai_retry_pending"):
            pending_count = await _maybe_await(repository.count_ai_retry_pending())

        status = await _maybe_await(self.ai_router.status())
        if (
            not status.last_error
            and repository is not None
            and hasattr(repository, "last_ai_error")
        ):
            last_error = await _maybe_await(repository.last_ai_error())
            if last_error:
                status = SimpleNamespace(chain=status.chain, last_error=last_error)

        await _send(
            reply,
            format_ai_status(status, pending_retry_count=pending_count),
        )

    async def _handle_refresh(
        self,
        *,
        user_id: str,
        command: RefreshCommand,
        reply: Reply,
    ) -> None:
        if not command.item_ref:
            await _send(reply, "Tell me which item to refresh, like: refresh kb_7f3a.")
            return

        try:
            item = await _maybe_await(
                self.knowledge.refresh_item(user_id=user_id, item_ref=command.item_ref),
            )
        except ValueError:
            await _send(reply, "I could not find that saved item.")
            return

        await _send_enrichment_result(item, reply, alias=self._item_alias(item))

    async def _handle_model(self, *, command: ModelCommand, reply: Reply) -> None:
        if self.ai_router is None:
            await _send(reply, "AI router is not available right now.")
            return

        if not command.provider_model:
            await _send(reply, "Tell me which model to use, like: model gemini:lite.")
            return

        try:
            self.ai_router.select_model(command.provider_model)
        except ValueError as error:
            await _send(reply, str(error))
            return

        await _send(reply, f"Model selected: {command.provider_model}")

    async def _handle_review_archive(self, *, user_id: str, reply: Reply) -> None:
        if self.archive_review_service is None:
            await _send(reply, _ARCHIVE_REVIEW_UNAVAILABLE)
            return

        recommendations = await _maybe_await(
            self.archive_review_service.recommend(user_id=user_id, now=datetime.now(UTC)),
        )
        await _send(
            reply,
            format_archive_recommendations(
                recommendations,
                alias_for_item=self._item_alias,
            ),
        )

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

        try:
            item = await _maybe_await(
                self.knowledge.archive_item(user_id=user_id, item_id=command.item_id),
            )
        except ValueError:
            await _send(reply, _ARCHIVE_NOT_FOUND)
            return

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

    def _item_alias(self, item: Any) -> str | None:
        repository = getattr(self.knowledge, "repository", None)
        alias_for_item = getattr(repository, "item_alias", None)
        if callable(alias_for_item):
            return alias_for_item(item.user_id, item.id)
        return None


def build_application(
    handler: TelegramMessageHandler,
    token: str,
    *,
    allowed_chat_id: str | None = None,
) -> Application:
    async def handle_update(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if (
            update.effective_user is None
            or update.effective_chat is None
            or update.message is None
            or update.message.text is None
        ):
            return

        if allowed_chat_id is not None and str(update.effective_chat.id) != allowed_chat_id:
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


async def _send_enrichment_follow_up(
    done: asyncio.Task[Any],
    reply: Reply,
    *,
    fallback_item: Any | None = None,
    fallback_alias: str | None = None,
    alias_for_item: Callable[[Any], str | None] | None = None,
) -> None:
    try:
        try:
            item = done.result()
        except asyncio.CancelledError:
            return
        except Exception:
            if fallback_item is None:
                await _send(reply, _ENRICHMENT_RETRY_MESSAGE)
            else:
                await _send(
                    reply,
                    format_enrichment_retry_message(
                        fallback_item,
                        alias=fallback_alias,
                    ),
                )
            return
        alias = alias_for_item(item) if alias_for_item is not None else fallback_alias
        await _send_enrichment_result(item, reply, alias=alias)
    except Exception:
        return


async def _send_enrichment_result(item: Any, reply: Reply, *, alias: str | None = None) -> None:
    if item.status is Status.NEEDS_TEXT:
        await _send(reply, format_learning_brief(item, alias=alias))
        await _send(reply, format_needs_text_prompt(item))
        return

    if _needs_enrichment_retry_message(item):
        await _send(reply, format_enrichment_retry_message(item, alias=alias))
        return

    await _send(reply, format_learning_brief(item, alias=alias))


def _needs_enrichment_retry_message(item: Any) -> bool:
    return item.status is Status.FAILED_ENRICHMENT or item.ai_status in {
        AIStatus.FAILED,
        AIStatus.RETRY_PENDING,
    }


async def _enrich_saved_item(knowledge: Any, *, user_id: str, item_id: str) -> Any:
    return await _maybe_await(
        knowledge.enrich_saved_item(user_id=user_id, item_id=item_id),
    )


async def _maybe_await[T](value: T | Awaitable[T]) -> T:
    if isawaitable(value):
        return await value
    return value
