from datetime import UTC, datetime

import pytest

from kb_agent.ai.providers import HeuristicAIProvider
from kb_agent.core.models import ExtractedContent, Priority, Status
from kb_agent.core.service import KnowledgeService, SystemClock
from kb_agent.extraction.extractors import StaticExtractor
from kb_agent.storage.sqlite import SQLiteItemRepository


class FixedClock(SystemClock):
    def now(self):
        return datetime(2026, 5, 3, 9, 0, tzinfo=UTC)


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
