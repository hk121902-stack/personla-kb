import json
from datetime import UTC, datetime

import pytest

from kb_agent.core.models import (
    AIStatus,
    Enrichment,
    ExtractedContent,
    LearningBrief,
    Priority,
    SavedItem,
    SourceType,
    Status,
)


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


def test_saved_item_tracks_default_ai_state() -> None:
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/ai",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )

    assert item.ai_status is AIStatus.PENDING
    assert item.ai_attempt_count == 0
    assert item.ai_last_attempt_at is None
    assert item.ai_last_error == ""
    assert item.learning_brief is None


def test_learning_brief_is_frozen_and_normalized() -> None:
    brief = LearningBrief(
        brief_version=1,
        provider="gemini",
        model="gemini-2.5-flash-lite",
        generated_at=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
        title=" Retrieval Guide ",
        topic=" Search ",
        tags=["RAG", " Search ", "RAG"],
        summary=" How retrieval evaluation works. ",
        key_takeaways=[" Use recall. ", " Check precision. "],
        why_it_matters="It improves saved-first answers.",
        estimated_time_minutes=20,
        suggested_next_action="Try a small evaluation example.",
    )

    assert brief.title == "Retrieval Guide"
    assert brief.topic == "Search"
    assert brief.tags == ["rag", "search"]
    assert brief.summary == "How retrieval evaluation works."
    assert brief.key_takeaways == ["Use recall.", "Check precision."]

    with pytest.raises(TypeError):
        brief.tags.append("new")


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


def test_saved_item_collections_cannot_be_mutated() -> None:
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/post",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )

    assert item.tags == []
    assert item.source_metadata == {}
    assert item.embedding == []
    assert json.dumps(item.tags) == "[]"
    assert json.dumps(item.source_metadata) == "{}"
    assert json.dumps(item.embedding) == "[]"

    with pytest.raises(TypeError):
        item.tags.append("python")
    with pytest.raises(TypeError):
        item.source_metadata["author"] = "Ada"
    with pytest.raises(TypeError):
        item.embedding.extend([0.1])

    assert item.tags == []
    assert item.source_metadata == {}
    assert item.embedding == []


def test_extracted_content_metadata_cannot_be_mutated() -> None:
    extracted = ExtractedContent(
        title="Example",
        text="Body",
        metadata={"author": "Ada"},
    )

    assert extracted.metadata == {"author": "Ada"}
    assert json.dumps(extracted.metadata) == '{"author": "Ada"}'

    with pytest.raises(TypeError):
        extracted.metadata.update({"site": "example.com"})

    assert extracted.metadata == {"author": "Ada"}


def test_enrichment_collections_cannot_be_mutated() -> None:
    enrichment = Enrichment(
        title="Example",
        tags=["python"],
        topic="engineering",
        summary="A summary",
        embedding=[0.1, 0.2],
    )

    assert enrichment.tags == ["python"]
    assert enrichment.embedding == [0.1, 0.2]
    assert json.dumps(enrichment.tags) == '["python"]'
    assert json.dumps(enrichment.embedding) == "[0.1, 0.2]"

    with pytest.raises(TypeError):
        enrichment.tags.pop()
    with pytest.raises(TypeError):
        enrichment.embedding[0] = 0.3

    assert enrichment.tags == ["python"]
    assert enrichment.embedding == [0.1, 0.2]
