from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from kb_agent.core.archive_review import ArchiveRecommendation
from kb_agent.core.models import SavedItem


class TextResult(Protocol):
    text: str


def format_save_confirmation(item: SavedItem) -> str:
    title = item.title or item.url
    tags = ", ".join(item.tags) if item.tags else "none"
    return "\n".join(
        [
            f"Saved: {title}",
            f"URL: {item.url}",
            f"Tags: {tags}",
            f"Priority: {item.priority.value}",
            f"Status: {item.status.value}",
        ],
    )


def format_needs_text_prompt(item: SavedItem) -> str:
    return "\n".join(
        [
            f"I saved the link, but could not extract text from: {item.url}",
            "Reply with the key text or a short note when you have it.",
        ],
    )


def format_retrieval_response(response: TextResult | str) -> str:
    if isinstance(response, str):
        return response
    return response.text


def format_daily_digest(digest: TextResult | str) -> str:
    return _format_text_result(digest)


def format_weekly_digest(digest: TextResult | str) -> str:
    return _format_text_result(digest)


def format_digest(digest: TextResult | str) -> str:
    return _format_text_result(digest)


def format_archive_recommendations(recommendations: Sequence[ArchiveRecommendation]) -> str:
    if not recommendations:
        return "No archive recommendations."

    lines = ["Archive recommendations"]
    for recommendation in recommendations:
        item = recommendation.item
        title = item.title or item.url
        lines.append(f"- {item.id}: {title} ({recommendation.reason})")
    return "\n".join(lines)


def _format_text_result(result: TextResult | str) -> str:
    if isinstance(result, str):
        return result
    return result.text
