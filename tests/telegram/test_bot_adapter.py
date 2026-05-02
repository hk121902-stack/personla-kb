from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from kb_agent.core.archive_review import ArchiveRecommendation
from kb_agent.core.models import SavedItem, SourceType, Status
from kb_agent.telegram.bot import TelegramMessageHandler


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

    async def save_link(self, *, user_id, url, note="", priority=None):
        return _saved_item()

    async def archive_item(self, *, user_id, item_id):
        self.archived = (user_id, item_id)
        return replace(_saved_item(title="Archived Title"), id=item_id, archived=True)


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
                item=replace(_saved_item(title="Old Link"), id="item123"),
                reason="old_low_priority",
            ),
        ]


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

    assert "Saved: Saved Title" in replies[0]


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

    assert replies == ["Archive recommendations\n- item123: Old Link (old_low_priority)"]


@pytest.mark.asyncio
async def test_handler_archives_item() -> None:
    replies = []
    knowledge = FakeKnowledge()
    handler = TelegramMessageHandler(
        knowledge=knowledge,
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(user_id="telegram:123", text="archive item123", reply=replies.append)

    assert knowledge.archived == ("telegram:123", "item123")
    assert replies == ["Archived: Archived Title"]


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
