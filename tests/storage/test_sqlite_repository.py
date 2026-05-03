from dataclasses import replace
from datetime import UTC, datetime

from kb_agent.core.models import AIStatus, LearningBrief, Priority, SavedItem, SourceType
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
    active = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/active",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        ),
        id="a-active",
    )
    archived = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/archive",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        ).archive(datetime(2026, 5, 4, 9, 0, tzinfo=UTC)),
        id="b-archived",
    )

    repo.save(active)
    repo.save(archived)

    assert repo.list_by_user("telegram:123") == [active]
    assert repo.list_by_user("telegram:123", include_archived=True) == [active, archived]
    assert repo.list_by_user("telegram:123", True) == [active, archived]


def test_list_by_user_orders_same_created_at_by_id(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    now = datetime(2026, 5, 3, 9, 0, tzinfo=UTC)
    first = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/first",
            source_type=SourceType.WEB,
            now=now,
        ),
        id="item-a",
    )
    second = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/second",
            source_type=SourceType.WEB,
            now=now,
        ),
        id="item-b",
    )

    repo.save(second)
    repo.save(first)

    assert repo.list_by_user("telegram:123") == [first, second]


def test_repository_round_trips_ai_fields(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    now = datetime(2026, 5, 3, 9, 0, tzinfo=UTC)
    brief = LearningBrief(
        brief_version=1,
        provider="gemini",
        model="gemini-2.5-flash-lite",
        generated_at=now,
        title="AI Brief",
        topic="retrieval",
        tags=["rag"],
        summary="A structured summary.",
        key_takeaways=["Use structured output."],
        why_it_matters="It makes review easier.",
        estimated_time_minutes=15,
        suggested_next_action="Refresh one saved item.",
    )
    item = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/brief",
            source_type=SourceType.WEB,
            now=now,
        ),
        learning_brief=brief,
        ai_status=AIStatus.READY,
        ai_attempt_count=2,
        ai_last_attempt_at=now,
        ai_last_error="rate limited",
    )

    repo.save(item)

    assert repo.get(item.id) == item


def test_repository_resolves_short_aliases(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    item = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/alias",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        ),
        id="7f3a9b8c1234",
    )
    repo.save(item)

    assert repo.resolve_item_ref("telegram:123", "kb_7f3a") == item.id
    assert repo.resolve_item_ref("telegram:999", "kb_7f3a") is None


def test_repository_lists_ai_retry_candidates(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    now = datetime(2026, 5, 3, 9, 0, tzinfo=UTC)
    retryable = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/retry",
            source_type=SourceType.WEB,
            now=now,
        ),
        id="retry",
        ai_status=AIStatus.RETRY_PENDING,
        ai_attempt_count=1,
    )
    archived = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/archive",
            source_type=SourceType.WEB,
            now=now,
        ).archive(now),
        id="archived",
        ai_status=AIStatus.RETRY_PENDING,
    )
    ready = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/ready",
            source_type=SourceType.WEB,
            now=now,
        ),
        id="ready",
        ai_status=AIStatus.READY,
    )
    maxed_attempts = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/maxed",
            source_type=SourceType.WEB,
            now=now,
        ),
        id="maxed",
        ai_status=AIStatus.RETRY_PENDING,
        ai_attempt_count=3,
    )
    repo.save(ready)
    repo.save(archived)
    repo.save(maxed_attempts)
    repo.save(retryable)

    assert repo.list_ai_retry_candidates(limit=10, max_attempts=3) == [retryable]
    assert repo.count_ai_retry_pending() == 2
