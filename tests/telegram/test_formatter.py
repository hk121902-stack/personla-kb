from dataclasses import replace
from datetime import UTC, datetime

from kb_agent.core.models import Priority, SavedItem, SourceType, Status
from kb_agent.telegram.formatter import format_save_confirmation


def test_save_confirmation_is_compact() -> None:
    item = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/rag",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        ),
        title="RAG Notes",
        tags=["rag", "retrieval"],
        priority=Priority.HIGH,
        status=Status.READY,
    )

    text = format_save_confirmation(item)

    assert "Saved: RAG Notes" in text
    assert "Tags: rag, retrieval" in text
    assert "Priority: high" in text
    assert "Status: ready" in text
