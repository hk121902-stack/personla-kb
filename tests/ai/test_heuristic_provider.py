from datetime import UTC, datetime

import pytest

from kb_agent.ai.providers import HeuristicAIProvider
from kb_agent.core.models import ExtractedContent, SavedItem, SourceType, Status


@pytest.mark.asyncio
async def test_heuristic_provider_enriches_from_extracted_content() -> None:
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/rag",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        note="useful for retrieval evaluation",
    )
    extracted = ExtractedContent(
        title="RAG Evaluation Guide",
        text="Retrieval augmented generation evaluation uses recall and precision.",
        metadata={"status_code": "200"},
    )

    enriched = await HeuristicAIProvider().enrich(item, extracted)

    assert enriched.status is Status.READY
    assert enriched.title == "RAG Evaluation Guide"
    assert "retrieval" in enriched.tags
    assert enriched.topic
    assert enriched.summary
    assert enriched.embedding


@pytest.mark.asyncio
async def test_heuristic_provider_marks_missing_content_as_needs_text() -> None:
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://linkedin.com/posts/private",
        source_type=SourceType.LINKEDIN,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )

    enriched = await HeuristicAIProvider().enrich(item, None)

    assert enriched.status is Status.NEEDS_TEXT
    assert enriched.title == item.url
