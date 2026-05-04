from dataclasses import replace
from datetime import UTC, datetime

from kb_agent.ai.router import AIStatusSnapshot
from kb_agent.core.models import AIStatus, LearningBrief, Priority, SavedItem, SourceType, Status
from kb_agent.telegram.formatter import (
    format_ai_status,
    format_enrichment_retry_message,
    format_item_details,
    format_learning_brief,
    format_needs_text_prompt,
    format_pending_learning_brief,
    format_save_confirmation,
)


def _brief() -> LearningBrief:
    return LearningBrief(
        brief_version=1,
        provider="gemini",
        model="gemini-2.5-flash-lite",
        generated_at=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
        title="Learning Brief",
        topic="ai",
        tags=["gemini", "claude", "agents", "repos", "costs", "extra"],
        summary=(
            "This is a long summary sentence about a useful saved item. "
            "This second sentence should be hidden from compact Telegram cards. "
            "This third sentence should only appear in details."
        ),
        key_takeaways=["Takeaway one.", "Takeaway two."],
        why_it_matters="It matters.",
        estimated_time_minutes=20,
        suggested_next_action="Try it.",
    )


def _item() -> SavedItem:
    return replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/brief",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        ),
        id="7f3a9b8c1234",
        title="Learning Brief",
        learning_brief=_brief(),
        ai_status=AIStatus.READY,
        status=Status.READY,
    )


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

    assert text.startswith('<b><a href="https://example.com/rag">RAG Notes</a></b>')
    assert "ID: kb_" in text
    assert "Tags: rag, retrieval" in text
    assert "Priority: high" in text
    assert "Status: ready" not in text
    assert 'Need more? Reply "details" or send details kb_' in text


def test_needs_text_prompt_tells_user_to_save_note() -> None:
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/rag",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )

    text = format_needs_text_prompt(item)

    assert text == (
        "I saved the link, but could not extract text from: https://example.com/rag\n"
        "Send the useful text and I will use it as saved content: "
        "save https://example.com/rag note: <text>"
    )


def test_format_learning_brief_is_compact_html_card() -> None:
    text = format_learning_brief(_item())

    assert text.startswith('<b><a href="https://example.com/brief">Learning Brief</a></b>')
    assert "ID: kb_7f3a" in text
    assert "Tags: gemini, claude, agents, repos, costs" in text
    assert "Priority: unset · 20 min" in text
    assert "This second sentence should be hidden" not in text
    assert "Key takeaways:" not in text
    assert 'Need more? Reply "details" or send details kb_7f3a.' in text


def test_format_learning_brief_escapes_html() -> None:
    item = replace(
        _item(),
        title='Use <script> & "quotes"',
        url="https://example.com/?a=1&b=2",
        learning_brief=replace(
            _brief(),
            title='Use <script> & "quotes"',
            summary="A <dangerous> summary & note.",
            tags=["a&b"],
        ),
    )

    text = format_learning_brief(item)

    assert "&lt;script&gt;" in text
    assert "A &lt;dangerous&gt; summary &amp; note." in text
    assert "https://example.com/?a=1&amp;b=2" in text


def test_format_item_details_includes_full_brief() -> None:
    text = format_item_details(_item())

    assert "<b>Details</b>" in text
    assert "ID: kb_7f3a" in text
    assert "Key takeaways:" in text
    assert "- Takeaway one." in text
    assert "Why it matters:" in text
    assert "Source: https://example.com/brief" in text


def test_format_pending_learning_brief_includes_alias() -> None:
    assert format_pending_learning_brief(_item()) == (
        "Saved: Learning Brief\nID: kb_7f3a\nPreparing learning brief..."
    )


def test_format_enrichment_retry_message_includes_alias() -> None:
    assert format_enrichment_retry_message(_item()) == (
        "Saved with basic enrichment. AI brief is pending retry.\nID: kb_7f3a"
    )


def test_format_ai_status() -> None:
    text = format_ai_status(
        AIStatusSnapshot(
            chain=["gemini:lite", "ollama:qwen3:8b", "heuristic:heuristic"],
            selected_model="gemini:lite",
            gemini_model="lite",
            ollama_base_url="http://localhost:11434",
            ollama_model="qwen3:8b",
            last_error="Ollama unavailable",
        ),
        pending_retry_count=3,
    )

    assert "AI status" in text
    assert "gemini:lite -> ollama:qwen3:8b -> heuristic:heuristic" in text
    assert "Selected: gemini:lite" in text
    assert "Gemini model: lite" in text
    assert "Ollama: http://localhost:11434 (qwen3:8b)" in text
    assert "Pending retries: 3" in text
    assert "Last error: Ollama unavailable" in text
