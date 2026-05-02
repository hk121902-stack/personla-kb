from datetime import UTC, datetime

from kb_agent.core.models import Priority, SavedItem, SourceType, Status


def test_saved_item_defaults_to_active_processing_item() -> None:
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://youtu.be/demo",
        source_type=SourceType.YOUTUBE,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )

    assert item.id
    assert item.priority is Priority.UNSET
    assert item.status is Status.PROCESSING
    assert item.archived is False
    assert item.created_at == datetime(2026, 5, 3, 9, 0, tzinfo=UTC)


def test_saved_item_can_be_archived() -> None:
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/post",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )

    archived = item.archive(datetime(2026, 5, 4, 9, 0, tzinfo=UTC))

    assert archived.archived is True
    assert archived.archived_at == datetime(2026, 5, 4, 9, 0, tzinfo=UTC)
    assert archived.status is Status.PROCESSING
