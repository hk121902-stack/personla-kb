from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from kb_agent.core.aliases import alias_for_item_id
from kb_agent.core.archive_review import ArchiveRecommendation
from kb_agent.core.models import SavedItem


class TextResult(Protocol):
    text: str


def format_save_confirmation(item: SavedItem, *, alias: str | None = None) -> str:
    title = item.title or item.url
    tags = ", ".join(item.tags) if item.tags else "none"
    alias = alias or alias_for_item_id(item.id)
    return "\n".join(
        [
            f"Saved: {title}",
            f"ID: {alias}",
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
            "Send the useful text and I will use it as saved content: "
            f"save {item.url} note: <text>",
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


def format_archive_recommendations(
    recommendations: Sequence[ArchiveRecommendation],
    *,
    alias_for_item: Callable[[SavedItem], str | None] | None = None,
) -> str:
    if not recommendations:
        return "No archive recommendations."

    lines = ["Archive recommendations"]
    for recommendation in recommendations:
        item = recommendation.item
        title = item.title or item.url
        alias = alias_for_item(item) if alias_for_item is not None else None
        alias = alias or alias_for_item_id(item.id)
        lines.append(f"- {alias}: {title} ({recommendation.reason})")
    return "\n".join(lines)


def format_learning_brief(item: SavedItem, *, alias: str | None = None) -> str:
    brief = item.learning_brief
    if brief is None:
        return format_save_confirmation(item, alias=alias)

    alias = alias or alias_for_item_id(item.id)
    lines = [
        f"Learning brief: {brief.title}",
        f"ID: {alias}",
        "",
        "Summary:",
        brief.summary,
        "",
        "Key takeaways:",
    ]
    lines.extend(f"- {takeaway}" for takeaway in brief.key_takeaways)
    lines.extend(
        [
            "",
            "Why it matters:",
            brief.why_it_matters,
            "",
            f"Time: {brief.estimated_time_minutes} min",
            f"Next: {brief.suggested_next_action}",
        ],
    )
    return "\n".join(lines)


def format_pending_learning_brief(item: SavedItem, *, alias: str | None = None) -> str:
    alias = alias or alias_for_item_id(item.id)
    return "\n".join(
        [
            f"Saved: {item.title or item.url}",
            f"ID: {alias}",
            "Preparing learning brief...",
        ],
    )


def format_enrichment_retry_message(item: SavedItem, *, alias: str | None = None) -> str:
    alias = alias or alias_for_item_id(item.id)
    return "\n".join(
        [
            "Saved with basic enrichment. AI brief is pending retry.",
            f"ID: {alias}",
        ],
    )


def format_ai_status(status, *, pending_retry_count: int) -> str:
    last_error = status.last_error or "none"
    return "\n".join(
        [
            "AI status",
            f"Chain: {' -> '.join(status.chain)}",
            f"Pending retries: {pending_retry_count}",
            f"Last error: {last_error}",
        ],
    )


def _format_text_result(result: TextResult | str) -> str:
    if isinstance(result, str):
        return result
    return result.text
