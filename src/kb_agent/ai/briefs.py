from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from kb_agent.core.models import (
    AIStatus,
    ExtractedContent,
    LearningBrief,
    Priority,
    SavedItem,
    Status,
)


class AIErrorCategory(StrEnum):
    MISSING_API_KEY = "missing_api_key"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    INVALID_MODEL = "invalid_model"
    INVALID_RESPONSE = "invalid_ai_response"
    LOCAL_PROVIDER_UNAVAILABLE = "local_provider_unavailable"
    UNKNOWN_PROVIDER_ERROR = "unknown_provider_error"


class AIProviderError(RuntimeError):
    def __init__(self, category: AIErrorCategory, message: str) -> None:
        super().__init__(message)
        self.category = category


_REQUIRED_BRIEF_KEYS = (
    "title",
    "topic",
    "tags",
    "summary",
    "key_takeaways",
    "why_it_matters",
    "estimated_time_minutes",
    "suggested_next_action",
)


def build_request_context(
    *,
    item: SavedItem,
    extracted: ExtractedContent | None,
    normal_char_limit: int = 12_000,
    extended_char_limit: int = 40_000,
) -> dict[str, Any]:
    title = item.title
    text = item.extracted_text
    metadata: dict[str, str] = dict(item.source_metadata)

    if extracted is not None:
        title = extracted.title.strip() or item.title
        text = extracted.text.strip()
        metadata = dict(extracted.metadata)

    limit = extended_char_limit if item.priority is Priority.HIGH else normal_char_limit

    return {
        "url": item.url,
        "source_type": item.source_type.value,
        "title": title,
        "note": item.user_note,
        "priority": item.priority.value,
        "metadata": metadata,
        "extracted_text": text[:limit],
    }


def build_learning_brief_schema() -> dict[str, Any]:
    properties: dict[str, Any] = {
        "title": {"type": "string"},
        "topic": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
        "key_takeaways": {"type": "array", "items": {"type": "string"}},
        "why_it_matters": {"type": "string"},
        "estimated_time_minutes": {"type": "integer", "minimum": 1},
        "suggested_next_action": {"type": "string"},
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(_REQUIRED_BRIEF_KEYS),
        "additionalProperties": False,
    }


def build_enrichment_prompt(context: dict[str, Any]) -> str:
    return (
        "Create a concise learning brief for this saved item. "
        "Return JSON only using the provided schema fields. "
        "Use the source content, but preserve the user's intent from their note.\n\n"
        f"Context:\n{json.dumps(context, ensure_ascii=False, sort_keys=True)}"
    )


def validate_learning_brief(
    data: dict[str, Any],
    *,
    provider: str,
    model: str,
    now: datetime | None = None,
) -> LearningBrief:
    missing = [key for key in _REQUIRED_BRIEF_KEYS if key not in data]
    if missing:
        keys = ", ".join(missing)
        raise AIProviderError(
            AIErrorCategory.INVALID_RESPONSE,
            f"{provider} returned a learning brief missing required keys: {keys}",
        )

    return LearningBrief(
        brief_version=1,
        provider=provider,
        model=model,
        generated_at=now or datetime.now(UTC),
        title=str(data["title"]),
        topic=str(data["topic"]),
        tags=list(data["tags"]),
        summary=str(data["summary"]),
        key_takeaways=list(data["key_takeaways"]),
        why_it_matters=str(data["why_it_matters"]),
        estimated_time_minutes=int(data["estimated_time_minutes"]),
        suggested_next_action=str(data["suggested_next_action"]),
    )


def sync_brief_to_item(
    item: SavedItem,
    brief: LearningBrief,
    *,
    ready: bool,
    now: datetime,
    extracted: ExtractedContent | None = None,
) -> SavedItem:
    extracted_text = item.extracted_text
    source_metadata = dict(item.source_metadata)
    if extracted is not None:
        extracted_text = extracted.text.strip()
        source_metadata = dict(extracted.metadata)

    return replace(
        item,
        title=brief.title,
        topic=brief.topic,
        tags=list(brief.tags),
        summary=brief.summary,
        learning_brief=brief,
        ai_status=AIStatus.READY if ready else AIStatus.RETRY_PENDING,
        ai_last_error="" if ready else item.ai_last_error,
        extracted_text=extracted_text,
        source_metadata=source_metadata,
        status=Status.READY if ready else Status.FAILED_ENRICHMENT,
        updated_at=now,
    )
