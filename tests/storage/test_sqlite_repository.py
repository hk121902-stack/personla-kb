from datetime import UTC, datetime

from kb_agent.core.models import Priority, SavedItem, SourceType
from kb_agent.storage.sqlite import SQLiteItemRepository


def test_repository_round_trips_saved_item(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/a",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        note="read for RAG evaluation",
        priority=Priority.HIGH,
    )

    repo.save(item)
    loaded = repo.get(item.id)

    assert loaded == item


def test_list_by_user_excludes_archived_items_by_default(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    active = SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/active",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )
    archived = SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/archive",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    ).archive(datetime(2026, 5, 4, 9, 0, tzinfo=UTC))

    repo.save(active)
    repo.save(archived)

    assert repo.list_by_user("telegram:123") == [active]
    assert repo.list_by_user("telegram:123", include_archived=True) == [active, archived]
