from dataclasses import replace
from datetime import UTC, datetime

import pytest

from kb_agent.ai.providers import HeuristicAIProvider
from kb_agent.core.models import (
    AIStatus,
    ExtractedContent,
    LearningBrief,
    Priority,
    SavedItem,
    Status,
)
from kb_agent.core.service import KnowledgeService, SystemClock
from kb_agent.extraction.extractors import StaticExtractor
from kb_agent.storage.sqlite import SQLiteItemRepository


class FixedClock(SystemClock):
    def now(self):
        return datetime(2026, 5, 3, 9, 0, tzinfo=UTC)


class ThrowingExtractor:
    async def extract(self, url: str) -> ExtractedContent | None:
        raise RuntimeError("extractor unavailable")


class ThrowingAIProvider(HeuristicAIProvider):
    async def enrich(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> SavedItem:
        raise RuntimeError("ai unavailable")


class RecordingAIProvider(HeuristicAIProvider):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def enrich(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> SavedItem:
        self.calls.append(item.id)
        return await super().enrich(item, extracted)


class ExtractedRecordingAIProvider(HeuristicAIProvider):
    def __init__(self) -> None:
        self.extracted: list[ExtractedContent | None] = []

    async def enrich(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> SavedItem:
        self.extracted.append(extracted)
        return await super().enrich(item, extracted)


class ReadyOnMissingTextAIProvider(HeuristicAIProvider):
    def __init__(self) -> None:
        self.calls: list[ExtractedContent | None] = []

    async def enrich(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> SavedItem:
        self.calls.append(extracted)
        if extracted is None:
            return replace(
                item,
                title="Provider ignored missing text",
                extracted_text="",
                summary="Provider marked missing content ready.",
                status=Status.READY,
                ai_status=AIStatus.READY,
            )
        return await super().enrich(item, extracted)


class RetryCountingAIProvider(HeuristicAIProvider):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def enrich(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> SavedItem:
        self.calls.append(item.id)
        enriched = _brief_item(item, now=FixedClock().now())
        if item.url.endswith("/router"):
            return replace(enriched, ai_attempt_count=item.ai_attempt_count + 1)
        return enriched


def _brief_item(item: SavedItem, *, now: datetime) -> SavedItem:
    brief = LearningBrief(
        brief_version=1,
        provider="gemini",
        model="gemini-2.5-flash-lite",
        generated_at=now,
        title="Refreshed Brief",
        topic="ai",
        tags=["refresh"],
        summary="Refreshed summary.",
        key_takeaways=["Refresh works."],
        why_it_matters="Model prompts improve.",
        estimated_time_minutes=5,
        suggested_next_action="Review the result.",
    )
    return replace(
        item,
        title=brief.title,
        topic=brief.topic,
        tags=list(brief.tags),
        summary=brief.summary,
        learning_brief=brief,
        ai_status=AIStatus.READY,
        status=Status.READY,
        updated_at=now,
    )


class BriefAIProvider(HeuristicAIProvider):
    async def enrich(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> SavedItem:
        return _brief_item(item, now=FixedClock().now())


@pytest.mark.asyncio
async def test_create_link_saves_without_running_extraction_or_ai(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    ai = RecordingAIProvider()
    service = KnowledgeService(
        repository=repo,
        extractor=ThrowingExtractor(),
        ai_provider=ai,
        clock=FixedClock(),
    )

    item = service.create_link(
        user_id="telegram:123",
        url="https://example.com/immediate",
        note="capture now",
        priority=Priority.HIGH,
    )

    assert item.status is Status.PROCESSING
    assert item.ai_status is AIStatus.PENDING
    assert item.user_note == "capture now"
    assert item.priority is Priority.HIGH
    assert ai.calls == []
    assert repo.get(item.id) == item


@pytest.mark.asyncio
async def test_create_link_with_note_completes_existing_needs_text_item(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(None),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )
    blocked = await service.save_link(
        user_id="telegram:123",
        url="https://linkedin.com/posts/private",
    )

    captured = service.create_link(
        user_id="telegram:123",
        url="https://linkedin.com/posts/private",
        note="Manual text that should enrich the original item.",
        priority=Priority.HIGH,
    )

    assert captured.id == blocked.id
    assert captured.status is Status.PROCESSING
    assert captured.ai_status is AIStatus.PENDING
    assert captured.user_note == "Manual text that should enrich the original item."
    assert captured.priority is Priority.HIGH
    assert len(repo.list_by_user("telegram:123")) == 1


@pytest.mark.asyncio
async def test_enrich_saved_item_updates_existing_item(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(ExtractedContent(title="Source", text="Body", metadata={})),
        ai_provider=BriefAIProvider(),
        clock=FixedClock(),
    )
    item = service.create_link(user_id="telegram:123", url="https://example.com/source")

    enriched = await service.enrich_saved_item(user_id="telegram:123", item_id=item.id)

    assert enriched.id == item.id
    assert enriched.ai_status is AIStatus.READY
    assert enriched.learning_brief.title == "Refreshed Brief"
    assert repo.get(item.id) == enriched


@pytest.mark.asyncio
async def test_enrich_saved_item_passes_extracted_content_to_ai_provider(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    extracted = ExtractedContent(
        title="Extractor Title",
        text="Extractor text should be sent to the provider.",
        metadata={"source": "extractor"},
    )
    ai = ExtractedRecordingAIProvider()
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(extracted),
        ai_provider=ai,
        clock=FixedClock(),
    )
    item = service.create_link(user_id="telegram:123", url="https://example.com/source")

    enriched = await service.enrich_saved_item(user_id="telegram:123", item_id=item.id)

    assert ai.extracted == [extracted]
    assert enriched.title == "Extractor Title"
    assert enriched.extracted_text == "Extractor text should be sent to the provider."


@pytest.mark.asyncio
async def test_enrich_saved_item_without_text_persists_needs_text_without_ai(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    ai = ReadyOnMissingTextAIProvider()
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(None),
        ai_provider=ai,
        clock=FixedClock(),
    )
    item = service.create_link(user_id="telegram:123", url="https://linkedin.com/posts/private")

    enriched = await service.enrich_saved_item(user_id="telegram:123", item_id=item.id)

    assert ai.calls == []
    assert enriched.status is Status.NEEDS_TEXT
    assert enriched.ai_status is AIStatus.FAILED
    assert enriched.title == "https://linkedin.com/posts/private"
    assert repo.get(item.id) == enriched


@pytest.mark.asyncio
async def test_refresh_item_accepts_alias(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(ExtractedContent(title="Source", text="Body", metadata={})),
        ai_provider=BriefAIProvider(),
        clock=FixedClock(),
    )
    item = replace(
        service.create_link(user_id="telegram:123", url="https://example.com/source"),
        id="7f3a9b8c1234",
    )
    repo.save(item)

    refreshed = await service.refresh_item(user_id="telegram:123", item_ref="kb_7f3a")

    assert refreshed.id == "7f3a9b8c1234"
    assert refreshed.learning_brief.title == "Refreshed Brief"


@pytest.mark.asyncio
async def test_retry_pending_ai_skips_archived_items_and_caps_attempts(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    ai = RetryCountingAIProvider()
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(ExtractedContent(title="Source", text="Body", metadata={})),
        ai_provider=ai,
        clock=FixedClock(),
    )
    retryable = replace(
        service.create_link(user_id="telegram:123", url="https://example.com/retry"),
        ai_status=AIStatus.RETRY_PENDING,
        ai_attempt_count=1,
    )
    maxed = replace(
        service.create_link(user_id="telegram:123", url="https://example.com/maxed"),
        ai_status=AIStatus.RETRY_PENDING,
        ai_attempt_count=3,
    )
    archived = replace(
        service.create_link(user_id="telegram:123", url="https://example.com/archive").archive(
            FixedClock().now(),
        ),
        ai_status=AIStatus.RETRY_PENDING,
    )
    repo.save(retryable)
    repo.save(maxed)
    repo.save(archived)

    results = await service.retry_pending_ai(limit=10, max_attempts=3)

    assert [item.id for item in results] == [retryable.id]
    assert ai.calls == [retryable.id]
    assert repo.get(retryable.id).ai_status is AIStatus.READY
    assert repo.get(retryable.id).ai_attempt_count == 2
    assert repo.get(maxed.id) == maxed
    assert repo.get(archived.id).ai_status is AIStatus.RETRY_PENDING


@pytest.mark.asyncio
async def test_retry_pending_ai_does_not_double_count_incrementing_provider(
    tmp_path,
) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(ExtractedContent(title="Source", text="Body", metadata={})),
        ai_provider=RetryCountingAIProvider(),
        clock=FixedClock(),
    )
    retryable = replace(
        service.create_link(user_id="telegram:123", url="https://example.com/router"),
        ai_status=AIStatus.RETRY_PENDING,
        ai_attempt_count=1,
    )
    repo.save(retryable)

    results = await service.retry_pending_ai(limit=10, max_attempts=3)

    assert [item.id for item in results] == [retryable.id]
    assert results[0].ai_attempt_count == 2
    assert repo.get(retryable.id).ai_attempt_count == 2


@pytest.mark.asyncio
async def test_retry_pending_ai_skips_needs_text_items_without_manual_content(
    tmp_path,
) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    ai = ReadyOnMissingTextAIProvider()
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(None),
        ai_provider=ai,
        clock=FixedClock(),
    )
    blocked = await service.save_link(
        user_id="telegram:123",
        url="https://linkedin.com/posts/private",
    )

    results = await service.retry_pending_ai(limit=10, max_attempts=3)

    persisted = repo.get(blocked.id)
    assert results == []
    assert ai.calls == []
    assert persisted is not None
    assert persisted.status is Status.NEEDS_TEXT
    assert persisted.ai_status is AIStatus.FAILED
    assert persisted.ai_attempt_count == 0
    assert persisted.ai_last_attempt_at is None


@pytest.mark.asyncio
async def test_refresh_item_preserves_existing_extraction_when_extractor_returns_blank(
    tmp_path,
) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(ExtractedContent(title="", text="", metadata={})),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )
    existing = replace(
        service.create_link(user_id="telegram:123", url="https://example.com/source"),
        title="Existing Source",
        extracted_text="Existing useful source text for retrieval.",
        source_metadata={"status_code": "200", "content_type": "text/html"},
        status=Status.READY,
        ai_status=AIStatus.READY,
    )
    repo.save(existing)

    refreshed = await service.refresh_item(user_id="telegram:123", item_ref=existing.id)

    assert refreshed.extracted_text == "Existing useful source text for retrieval."
    assert refreshed.source_metadata == {
        "status_code": "200",
        "content_type": "text/html",
    }
    assert refreshed.title == "Existing Source"
    assert repo.get(existing.id) == refreshed


@pytest.mark.asyncio
async def test_save_link_with_note_and_priority_enriches_item(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(
            ExtractedContent(
                title="Vector DB Notes",
                text="Vector search helps semantic retrieval.",
                metadata={},
            )
        ),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )

    item = await service.save_link(
        user_id="telegram:123",
        url="https://example.com/vector",
        note="learn for personal search",
        priority=Priority.HIGH,
    )

    assert item.status is Status.READY
    assert item.priority is Priority.HIGH
    assert item.user_note == "learn for personal search"
    assert repo.get(item.id) == item


@pytest.mark.asyncio
async def test_save_link_survives_extraction_failure(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(None),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )

    item = await service.save_link(
        user_id="telegram:123",
        url="https://linkedin.com/posts/private",
    )

    assert item.status is Status.NEEDS_TEXT
    assert repo.get(item.id) == item


@pytest.mark.asyncio
async def test_save_link_uses_note_as_manual_content_when_extraction_returns_none(
    tmp_path,
) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(None),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )

    item = await service.save_link(
        user_id="telegram:123",
        url="https://linkedin.com/posts/private",
        note="Example Domain explains private fallback retrieval.",
    )

    assert item.status is Status.READY
    assert item.title == "https://linkedin.com/posts/private"
    assert item.user_note == "Example Domain explains private fallback retrieval."
    assert item.extracted_text == "Example Domain explains private fallback retrieval."
    assert item.summary == "Example Domain explains private fallback retrieval."
    assert "example" in item.tags
    assert repo.get(item.id) == item


@pytest.mark.asyncio
async def test_save_link_persists_needs_text_when_extractor_raises(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=ThrowingExtractor(),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )

    item = await service.save_link(
        user_id="telegram:123",
        url="https://example.com/private",
    )

    assert item.status is Status.NEEDS_TEXT
    assert item.status is not Status.PROCESSING
    assert item.updated_at == FixedClock().now()
    assert repo.get(item.id) == item


@pytest.mark.asyncio
async def test_save_link_does_not_call_ai_when_extraction_fails_without_text(
    tmp_path,
) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    ai = ReadyOnMissingTextAIProvider()
    service = KnowledgeService(
        repository=repo,
        extractor=ThrowingExtractor(),
        ai_provider=ai,
        clock=FixedClock(),
    )

    item = await service.save_link(
        user_id="telegram:123",
        url="https://example.com/private",
    )

    assert item.status is Status.NEEDS_TEXT
    assert ai.calls == []
    assert repo.get(item.id) == item


@pytest.mark.asyncio
async def test_save_link_uses_note_as_manual_content_when_extractor_raises(
    tmp_path,
) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=ThrowingExtractor(),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )

    item = await service.save_link(
        user_id="telegram:123",
        url="https://example.com/private",
        note="Example Domain manual source content for digest search.",
    )

    assert item.status is Status.READY
    assert item.title == "https://example.com/private"
    assert item.user_note == "Example Domain manual source content for digest search."
    assert item.extracted_text == "Example Domain manual source content for digest search."
    assert item.summary == "Example Domain manual source content for digest search."
    assert "manual" in item.tags
    assert repo.get(item.id) == item


@pytest.mark.asyncio
async def test_save_link_note_completes_existing_needs_text_item_without_duplicate(
    tmp_path,
) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=ThrowingExtractor(),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )
    pending = await service.save_link(
        user_id="telegram:123",
        url="https://example.com/private",
    )

    completed = await service.save_link(
        user_id="telegram:123",
        url="https://example.com/private",
        note="Manual content to complete the blocked private link.",
    )

    assert completed.id == pending.id
    assert completed.status is Status.READY
    assert completed.user_note == "Manual content to complete the blocked private link."
    assert completed.extracted_text == "Manual content to complete the blocked private link."
    assert repo.list_by_user("telegram:123") == [completed]


@pytest.mark.asyncio
async def test_save_link_persists_failed_enrichment_when_ai_provider_raises(
    tmp_path,
) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    extracted = ExtractedContent(
        title=" Provider Failure ",
        text=" The provider should not strand processing items. ",
        metadata={"status_code": "200"},
    )
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(extracted),
        ai_provider=ThrowingAIProvider(),
        clock=FixedClock(),
    )

    item = await service.save_link(
        user_id="telegram:123",
        url="https://example.com/provider",
        note="keep extracted details",
        priority=Priority.HIGH,
    )

    assert item.status is Status.FAILED_ENRICHMENT
    assert item.status is not Status.PROCESSING
    assert item.title == extracted.title
    assert item.extracted_text == extracted.text
    assert item.source_metadata == extracted.metadata
    assert item.user_note == "keep extracted details"
    assert item.priority is Priority.HIGH
    assert item.updated_at == FixedClock().now()
    assert repo.get(item.id) == item


@pytest.mark.asyncio
async def test_archive_excludes_item_from_active_list(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(None),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )
    item = await service.save_link(user_id="telegram:123", url="https://example.com/old")

    archived = service.archive_item(user_id="telegram:123", item_id=item.id)

    assert archived.archived is True
    assert repo.list_by_user("telegram:123") == []


@pytest.mark.asyncio
async def test_archive_item_accepts_alias(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(None),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )
    item = replace(
        await service.save_link(user_id="telegram:123", url="https://example.com/old"),
        id="7f3a9b8c1234",
    )
    repo.save(item)

    archived = service.archive_item(user_id="telegram:123", item_id="kb_7f3a")

    assert archived.id == "7f3a9b8c1234"
    assert archived.archived is True
    assert repo.get("7f3a9b8c1234") == archived


@pytest.mark.asyncio
async def test_archive_rejects_missing_or_wrong_user_items(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(None),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )
    item = await service.save_link(
        user_id="telegram:123",
        url="https://example.com/archive",
    )

    with pytest.raises(ValueError, match="Saved item not found"):
        service.archive_item(user_id="telegram:999", item_id=item.id)

    with pytest.raises(ValueError, match="Saved item not found"):
        service.archive_item(user_id="telegram:123", item_id="missing")


@pytest.mark.asyncio
async def test_add_note_updates_and_persists_item(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(None),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )
    item = await service.save_link(user_id="telegram:123", url="https://example.com/note")

    updated = service.add_note(
        user_id="telegram:123",
        item_id=item.id,
        note="review before weekly planning",
    )

    assert updated.user_note == "review before weekly planning"
    assert updated.updated_at == FixedClock().now()
    assert repo.get(item.id) == updated


@pytest.mark.asyncio
async def test_add_note_accepts_alias(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(None),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )
    item = replace(
        await service.save_link(user_id="telegram:123", url="https://example.com/note"),
        id="7f3a9b8c1234",
    )
    repo.save(item)

    updated = service.add_note(
        user_id="telegram:123",
        item_id="kb_7f3a",
        note="review before weekly planning",
    )

    assert updated.id == "7f3a9b8c1234"
    assert updated.user_note == "review before weekly planning"
    assert repo.get("7f3a9b8c1234") == updated


@pytest.mark.asyncio
async def test_set_priority_updates_and_persists_item(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(None),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )
    item = await service.save_link(
        user_id="telegram:123",
        url="https://example.com/priority",
    )

    updated = service.set_priority(
        user_id="telegram:123",
        item_id=item.id,
        priority=Priority.MEDIUM,
    )

    assert updated.priority is Priority.MEDIUM
    assert updated.updated_at == FixedClock().now()
    assert repo.get(item.id) == updated


@pytest.mark.asyncio
async def test_set_priority_accepts_alias(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(None),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )
    item = replace(
        await service.save_link(
            user_id="telegram:123",
            url="https://example.com/priority",
        ),
        id="7f3a9b8c1234",
    )
    repo.save(item)

    updated = service.set_priority(
        user_id="telegram:123",
        item_id="kb_7f3a",
        priority=Priority.MEDIUM,
    )

    assert updated.id == "7f3a9b8c1234"
    assert updated.priority is Priority.MEDIUM
    assert repo.get("7f3a9b8c1234") == updated


@pytest.mark.asyncio
async def test_add_note_rejects_missing_or_wrong_user_items(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(None),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )
    item = await service.save_link(user_id="telegram:123", url="https://example.com/note")

    with pytest.raises(ValueError, match="Saved item not found"):
        service.add_note(user_id="telegram:999", item_id=item.id, note="wrong")

    with pytest.raises(ValueError, match="Saved item not found"):
        service.add_note(user_id="telegram:123", item_id="missing", note="missing")


@pytest.mark.asyncio
async def test_set_priority_rejects_missing_or_wrong_user_items(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(None),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )
    item = await service.save_link(
        user_id="telegram:123",
        url="https://example.com/priority",
    )

    with pytest.raises(ValueError, match="Saved item not found"):
        service.set_priority(
            user_id="telegram:999",
            item_id=item.id,
            priority=Priority.LOW,
        )

    with pytest.raises(ValueError, match="Saved item not found"):
        service.set_priority(
            user_id="telegram:123",
            item_id="missing",
            priority=Priority.LOW,
        )
