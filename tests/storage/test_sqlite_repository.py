import sqlite3
from dataclasses import replace
from datetime import UTC, datetime

from kb_agent.core.models import AIStatus, LearningBrief, Priority, SavedItem, SourceType, Status
from kb_agent.storage.sqlite import SQLiteItemRepository


def test_repository_migrates_pre_task_2_saved_items_table(tmp_path) -> None:
    db_path = tmp_path / "kb.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE saved_items (
              id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              url TEXT NOT NULL,
              source_type TEXT NOT NULL,
              title TEXT NOT NULL,
              extracted_text TEXT NOT NULL,
              user_note TEXT NOT NULL,
              tags_json TEXT NOT NULL,
              topic TEXT NOT NULL,
              summary TEXT NOT NULL,
              priority TEXT NOT NULL,
              status TEXT NOT NULL,
              archived INTEGER NOT NULL,
              archived_at TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              last_surfaced_at TEXT,
              surface_count INTEGER NOT NULL,
              source_metadata_json TEXT NOT NULL,
              embedding_json TEXT NOT NULL
            )
            """,
        )
        connection.execute(
            """
            INSERT INTO saved_items (
              id, user_id, url, source_type, title, extracted_text, user_note,
              tags_json, topic, summary, priority, status, archived, archived_at,
              created_at, updated_at, last_surfaced_at, surface_count,
              source_metadata_json, embedding_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "old-item",
                "telegram:123",
                "https://example.com/old",
                "web",
                "Old item",
                "",
                "",
                "[]",
                "",
                "",
                "unset",
                "processing",
                0,
                None,
                "2026-05-03T09:00:00+00:00",
                "2026-05-03T09:00:00+00:00",
                None,
                0,
                "{}",
                "[]",
            ),
        )
        connection.execute(
            """
            INSERT INTO saved_items (
              id, user_id, url, source_type, title, extracted_text, user_note,
              tags_json, topic, summary, priority, status, archived, archived_at,
              created_at, updated_at, last_surfaced_at, surface_count,
              source_metadata_json, embedding_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "blocked-item",
                "telegram:123",
                "https://example.com/blocked",
                "web",
                "Blocked item",
                "",
                "",
                "[]",
                "",
                "",
                "unset",
                "needs_text",
                0,
                None,
                "2026-05-03T09:00:00+00:00",
                "2026-05-03T09:00:00+00:00",
                None,
                0,
                "{}",
                "[]",
            ),
        )

    repo = SQLiteItemRepository(db_path)

    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(saved_items)")}
        row = connection.execute(
            """
            SELECT learning_brief_json, ai_status, ai_attempt_count,
                   ai_last_attempt_at, ai_last_error
            FROM saved_items WHERE id = ?
            """,
            ("old-item",),
        ).fetchone()

    assert {
        "learning_brief_json",
        "ai_status",
        "ai_attempt_count",
        "ai_last_attempt_at",
        "ai_last_error",
    } <= columns
    assert row == ("{}", "pending", 0, None, "")

    loaded = repo.get("old-item")
    assert loaded is not None
    assert loaded.learning_brief is None
    assert loaded.ai_status is AIStatus.PENDING
    assert loaded.ai_attempt_count == 0
    assert loaded.ai_last_attempt_at is None
    assert loaded.ai_last_error == ""

    blocked = repo.get("blocked-item")
    assert blocked is not None
    assert blocked.status is Status.NEEDS_TEXT
    assert blocked.ai_status is AIStatus.FAILED
    assert blocked not in repo.list_ai_retry_candidates(limit=10, max_attempts=3)


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


def test_repository_returns_none_for_ambiguous_short_alias(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    now = datetime(2026, 5, 3, 9, 0, tzinfo=UTC)
    first = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/first",
            source_type=SourceType.WEB,
            now=now,
        ),
        id="7f3a0000aaaa",
    )
    second = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/second",
            source_type=SourceType.WEB,
            now=now,
        ),
        id="7f3a1111bbbb",
    )

    repo.save(first)
    repo.save(second)

    assert repo.resolve_item_ref("telegram:123", "kb_7f3a") is None


def test_repository_preserves_previously_assigned_alias_after_later_collision(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    now = datetime(2026, 5, 3, 9, 0, tzinfo=UTC)
    first = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/first",
            source_type=SourceType.WEB,
            now=now,
        ),
        id="7f3a0000aaaa",
    )
    repo.save(first)

    assert repo.item_alias("telegram:123", first.id) == "kb_7f3a"

    second = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/second",
            source_type=SourceType.WEB,
            now=now,
        ),
        id="7f3a1111bbbb",
    )
    repo.save(second)

    assert repo.item_alias("telegram:123", first.id) == "kb_7f3a"
    assert repo.item_alias("telegram:123", second.id) == "kb_7f3a1"
    assert repo.resolve_item_ref("telegram:123", "kb_7f3a") == first.id
    assert repo.resolve_item_ref("telegram:123", "kb_7f3a1") == second.id


def test_repository_renders_longer_alias_when_short_alias_collides(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    now = datetime(2026, 5, 3, 9, 0, tzinfo=UTC)
    first = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/first",
            source_type=SourceType.WEB,
            now=now,
        ),
        id="7f3a0000aaaa",
    )
    second = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/second",
            source_type=SourceType.WEB,
            now=now,
        ),
        id="7f3a1111bbbb",
    )

    repo.save(first)
    repo.save(second)

    assert repo.item_alias("telegram:123", first.id) == "kb_7f3a0"
    assert repo.item_alias("telegram:123", second.id) == "kb_7f3a1"
    assert repo.resolve_item_ref("telegram:123", "kb_7f3a0") == first.id
    assert repo.resolve_item_ref("telegram:123", "kb_7f3a1") == second.id


def test_repository_lists_ai_retry_candidates(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    now = datetime(2026, 5, 3, 9, 0, tzinfo=UTC)
    never_attempted = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/never",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, 30, tzinfo=UTC),
        ),
        id="never-attempted",
        ai_status=AIStatus.PENDING,
    )
    older_attempt = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/older",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        ),
        id="older-attempt",
        ai_status=AIStatus.RETRY_PENDING,
        ai_attempt_count=1,
        ai_last_attempt_at=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
    )
    same_attempt_first_created = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/same-first",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        ),
        id="same-b",
        ai_status=AIStatus.RETRY_PENDING,
        ai_attempt_count=1,
        ai_last_attempt_at=datetime(2026, 5, 3, 11, 0, tzinfo=UTC),
    )
    same_attempt_second_created_low_id = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/same-second-low",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, 5, tzinfo=UTC),
        ),
        id="same-a",
        ai_status=AIStatus.RETRY_PENDING,
        ai_attempt_count=1,
        ai_last_attempt_at=datetime(2026, 5, 3, 11, 0, tzinfo=UTC),
    )
    same_attempt_second_created_high_id = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/same-second-high",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, 5, tzinfo=UTC),
        ),
        id="same-c",
        ai_status=AIStatus.RETRY_PENDING,
        ai_attempt_count=1,
        ai_last_attempt_at=datetime(2026, 5, 3, 11, 0, tzinfo=UTC),
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
    for item in (
        same_attempt_second_created_high_id,
        ready,
        archived,
        same_attempt_second_created_low_id,
        maxed_attempts,
        same_attempt_first_created,
        older_attempt,
        never_attempted,
    ):
        repo.save(item)

    retry_candidates = repo.list_ai_retry_candidates(limit=10, max_attempts=3)

    assert repo.list_ai_retry_candidates(limit=4, max_attempts=3) == [
        never_attempted,
        older_attempt,
        same_attempt_first_created,
        same_attempt_second_created_low_id,
    ]
    assert same_attempt_second_created_high_id in retry_candidates
    assert archived not in retry_candidates
    assert ready not in retry_candidates
    assert maxed_attempts not in retry_candidates
    assert repo.count_ai_retry_pending() == 6


def test_repository_skips_needs_text_retry_candidates_without_manual_text(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    now = datetime(2026, 5, 3, 9, 0, tzinfo=UTC)
    blocked = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/blocked",
            source_type=SourceType.WEB,
            now=now,
        ),
        id="blocked",
        status=Status.NEEDS_TEXT,
        ai_status=AIStatus.PENDING,
    )
    manual_text = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/manual",
            source_type=SourceType.WEB,
            now=now,
            note="Manual content is enough to retry.",
        ),
        id="manual",
        status=Status.NEEDS_TEXT,
        ai_status=AIStatus.PENDING,
    )
    repo.save(blocked)
    repo.save(manual_text)

    assert repo.list_ai_retry_candidates(limit=10, max_attempts=3) == [manual_text]
    assert repo.count_ai_retry_pending() == 1


def test_repository_returns_last_ai_error(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")

    assert repo.last_ai_error() == ""

    old_attempt_newer_update = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/old-attempt",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        ),
        id="old-attempt",
        ai_status=AIStatus.RETRY_PENDING,
        ai_last_attempt_at=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
        ai_last_error="old attempt",
        updated_at=datetime(2026, 5, 3, 12, 0, tzinfo=UTC),
    )
    latest_attempt = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/latest-attempt",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        ),
        id="latest-attempt",
        ai_status=AIStatus.RETRY_PENDING,
        ai_last_attempt_at=datetime(2026, 5, 3, 11, 0, tzinfo=UTC),
        ai_last_error="latest attempt",
        updated_at=datetime(2026, 5, 3, 11, 0, tzinfo=UTC),
    )
    blank_error = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/blank",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        ),
        id="blank-error",
        ai_status=AIStatus.RETRY_PENDING,
        ai_last_attempt_at=datetime(2026, 5, 3, 12, 0, tzinfo=UTC),
        ai_last_error="",
    )
    repo.save(old_attempt_newer_update)
    repo.save(latest_attempt)
    repo.save(blank_error)

    assert repo.last_ai_error() == "latest attempt"

    fallback_repo = SQLiteItemRepository(tmp_path / "fallback.sqlite3")
    older_update = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/older-update",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        ),
        id="older-update",
        ai_status=AIStatus.RETRY_PENDING,
        ai_last_error="older update",
        updated_at=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
    )
    newer_update = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/newer-update",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        ),
        id="newer-update",
        ai_status=AIStatus.RETRY_PENDING,
        ai_last_error="newer update",
        updated_at=datetime(2026, 5, 3, 11, 0, tzinfo=UTC),
    )
    fallback_repo.save(older_update)
    fallback_repo.save(newer_update)

    assert fallback_repo.last_ai_error() == "newer update"
