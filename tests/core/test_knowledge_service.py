from datetime import UTC, datetime

import pytest

from kb_agent.ai.providers import HeuristicAIProvider
from kb_agent.core.models import ExtractedContent, Priority, SavedItem, Status
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
