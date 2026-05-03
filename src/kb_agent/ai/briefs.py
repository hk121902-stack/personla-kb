from __future__ import annotations

import json
from collections.abc import Mapping
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

_STRING_BRIEF_KEYS = (
    "title",
    "topic",
    "summary",
    "why_it_matters",
    "suggested_next_action",
)


def build_request_context(
    *,
    item: SavedItem,
    extracted: ExtractedContent | None,
    normal_char_limit: int = 4_000,
    extended_char_limit: int = 12_000,
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
    data: Mapping[str, Any],
    *,
    provider: str,
    model: str,
    now: datetime | None = None,
) -> LearningBrief:
    if not isinstance(data, Mapping):
        raise AIProviderError(
            AIErrorCategory.INVALID_RESPONSE,
            f"{provider} returned a non-object learning brief",
        )

    unexpected = [key for key in data if key not in _REQUIRED_BRIEF_KEYS]
    if unexpected:
        keys = ", ".join(sorted(unexpected))
        raise AIProviderError(
            AIErrorCategory.INVALID_RESPONSE,
            f"{provider} returned a learning brief with unexpected keys: {keys}",
        )

    missing = [key for key in _REQUIRED_BRIEF_KEYS if key not in data]
    if missing:
        keys = ", ".join(missing)
        raise AIProviderError(
            AIErrorCategory.INVALID_RESPONSE,
            f"{provider} returned a learning brief missing required keys: {keys}",
        )

    for key in _STRING_BRIEF_KEYS:
        value = data[key]
        if not isinstance(value, str) or not value.strip():
            raise AIProviderError(
                AIErrorCategory.INVALID_RESPONSE,
                f"{provider} returned an invalid learning brief field: {key}",
            )

    tags = _validate_string_list(data["tags"], field_name="tags", provider=provider)
    key_takeaways = _validate_string_list(
        data["key_takeaways"],
        field_name="key_takeaways",
        provider=provider,
    )

    estimated_time_minutes = data["estimated_time_minutes"]
    if not isinstance(estimated_time_minutes, int) or isinstance(
        estimated_time_minutes,
        bool,
    ) or estimated_time_minutes < 1:
        raise AIProviderError(
            AIErrorCategory.INVALID_RESPONSE,
            f"{provider} returned an invalid learning brief field: estimated_time_minutes",
        )

    return LearningBrief(
        brief_version=1,
        provider=provider,
        model=model,
        generated_at=now or datetime.now(UTC),
        title=str(data["title"]),
        topic=str(data["topic"]),
        tags=tags,
        summary=str(data["summary"]),
        key_takeaways=key_takeaways,
        why_it_matters=str(data["why_it_matters"]),
        estimated_time_minutes=estimated_time_minutes,
        suggested_next_action=str(data["suggested_next_action"]),
    )


def _validate_string_list(value: Any, *, field_name: str, provider: str) -> list[str]:
    if not isinstance(value, list):
        raise AIProviderError(
            AIErrorCategory.INVALID_RESPONSE,
            f"{provider} returned an invalid learning brief field: {field_name}",
        )

    if not all(isinstance(item, str) for item in value):
        raise AIProviderError(
            AIErrorCategory.INVALID_RESPONSE,
            f"{provider} returned an invalid learning brief field: {field_name}",
        )

    valid_items = [item for item in value if item.strip()]
    if not valid_items:
        raise AIProviderError(
            AIErrorCategory.INVALID_RESPONSE,
            f"{provider} returned an empty learning brief field after validation: {field_name}",
        )

    return value


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
        status=Status.READY,
        updated_at=now,
    )
