import json
from datetime import UTC, datetime

import pytest

from kb_agent.core.models import (
    Enrichment,
    ExtractedContent,
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
