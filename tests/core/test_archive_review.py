from dataclasses import replace
from datetime import UTC, datetime, timedelta

from kb_agent.core.archive_review import ArchiveReviewService
from kb_agent.core.models import Priority, SavedItem, SourceType, Status
from kb_agent.storage.sqlite import SQLiteItemRepository


def saved(title: str, text: str, priority: Priority, days_old: int) -> SavedItem:
    created = datetime(2026, 5, 3, 9, 0, tzinfo=UTC) - timedelta(days=days_old)
    return replace(
        SavedItem.new(
            user_id="telegram:123",
            url=f"https://example.com/{title}",
            source_type=SourceType.WEB,
            now=created,
        ),
        title=title,
        extracted_text=text,
        priority=priority,
        status=Status.READY,
    )


def test_recommends_old_low_priority_items(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    old_low = saved("old", "old low priority", Priority.LOW, 61)
    recent_low = saved("recent", "recent low priority", Priority.LOW, 10)
    repo.save(old_low)
    repo.save(recent_low)

    recommendations = ArchiveReviewService(repo).recommend(
        user_id="telegram:123",
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )

    assert [rec.item.id for rec in recommendations] == [old_low.id]
    assert recommendations[0].reason == "old_low_priority"


def test_recommends_older_duplicate_items(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    older = saved(
        "older rag",
        "retrieval augmented generation evaluation guide",
        Priority.UNSET,
        20,
    )
    newer = saved(
        "newer rag",
        "retrieval augmented generation evaluation guide",
        Priority.HIGH,
        1,
    )
    repo.save(older)
    repo.save(newer)

    recommendations = ArchiveReviewService(repo).recommend(
        user_id="telegram:123",
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )

    assert recommendations[0].item.id == older.id
    assert recommendations[0].reason == "duplicate_overlap"
