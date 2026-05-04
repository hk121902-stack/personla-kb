from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from kb_agent.core.archive_review import ArchiveRecommendation
from kb_agent.core.models import AIStatus, LearningBrief, Priority, SavedItem, SourceType, Status
from kb_agent.telegram.bot import TelegramMessageHandler, _chat_scoped_user_id, build_application


def _saved_item(*, title: str = "Saved Title") -> SavedItem:
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/rag",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )
    return replace(item, title=title, status=Status.READY, tags=["saved"])


class FakeKnowledge:
    def __init__(self) -> None:
        self.archived: tuple[str, str] | None = None
        self.repository = type("Repository", (), {"count_ai_retry_pending": lambda _: 0})()

    async def save_link(self, *, user_id, url, note="", priority=None):
        return _saved_item()

    async def archive_item(self, *, user_id, item_id):
        self.archived = (user_id, item_id)
        return replace(_saved_item(title="Archived Title"), id=item_id, archived=True)

    async def get_item(self, *, user_id, item_ref):
        if item_ref == "missing":
            raise ValueError("missing")
        return replace(_saved_item(title="Detailed Item"), id="7f3a9b8c1234")

    async def latest_item(self, *, user_id):
        return replace(_saved_item(title="Latest Item"), id="9c11aaaa1234")


class SlowKnowledge(FakeKnowledge):
    def __init__(self) -> None:
        super().__init__()
        self.created = replace(_saved_item(title="https://example.com/rag"), id="7f3a9b8c1234")

    def create_link(self, *, user_id, url, note="", priority=None):
        return self.created

    async def enrich_saved_item(self, *, user_id, item_id):
        await asyncio.sleep(0.01)
        return replace(self.created, title="Finished Brief")


class RecordingSplitKnowledge(FakeKnowledge):
    def __init__(self) -> None:
        super().__init__()
        self.save_link_calls: list[dict[str, object]] = []
        self.create_link_calls: list[dict[str, object]] = []
        self.enrich_saved_item_calls: list[dict[str, object]] = []
        self.created = replace(_saved_item(title="https://example.com/rag"), id="7f3a9b8c1234")

    async def save_link(self, *, user_id, url, note="", priority=None):
        self.save_link_calls.append(
            {"user_id": user_id, "url": url, "note": note, "priority": priority},
        )
        return _saved_item()

    async def create_link(self, *, user_id, url, note="", priority=None):
        self.create_link_calls.append(
            {"user_id": user_id, "url": url, "note": note, "priority": priority},
        )
        return self.created

    async def enrich_saved_item(self, *, user_id, item_id):
        self.enrich_saved_item_calls.append({"user_id": user_id, "item_id": item_id})
        return replace(self.created, title="Finished Brief")


class FastFailingEnrichmentKnowledge(SlowKnowledge):
    async def enrich_saved_item(self, *, user_id, item_id):
        raise RuntimeError("AI unavailable")


class SlowNeedsTextKnowledge(SlowKnowledge):
    async def enrich_saved_item(self, *, user_id, item_id):
        await asyncio.sleep(0.01)
        return replace(
            self.created,
            status=Status.NEEDS_TEXT,
            title="https://example.com/rag",
        )


class FastNeedsTextKnowledge(SlowKnowledge):
    async def enrich_saved_item(self, *, user_id, item_id):
        return replace(
            self.created,
            status=Status.NEEDS_TEXT,
            ai_status=AIStatus.FAILED,
            title="https://example.com/rag",
        )


class SlowRetryPendingKnowledge(SlowKnowledge):
    async def enrich_saved_item(self, *, user_id, item_id):
        await asyncio.sleep(0.01)
        return replace(
            self.created,
            status=Status.FAILED_ENRICHMENT,
            ai_status=AIStatus.RETRY_PENDING,
        )


class FakeAIRouter:
    def __init__(self) -> None:
        self.selected: str | None = None

    def status(self):
        return type(
            "Status",
            (),
            {
                "chain": ["gemini:lite", "heuristic:heuristic"],
                "selected_model": "gemini:lite",
                "gemini_model": "lite",
                "ollama_base_url": "http://localhost:11434",
                "ollama_model": "qwen3:8b",
                "last_error": "",
            },
        )()

    def select_model(self, provider_model: str) -> None:
        self.selected = provider_model


class FakeRetrieval:
    async def answer(self, *, user_id, question, include_archived=False):
        return type("Response", (), {"text": "From your knowledge base\nAnswer", "matches": []})()


class FakeDigest:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def daily(self, *, user_id):
        self.calls.append(("daily", user_id))
        return type("Digest", (), {"text": "Daily tiny nudge", "items": []})()

    async def weekly(self, *, user_id):
        self.calls.append(("weekly", user_id))
        return type("Digest", (), {"text": "Weekly synthesis", "items": []})()


class FakeArchiveReview:
    async def recommend(self, *, user_id, now):
        return [
            ArchiveRecommendation(
                item=replace(_saved_item(title="Old Link"), id="7f3a9b8c1234"),
                reason="old_low_priority",
            ),
        ]


class RecordingTelegramHandler:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def handle_text(
        self,
        *,
        user_id: str,
        text: str,
        reply,
        reply_to_text: str | None = None,
    ) -> None:
        self.calls.append(
            {"user_id": user_id, "text": text, "reply_to_text": reply_to_text},
        )
        await reply("handled")


class RecordingMessage:
    def __init__(self, text: str, *, reply_to_text: str | None = None) -> None:
        self.text = text
        self.reply_to_message = (
            type("ReplyToMessage", (), {"text": reply_to_text})()
            if reply_to_text is not None
            else None
        )
        self.replies: list[str] = []
        self.reply_kwargs: dict[str, object] = {}

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append(text)
        self.reply_kwargs = kwargs


def _text_update(*, chat_id: int, text: str = "hello", reply_to_text: str | None = None):
    message = RecordingMessage(text, reply_to_text=reply_to_text)
    update = type(
        "Update",
        (),
        {
            "effective_user": type("User", (), {"id": 111})(),
            "effective_chat": type("Chat", (), {"id": chat_id})(),
            "message": message,
        },
    )()
    return update, message


def _message_callback(application):
    return application.handlers[0][0].callback


def _assert_compact_card(
    text: str,
    *,
    title: str,
    url: str = "https://example.com/rag",
    alias: str | None = None,
    tags: str = "saved",
) -> None:
    assert text.startswith(f'<b><a href="{url}">{title}</a></b>')
    if alias is None:
        assert "ID: kb_" in text
        assert 'Need more? Reply "details" or send details kb_' in text
    else:
        assert f"ID: {alias}" in text
        assert f'Need more? Reply "details" or send details {alias}.' in text
    assert f"Tags: {tags}" in text
    assert "Priority: unset" in text


def test_chat_scoped_user_id_uses_chat_id_when_user_differs() -> None:
    update = type(
        "Update",
        (),
        {
            "effective_user": type("User", (), {"id": 111})(),
            "effective_chat": type("Chat", (), {"id": -222})(),
        },
    )()

    assert _chat_scoped_user_id(update) == "telegram:-222"


@pytest.mark.asyncio
async def test_application_ignores_disallowed_chat_before_handling_text() -> None:
    handler = RecordingTelegramHandler()
    application = build_application(handler, "token", allowed_chat_id="123")
    update, message = _text_update(chat_id=999)

    await _message_callback(application)(update, None)

    assert handler.calls == []
    assert message.replies == []


@pytest.mark.asyncio
async def test_application_processes_allowed_chat() -> None:
    handler = RecordingTelegramHandler()
    application = build_application(handler, "token", allowed_chat_id="123")
    update, message = _text_update(chat_id=123)

    await _message_callback(application)(update, None)

    assert handler.calls == [
        {"user_id": "telegram:123", "text": "hello", "reply_to_text": None},
    ]
    assert message.replies == ["handled"]


@pytest.mark.asyncio
async def test_application_replies_with_html_parse_mode() -> None:
    handler = RecordingTelegramHandler()
    application = build_application(handler, "token", allowed_chat_id="123")
    update, message = _text_update(chat_id=123, text="hello")

    await _message_callback(application)(update, None)

    assert message.replies == ["handled"]
    assert message.reply_kwargs["parse_mode"] == "HTML"
    assert message.reply_kwargs["disable_web_page_preview"] is True


@pytest.mark.asyncio
async def test_application_passes_reply_to_message_text() -> None:
    handler = RecordingTelegramHandler()
    application = build_application(handler, "token", allowed_chat_id="123")
    update, _message = _text_update(
        chat_id=123,
        text="details",
        reply_to_text="Original saved text",
    )

    await _message_callback(application)(update, None)

    assert handler.calls == [
        {
            "user_id": "telegram:123",
            "text": "details",
            "reply_to_text": "Original saved text",
        },
    ]


@pytest.mark.asyncio
async def test_application_processes_any_chat_without_allowed_chat_config() -> None:
    handler = RecordingTelegramHandler()
    application = build_application(handler, "token")
    update, message = _text_update(chat_id=999)

    await _message_callback(application)(update, None)

    assert handler.calls == [
        {"user_id": "telegram:999", "text": "hello", "reply_to_text": None},
    ]
    assert message.replies == ["handled"]


@pytest.mark.asyncio
async def test_handler_saves_plain_link() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="https://example.com/rag",
        reply=replies.append,
    )

    _assert_compact_card(replies[0], title="Saved Title")
    assert "Saved: Saved Title" not in replies[0]


@pytest.mark.asyncio
async def test_handler_note_save_uses_split_enrichment_for_split_knowledge() -> None:
    replies = []
    knowledge = RecordingSplitKnowledge()
    handler = TelegramMessageHandler(
        knowledge=knowledge,
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="save https://example.com/rag note: manual text",
        reply=replies.append,
    )

    assert knowledge.save_link_calls == []
    assert knowledge.create_link_calls == [
        {
            "user_id": "telegram:123",
            "url": "https://example.com/rag",
            "note": "manual text",
            "priority": Priority.UNSET,
        },
    ]
    assert knowledge.enrich_saved_item_calls == [
        {"user_id": "telegram:123", "item_id": "7f3a9b8c1234"},
    ]
    _assert_compact_card(replies[0], title="Finished Brief", alias="kb_7f3a")


@pytest.mark.asyncio
async def test_handler_replies_pending_then_follow_up_for_slow_save() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=SlowKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
        ai_router=FakeAIRouter(),
        ai_sync_wait_seconds=0,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="https://example.com/rag",
        reply=replies.append,
    )
    await asyncio.sleep(0.02)

    assert replies[0] == "Saved: https://example.com/rag\nID: kb_7f3a\nPreparing learning brief..."
    _assert_compact_card(replies[1], title="Finished Brief", alias="kb_7f3a")


@pytest.mark.asyncio
async def test_handler_sends_retry_message_when_fast_enrichment_raises() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FastFailingEnrichmentKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
        ai_router=FakeAIRouter(),
        ai_sync_wait_seconds=1,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="https://example.com/rag",
        reply=replies.append,
    )

    assert replies == [
        "Saved with basic enrichment. AI brief is pending retry.\nID: kb_7f3a",
    ]


@pytest.mark.asyncio
async def test_handler_follow_up_prompts_for_note_when_slow_enrichment_needs_text() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=SlowNeedsTextKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
        ai_router=FakeAIRouter(),
        ai_sync_wait_seconds=0,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="https://example.com/rag",
        reply=replies.append,
    )
    await asyncio.sleep(0.02)

    assert replies[0] == "Saved: https://example.com/rag\nID: kb_7f3a\nPreparing learning brief..."
    _assert_compact_card(replies[1], title="https://example.com/rag", alias="kb_7f3a")
    assert replies[2] == (
        "I saved the link, but could not extract text from: https://example.com/rag\n"
        "Send the useful text and I will use it as saved content: "
        "save https://example.com/rag note: &lt;text&gt;"
    )


@pytest.mark.asyncio
async def test_handler_prompts_for_note_when_fast_split_enrichment_needs_text() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FastNeedsTextKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
        ai_router=FakeAIRouter(),
        ai_sync_wait_seconds=1,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="https://example.com/rag",
        reply=replies.append,
    )

    assert len(replies) == 2
    _assert_compact_card(replies[0], title="https://example.com/rag", alias="kb_7f3a")
    assert replies[1] == (
        "I saved the link, but could not extract text from: https://example.com/rag\n"
        "Send the useful text and I will use it as saved content: "
        "save https://example.com/rag note: &lt;text&gt;"
    )


@pytest.mark.asyncio
async def test_handler_follow_up_sends_retry_message_when_slow_enrichment_fails() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=SlowRetryPendingKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
        ai_router=FakeAIRouter(),
        ai_sync_wait_seconds=0,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="https://example.com/rag",
        reply=replies.append,
    )
    await asyncio.sleep(0.02)

    assert replies == [
        "Saved: https://example.com/rag\nID: kb_7f3a\nPreparing learning brief...",
        "Saved with basic enrichment. AI brief is pending retry.\nID: kb_7f3a",
    ]


@pytest.mark.asyncio
async def test_handler_prompts_for_note_when_saved_link_needs_text() -> None:
    replies = []
    knowledge = FakeKnowledge()
    needs_text_item = replace(_saved_item(), status=Status.NEEDS_TEXT, title="https://example.com/rag")
    knowledge.save_link = lambda **_: needs_text_item
    handler = TelegramMessageHandler(
        knowledge=knowledge,
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="https://example.com/rag",
        reply=replies.append,
    )

    alias = f"kb_{needs_text_item.id[:4]}"
    assert len(replies) == 2
    _assert_compact_card(replies[0], title="https://example.com/rag", alias=alias)
    assert replies[1] == (
        "I saved the link, but could not extract text from: https://example.com/rag\n"
        "Send the useful text and I will use it as saved content: "
        "save https://example.com/rag note: &lt;text&gt;"
    )


@pytest.mark.asyncio
async def test_handler_answers_plain_question() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="what did I save about rag?",
        reply=replies.append,
    )

    assert replies == ["From your knowledge base\nAnswer"]


@pytest.mark.asyncio
async def test_handler_sends_details_by_alias() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="details kb_7f3a",
        reply=replies.append,
    )

    assert "<b>Details</b>" in replies[0]
    assert "Detailed Item" in replies[0]


@pytest.mark.asyncio
async def test_handler_sends_details_from_replied_message_id() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="more",
        reply=replies.append,
        reply_to_text="<b>Saved Item</b>\nID: kb_7f3a",
    )

    assert "<b>Details</b>" in replies[0]
    assert "Detailed Item" in replies[0]


@pytest.mark.asyncio
async def test_handler_plain_details_uses_latest_item() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="details",
        reply=replies.append,
    )

    assert "Latest Item" in replies[0]


@pytest.mark.asyncio
async def test_handler_details_reports_missing_item() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="details missing",
        reply=replies.append,
    )

    assert replies == ["I could not find that saved item."]


@pytest.mark.asyncio
async def test_handler_sends_daily_digest() -> None:
    replies = []
    digest = FakeDigest()
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=digest,
        archive_review_service=None,
    )

    await handler.handle_text(user_id="telegram:123", text="digest today", reply=replies.append)

    assert digest.calls == [("daily", "telegram:123")]
    assert replies == ["Daily tiny nudge"]


@pytest.mark.asyncio
async def test_handler_sends_weekly_digest() -> None:
    replies = []
    digest = FakeDigest()
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=digest,
        archive_review_service=None,
    )

    await handler.handle_text(user_id="telegram:123", text="digest week", reply=replies.append)

    assert digest.calls == [("weekly", "telegram:123")]
    assert replies == ["Weekly synthesis"]


@pytest.mark.asyncio
async def test_handler_reviews_archive_recommendations() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=FakeArchiveReview(),
    )

    await handler.handle_text(user_id="telegram:123", text="review archive", reply=replies.append)

    assert replies == ["Archive recommendations\n- kb_7f3a: Old Link (old_low_priority)"]


@pytest.mark.asyncio
async def test_handler_archives_item() -> None:
    replies = []
    knowledge = FakeKnowledge()

    async def archive_unsafe_title(*, user_id, item_id):
        knowledge.archived = (user_id, item_id)
        return replace(_saved_item(title="Archived <Title> & More"), id=item_id, archived=True)

    knowledge.archive_item = archive_unsafe_title
    handler = TelegramMessageHandler(
        knowledge=knowledge,
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(user_id="telegram:123", text="archive item123", reply=replies.append)

    assert knowledge.archived == ("telegram:123", "item123")
    assert replies == ["Archived: Archived &lt;Title&gt; &amp; More"]


@pytest.mark.asyncio
async def test_handler_prompts_for_missing_archive_id_with_html_safe_placeholder() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(user_id="telegram:123", text="archive", reply=replies.append)

    assert replies == ["Tell me which item to archive, like: archive &lt;item_id&gt;."]


@pytest.mark.asyncio
async def test_handler_replies_when_archive_item_is_missing() -> None:
    replies = []
    knowledge = FakeKnowledge()

    async def archive_missing_item(*, user_id, item_id):
        knowledge.archived = (user_id, item_id)
        raise ValueError("saved item not found")

    knowledge.archive_item = archive_missing_item
    handler = TelegramMessageHandler(
        knowledge=knowledge,
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(user_id="telegram:123", text="archive stale-id", reply=replies.append)

    assert knowledge.archived == ("telegram:123", "stale-id")
    assert replies == ["I could not find that saved item."]


@pytest.mark.asyncio
async def test_handler_prompts_for_empty_message() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(user_id="telegram:123", text=" ", reply=replies.append)

    assert replies == ["Send a link to save it, or ask a question about your knowledge base."]


@pytest.mark.asyncio
async def test_handler_sends_ai_status() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
        ai_router=FakeAIRouter(),
    )

    await handler.handle_text(user_id="telegram:123", text="ai status", reply=replies.append)

    assert "AI status" in replies[0]
    assert "gemini:lite -> heuristic:heuristic" in replies[0]
    assert "Selected: gemini:lite" in replies[0]
    assert "Gemini model: lite" in replies[0]
    assert "Ollama: http://localhost:11434 (qwen3:8b)" in replies[0]


@pytest.mark.asyncio
async def test_handler_ai_status_uses_persisted_error_when_router_has_no_error() -> None:
    replies = []
    knowledge = FakeKnowledge()
    knowledge.repository = type(
        "Repository",
        (),
        {
            "count_ai_retry_pending": lambda _: 2,
            "last_ai_error": lambda _: "gemini failed after retry",
        },
    )()
    handler = TelegramMessageHandler(
        knowledge=knowledge,
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
        ai_router=FakeAIRouter(),
    )

    await handler.handle_text(user_id="telegram:123", text="ai status", reply=replies.append)

    assert "Pending retries: 2" in replies[0]
    assert "Selected: gemini:lite" in replies[0]
    assert "Gemini model: lite" in replies[0]
    assert "Ollama: http://localhost:11434 (qwen3:8b)" in replies[0]
    assert "Last error: gemini failed after retry" in replies[0]


@pytest.mark.asyncio
async def test_handler_refreshes_item_by_alias() -> None:
    replies = []
    knowledge = FakeKnowledge()
    brief = LearningBrief(
        brief_version=1,
        provider="gemini",
        model="gemini-2.5-flash-lite",
        generated_at=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
        title="Learning Brief",
        topic="ai",
        tags=["brief"],
        summary="Summary.",
        key_takeaways=["Takeaway."],
        why_it_matters="Useful.",
        estimated_time_minutes=10,
        suggested_next_action="Review it.",
    )
    knowledge.refresh_item = lambda **_: replace(
        _saved_item(title="Learning Brief"),
        id="7f3a9b8c1234",
        learning_brief=brief,
    )
    handler = TelegramMessageHandler(
        knowledge=knowledge,
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
        ai_router=FakeAIRouter(),
    )

    await handler.handle_text(user_id="telegram:123", text="refresh kb_7f3a", reply=replies.append)

    _assert_compact_card(
        replies[0],
        title="Learning Brief",
        alias="kb_7f3a",
        tags="brief",
    )
    assert "Summary." in replies[0]


@pytest.mark.asyncio
async def test_handler_refresh_reports_retry_pending_with_alias() -> None:
    replies = []
    knowledge = FakeKnowledge()
    knowledge.refresh_item = lambda **_: replace(
        _saved_item(title="Learning Brief"),
        id="7f3a9b8c1234",
        status=Status.FAILED_ENRICHMENT,
        ai_status=AIStatus.RETRY_PENDING,
    )
    handler = TelegramMessageHandler(
        knowledge=knowledge,
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
        ai_router=FakeAIRouter(),
    )

    await handler.handle_text(user_id="telegram:123", text="refresh kb_7f3a", reply=replies.append)

    assert replies == [
        "Saved with basic enrichment. AI brief is pending retry.\nID: kb_7f3a",
    ]


@pytest.mark.asyncio
async def test_handler_selects_model() -> None:
    replies = []
    router = FakeAIRouter()
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
        ai_router=router,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="model gemini:lite",
        reply=replies.append,
    )

    assert router.selected == "gemini:lite"
    assert replies == ["Model selected: gemini:lite"]


@pytest.mark.asyncio
async def test_handler_escapes_selected_model_reply() -> None:
    replies = []
    router = FakeAIRouter()
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
        ai_router=router,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="model gemini:<lite>&",
        reply=replies.append,
    )

    assert router.selected == "gemini:<lite>&"
    assert replies == ["Model selected: gemini:&lt;lite&gt;&amp;"]


@pytest.mark.asyncio
async def test_handler_prompts_for_empty_model_command() -> None:
    replies = []
    router = FakeAIRouter()
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
        ai_router=router,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="model",
        reply=replies.append,
    )

    assert router.selected is None
    assert replies == ["Tell me which model to use, like: model gemini:lite."]
