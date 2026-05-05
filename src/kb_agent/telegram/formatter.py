from __future__ import annotations

from collections.abc import Callable, Sequence
from html import escape
from typing import Protocol
from urllib.parse import urlparse

from kb_agent.core.aliases import alias_for_item_id
from kb_agent.core.archive_review import ArchiveRecommendation
from kb_agent.core.models import SavedItem


class TextResult(Protocol):
    text: str


_SUMMARY_SENTENCE_LIMIT = 1
_SUMMARY_CHAR_LIMIT = 220
_TAG_LIMIT = 5


def _html(text: object) -> str:
    return escape(str(text), quote=True)


def format_plain_text(text: object) -> str:
    return _html(text)


def _valid_link(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _title_link(title: str, url: str) -> str:
    safe_title = _html(title or url)
    if _valid_link(url):
        return f'<a href="{_html(url)}">{safe_title}</a>'
    return safe_title


def _compact_summary(text: str) -> str:
    normalized = " ".join(text.split())
    if not normalized:
        return ""

    pieces = []
    for sentence in normalized.replace("? ", "?. ").replace("! ", "!. ").split(". "):
        cleaned = sentence.strip()
        if not cleaned:
            continue
        if not cleaned.endswith((".", "?", "!")):
            cleaned = f"{cleaned}."
        pieces.append(cleaned)
        if len(pieces) >= _SUMMARY_SENTENCE_LIMIT:
            break

    compact = " ".join(pieces) if pieces else normalized
    if len(compact) > _SUMMARY_CHAR_LIMIT:
        compact = compact[: _SUMMARY_CHAR_LIMIT - 1].rstrip() + "…"
    return compact


def _label(name: str) -> str:
    return f"<b>{_html(name)}:</b>"


def _labeled_line(name: str, value: object) -> str:
    return f"{_label(name)} {_html(value)}"


def _detail_hint(alias: str) -> str:
    return f'<b>{_html("Need more?")}</b> Reply "details" or send details {_html(alias)}.'


def _tag_line(tags: Sequence[str]) -> str:
    selected = [tag for tag in tags if tag.strip()][:_TAG_LIMIT]
    if not selected:
        return f"{_label('Tags')} none"
    return f"{_label('Tags')} " + ", ".join(_html(tag) for tag in selected)


def _compact_note_line(note: str) -> str:
    compact = _compact_summary(note)
    if not compact:
        return ""
    return _labeled_line("Note", compact)


def format_save_confirmation(item: SavedItem, *, alias: str | None = None) -> str:
    title = item.title or item.url
    alias = alias or alias_for_item_id(item.id)
    summary = _compact_summary(item.summary or title)
    lines = [
        f"<b>{_title_link(title, item.url)}</b>",
        _labeled_line("ID", alias),
        _tag_line(item.tags),
        _labeled_line("Priority", item.priority.value),
    ]
    note_line = _compact_note_line(item.user_note)
    if note_line:
        lines.append(note_line)
    if summary:
        lines.extend(["", _html(summary)])
    lines.extend(["", _detail_hint(alias)])
    return "\n".join(lines)


def format_needs_text_prompt(item: SavedItem) -> str:
    url = _html(item.url)
    return "\n".join(
        [
            f"I saved the link, but could not extract text from: {url}",
            "Send the useful text and I will use it as saved content: "
            f"save {url} note: &lt;text&gt;",
        ],
    )


def format_retrieval_response(
    response: TextResult | str,
    *,
    mode: str = "ask",
    query: str = "",
) -> str:
    if isinstance(response, str):
        return _html(response)

    matches = list(getattr(response, "matches", []))
    if mode == "show":
        query_text = query or getattr(response, "question", "")
        count = len(matches)
        noun = "item" if count == 1 else "items"
        aliases = getattr(response, "item_aliases", {}) or {}
        lines = [f'<b>Found {count} {noun} for "{_html(query_text)}"</b>']
        if not matches:
            return "\n".join([lines[0], "No strong saved source match."])
        lines.append("")
        for item in matches:
            lines.append(
                _compact_item_card(
                    item,
                    alias=_item_alias(item, aliases),
                ),
            )
            lines.append("")
        first_alias = _item_alias(matches[0], aliases)
        lines.append(
            f'<b>{_html("Need more?")}</b> Reply "details" to an item, '
            f"or send details {_html(first_alias)}.",
        )
        return "\n".join(lines).strip()

    aliases = getattr(response, "item_aliases", {}) or {}
    answer = _compact_summary(getattr(response, "answer", "") or response.text)
    lines = ["<b>From your knowledge base</b>", _html(answer), "", "<b>Sources</b>"]
    if matches:
        for item in matches:
            alias = _item_alias(item, aliases)
            lines.append(f"- {_html(alias)}: {_title_link(item.title or item.url, item.url)}")
    else:
        lines.append("- No strong saved source match.")
    extra_context = getattr(response, "extra_context", "")
    if extra_context:
        lines.extend(["", "<b>Extra context</b>", _html(_compact_summary(extra_context))])
    if matches:
        first_alias = _item_alias(matches[0], aliases)
        lines.extend(
            [
                "",
                f'<b>{_html("Need more?")}</b> Reply "details" to an item, '
                f"or send details {_html(first_alias)}.",
            ],
        )
    return "\n".join(lines)


def _item_alias(item: SavedItem, aliases: dict[str, str]) -> str:
    alias = aliases.get(item.id)
    if alias:
        return alias
    return _alias_or_item_id(item)


def _alias_or_item_id(item: SavedItem, alias: str | None = None) -> str:
    if alias:
        return alias
    try:
        return alias_for_item_id(item.id)
    except ValueError:
        return item.id


def _compact_item_card(item: SavedItem, *, alias: str) -> str:
    title = item.title or item.url
    summary = _compact_summary(item.summary or item.extracted_text or title)
    lines = [
        f"<b>{_title_link(title, item.url)}</b>",
        _labeled_line("ID", alias),
        _tag_line(item.tags),
    ]
    note_line = _compact_note_line(item.user_note)
    if note_line:
        lines.append(note_line)
    if summary:
        lines.append(_html(summary))
    return "\n".join(lines)


def format_daily_digest(digest: TextResult | str) -> str:
    if isinstance(digest, str) or not hasattr(digest, "items"):
        return _format_text_result(digest)
    items = list(getattr(digest, "items", []))
    aliases = getattr(digest, "item_aliases", {}) or {}
    lines = ["<b>Daily tiny nudge</b>"]
    for item in items:
        lines.extend(["", _compact_item_card(item, alias=_item_alias(item, aliases))])
    if items:
        first_alias = _item_alias(items[0], aliases)
        lines.extend(
            [
                "",
                f'<b>{_html("Need more?")}</b> Reply "details" to an item, '
                f"or send details {_html(first_alias)}.",
            ],
        )
    return "\n".join(lines)


def format_weekly_digest(digest: TextResult | str) -> str:
    if isinstance(digest, str) or not hasattr(digest, "items"):
        return _format_text_result(digest)
    items = list(getattr(digest, "items", []))
    aliases = getattr(digest, "item_aliases", {}) or {}
    lines = ["<b>Weekly synthesis</b>"]
    grouped: dict[str, list[SavedItem]] = {}
    for item in items:
        topic = item.topic or (item.tags[0] if item.tags else "general")
        grouped.setdefault(topic, []).append(item)
    for topic, topic_items in grouped.items():
        lines.extend(["", f"<b>{_html(topic)}</b>"])
        for item in topic_items:
            lines.extend(["", _compact_item_card(item, alias=_item_alias(item, aliases))])
    if items:
        first_alias = _item_alias(items[0], aliases)
        lines.extend(
            [
                "",
                f'<b>{_html("Need more?")}</b> Reply "details" to an item, '
                f"or send details {_html(first_alias)}.",
            ],
        )
    return "\n".join(lines)


def format_digest(digest: TextResult | str) -> str:
    return _format_text_result(digest)


def format_archive_recommendations(
    recommendations: Sequence[ArchiveRecommendation],
    *,
    alias_for_item: Callable[[SavedItem], str | None] | None = None,
) -> str:
    if not recommendations:
        return "No archive recommendations."

    lines = ["<b>Archive recommendations</b>"]
    for recommendation in recommendations:
        item = recommendation.item
        alias = _archive_item_alias(item, alias_for_item=alias_for_item)
        title = item.title.strip() if item.title else ""
        label = title or alias or "Saved item"
        lines.extend(
            [
                "",
                f"<b>{_html(label)}</b>",
                f"ID: {_html(alias)}",
                f"Reason: {_html(recommendation.reason)}",
            ],
        )
    return "\n".join(lines)


def _archive_item_alias(
    item: SavedItem,
    *,
    alias_for_item: Callable[[SavedItem], str | None] | None,
) -> str:
    if alias_for_item is not None:
        alias = alias_for_item(item)
        if alias:
            return alias
    try:
        return alias_for_item_id(item.id)
    except ValueError:
        return item.id


def format_learning_brief(item: SavedItem, *, alias: str | None = None) -> str:
    brief = item.learning_brief
    if brief is None:
        return format_save_confirmation(item, alias=alias)

    alias = alias or alias_for_item_id(item.id)
    summary = _compact_summary(brief.summary)
    return "\n".join(
        [
            f"<b>{_title_link(brief.title, item.url)}</b>",
            _labeled_line("ID", alias),
            _tag_line(brief.tags),
            f"{_label('Priority')} {_html(item.priority.value)} "
            f"· {_html(brief.estimated_time_minutes)} min",
            "",
            _html(summary),
            "",
            _detail_hint(alias),
        ],
    )


def format_item_details(item: SavedItem, *, alias: str | None = None) -> str:
    alias = _alias_or_item_id(item, alias)
    brief = item.learning_brief
    title = brief.title if brief is not None else item.title or item.url
    summary = brief.summary if brief is not None else item.summary
    lines = [
        "<b>Details</b>",
        f"<b>{_title_link(title, item.url)}</b>",
        f"ID: {_html(alias)}",
        _tag_line(brief.tags if brief is not None else item.tags),
        f"Priority: {_html(item.priority.value)}",
        f"Source: {_html(item.url)}",
        "",
        "<b>Summary</b>",
        _html(summary or title),
    ]
    if brief is not None:
        lines.extend(["", "<b>Key takeaways:</b>"])
        lines.extend(f"- {_html(takeaway)}" for takeaway in brief.key_takeaways)
        lines.extend(
            [
                "",
                "<b>Why it matters:</b>",
                _html(brief.why_it_matters),
                "",
                f"Time: {_html(brief.estimated_time_minutes)} min",
                f"Next: {_html(brief.suggested_next_action)}",
            ],
        )
    return "\n".join(line for line in lines if line != "")


def format_pending_learning_brief(item: SavedItem, *, alias: str | None = None) -> str:
    alias = alias or alias_for_item_id(item.id)
    return "\n".join(
        [
            f"Saved: {_html(item.title or item.url)}",
            _labeled_line("ID", alias),
            "Preparing learning brief...",
        ],
    )


def format_enrichment_retry_message(item: SavedItem, *, alias: str | None = None) -> str:
    alias = alias or alias_for_item_id(item.id)
    return "\n".join(
        [
            "Saved with basic enrichment. AI brief is pending retry.",
            _labeled_line("ID", alias),
        ],
    )


def format_ai_status(status, *, pending_retry_count: int) -> str:
    last_error = status.last_error or "none"
    chain = " -> ".join(_html(provider) for provider in status.chain)
    return "\n".join(
        [
            "AI status",
            f"Chain: {chain}",
            f"Selected: {_html(getattr(status, 'selected_model', '') or 'none')}",
            f"Gemini model: {_html(getattr(status, 'gemini_model', '') or 'none')}",
            "Ollama: "
            f"{_html(getattr(status, 'ollama_base_url', '') or 'not configured')} "
            f"({_html(getattr(status, 'ollama_model', '') or 'none')})",
            f"Pending retries: {_html(pending_retry_count)}",
            f"Last error: {_html(last_error)}",
        ],
    )


def _format_text_result(result: TextResult | str) -> str:
    if isinstance(result, str):
        return format_plain_text(result)
    return format_plain_text(result.text)
