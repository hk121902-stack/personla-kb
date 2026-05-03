from datetime import UTC, datetime

import pytest

from kb_agent.ai.briefs import (
    AIErrorCategory,
    AIProviderError,
    build_enrichment_prompt,
    build_learning_brief_schema,
    build_request_context,
    sync_brief_to_item,
    validate_learning_brief,
)
from kb_agent.core.models import (
    AIStatus,
    ExtractedContent,
    LearningBrief,
    Priority,
    SavedItem,
    SourceType,
)


def _item(priority: Priority = Priority.UNSET) -> SavedItem:
    return SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/long",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        note="focus on practical retrieval",
        priority=priority,
    )


def test_context_trims_normal_items() -> None:
    extracted = ExtractedContent(title="Long Post", text="x" * 600, metadata={"author": "Ada"})

    context = build_request_context(
        item=_item(),
        extracted=extracted,
        normal_char_limit=120,
        extended_char_limit=500,
    )

    assert context["extracted_text"] == "x" * 120
    assert context["title"] == "Long Post"
    assert context["note"] == "focus on practical retrieval"


def test_context_uses_extended_limit_for_high_priority() -> None:
    extracted = ExtractedContent(title="Long Post", text="x" * 600, metadata={})

    context = build_request_context(
        item=_item(Priority.HIGH),
        extracted=extracted,
        normal_char_limit=120,
        extended_char_limit=500,
    )

    assert context["extracted_text"] == "x" * 500


def test_validate_learning_brief_rejects_missing_keys() -> None:
    with pytest.raises(AIProviderError) as error:
        validate_learning_brief({"title": "Only title"}, provider="gemini", model="model")

    assert error.value.category is AIErrorCategory.INVALID_RESPONSE


def test_sync_brief_to_item_sets_search_fields_and_ai_status() -> None:
    item = _item()
    brief = LearningBrief(
        brief_version=1,
        provider="gemini",
        model="gemini-2.5-flash-lite",
        generated_at=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
        title="Retrieval Guide",
        topic="retrieval",
        tags=["rag", "search"],
        summary="A practical summary.",
        key_takeaways=["Use recall."],
        why_it_matters="Better answers.",
        estimated_time_minutes=12,
        suggested_next_action="Try an example.",
    )

    synced = sync_brief_to_item(
        item,
        brief,
        ready=True,
        now=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
    )

    assert synced.learning_brief == brief
    assert synced.title == "Retrieval Guide"
    assert synced.topic == "retrieval"
    assert synced.tags == ["rag", "search"]
    assert synced.summary == "A practical summary."
    assert synced.ai_status is AIStatus.READY


def test_prompt_mentions_json_and_preserves_user_note() -> None:
    prompt = build_enrichment_prompt(
        build_request_context(
            item=_item(),
            extracted=ExtractedContent(title="Post", text="Body", metadata={}),
        ),
    )

    assert "Return JSON only" in prompt
    assert "focus on practical retrieval" in prompt
    assert "preserve the user's intent" in prompt


def test_schema_requires_phase_two_fields() -> None:
    schema = build_learning_brief_schema()

    assert schema["type"] == "object"
    assert "difficulty" not in schema["properties"]
    assert "estimated_time_minutes" in schema["required"]
