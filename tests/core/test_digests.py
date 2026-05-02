from dataclasses import replace
from datetime import UTC, datetime, timedelta

from kb_agent.core.digests import DigestService
from kb_agent.core.models import Priority, SavedItem, SourceType, Status
from kb_agent.storage.sqlite import SQLiteItemRepository


def item(title: str, priority: Priority, days_old: int) -> SavedItem:
    created = datetime(2026, 5, 3, 9, 0, tzinfo=UTC) - timedelta(days=days_old)
    return replace(
        SavedItem.new(
            user_id="telegram:123",
            url=f"https://example.com/{title}",
            source_type=SourceType.WEB,
            now=created,
        ),
        title=title,
        tags=["ai"],
        topic="ai",
        summary=f"{title} summary",
        priority=priority,
        status=Status.READY,
    )


def test_daily_digest_selects_up_to_three_active_items(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    for saved in [
        item("one", Priority.HIGH, 1),
        item("two", Priority.MEDIUM, 2),
        item("three", Priority.UNSET, 3),
        item("four", Priority.LOW, 4),
    ]:
        repo.save(saved)

    digest = DigestService(repo).daily(user_id="telegram:123")

    assert len(digest.items) == 3
    assert "Daily tiny nudge" in digest.text


def test_weekly_digest_groups_items_by_topic(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    repo.save(item("rag", Priority.HIGH, 1))
    repo.save(replace(item("eval", Priority.MEDIUM, 2), topic="ai eval"))

    digest = DigestService(repo).weekly(user_id="telegram:123")

    assert "Weekly synthesis" in digest.text
    assert "ai" in digest.text
