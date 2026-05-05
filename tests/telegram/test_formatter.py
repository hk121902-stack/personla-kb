from dataclasses import replace
from datetime import UTC, datetime

from kb_agent.ai.router import AIStatusSnapshot
from kb_agent.core.archive_review import ArchiveRecommendation
from kb_agent.core.models import AIStatus, LearningBrief, Priority, SavedItem, SourceType, Status
from kb_agent.telegram.formatter import (
    format_ai_status,
    format_archive_recommendations,
    format_daily_digest,
    format_enrichment_retry_message,
    format_item_details,
    format_learning_brief,
    format_needs_text_prompt,
    format_pending_learning_brief,
    format_plain_text,
    format_retrieval_response,
    format_save_confirmation,
    format_weekly_digest,
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
            note="learn this for agent memory",
        ),
        title="RAG Notes",
        tags=["rag", "retrieval"],
        priority=Priority.HIGH,
        status=Status.READY,
    )

    text = format_save_confirmation(item)

    assert text.startswith('<b><a href="https://example.com/rag">RAG Notes</a></b>')
    assert "<b>ID:</b> kb_" in text
    assert "<b>Tags:</b> rag, retrieval" in text
    assert "<b>Priority:</b> high" in text
    assert "<b>Note:</b> learn this for agent memory" in text
    assert "Status: ready" not in text
    assert '<b>Need more?</b> Reply "details" or send details kb_' in text


def test_save_confirmation_omits_blank_note() -> None:
    item = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/rag",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        ),
        title="RAG Notes",
        tags=["rag"],
        status=Status.READY,
    )

    text = format_save_confirmation(item)

    assert "<b>Note:</b>" not in text


def test_save_confirmation_does_not_duplicate_note_as_summary() -> None:
    note = "learn this for agent memory"
    item = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/rag",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
            note=note,
        ),
        title="RAG Notes",
        summary="",
        status=Status.READY,
    )

    text = format_save_confirmation(item)

    assert f"<b>Note:</b> {note}" in text
    assert text.count(note) == 1


def test_needs_text_prompt_tells_user_to_save_note() -> None:
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/rag?a=1&b=2",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )

    text = format_needs_text_prompt(item)

    assert text == (
        "I saved the link, but could not extract text from: "
        "https://example.com/rag?a=1&amp;b=2\n"
        "Send the useful text and I will use it as saved content: "
        "save https://example.com/rag?a=1&amp;b=2 note: &lt;text&gt;"
    )


def test_format_plain_text_escapes_html() -> None:
    assert format_plain_text("A <raw> & text") == "A &lt;raw&gt; &amp; text"


def test_format_retrieval_response_escapes_html_fallbacks() -> None:
    response = type("Response", (), {"text": "From <kb> & notes"})()

    assert format_retrieval_response("A <raw> & text") == "A &lt;raw&gt; &amp; text"
    assert format_retrieval_response(response) == (
        "<b>From your knowledge base</b>\n"
        "From &lt;kb&gt; &amp; notes.\n"
        "\n"
        "<b>Sources</b>\n"
        "- No strong saved source match."
    )


def test_format_retrieval_response_show_mode_is_compact_list() -> None:
    item = replace(
        _item(),
        id="7f3a9b8c1234",
        title="Graphify + Claude Code",
        tags=["claude-code", "repos"],
        summary="A short summary. A hidden second sentence.",
    )
    response = type(
        "Response",
        (),
        {
            "question": "claude",
            "answer": "Long synthesized answer that should not show.",
            "matches": [item],
            "item_aliases": {item.id: "kb_7f3a"},
            "extra_context": "",
            "text": "legacy",
        },
    )()

    text = format_retrieval_response(response, mode="show", query="claude")

    assert '<b>Found 1 item for "claude"</b>' in text
    assert "Graphify + Claude Code" in text
    assert "Long synthesized answer" not in text
    assert '<b>Need more?</b> Reply "details" to an item, or send details kb_7f3a.' in text


def test_format_retrieval_response_show_mode_includes_compact_note() -> None:
    item = replace(
        _item(),
        id="7f3a9b8c1234",
        title="Graphify + Claude Code",
        tags=["claude-code", "repos"],
        user_note=(
            "compare this with my current repo workflow. "
            "This second sentence should stay hidden in compact cards."
        ),
        summary="A short summary.",
    )
    response = type(
        "Response",
        (),
        {
            "question": "claude",
            "answer": "Long synthesized answer that should not show.",
            "matches": [item],
            "item_aliases": {item.id: "kb_7f3a"},
            "extra_context": "",
            "text": "legacy",
        },
    )()

    text = format_retrieval_response(response, mode="show", query="claude")

    assert "<b>Note:</b> compare this with my current repo workflow." in text
    assert "This second sentence should stay hidden" not in text


def test_format_retrieval_response_show_mode_does_not_duplicate_note_as_summary() -> None:
    note = "compare this with my current repo workflow"
    item = replace(
        _item(),
        id="7f3a9b8c1234",
        title="Graphify + Claude Code",
        user_note=note,
        summary="",
    )
    response = type(
        "Response",
        (),
        {
            "question": "claude",
            "answer": "Long synthesized answer that should not show.",
            "matches": [item],
            "item_aliases": {item.id: "kb_7f3a"},
            "extra_context": "",
            "text": "legacy",
        },
    )()

    text = format_retrieval_response(response, mode="show", query="claude")

    assert f"<b>Note:</b> {note}" in text
    assert text.count(note) == 1


def test_compact_note_escapes_html() -> None:
    item = replace(
        _item(),
        id="7f3a9b8c1234",
        title="Escaped Note",
        user_note='Use <script> & "quotes". Hidden second sentence.',
        summary="A short summary.",
    )
    response = type(
        "Response",
        (),
        {
            "question": "escaped",
            "answer": "Answer.",
            "matches": [item],
            "item_aliases": {item.id: "kb_7f3a"},
            "extra_context": "",
            "text": "legacy",
        },
    )()

    text = format_retrieval_response(response, mode="show", query="escaped")

    assert '<b>Note:</b> Use &lt;script&gt; &amp; &quot;quotes&quot;.' in text


def test_format_retrieval_response_ask_mode_is_short_answer_with_sources() -> None:
    item = replace(_item(), id="7f3a9b8c1234", title="RAG Search")
    response = type(
        "Response",
        (),
        {
            "question": "what did I save?",
            "answer": "Sentence one. Sentence two. Sentence three should be hidden.",
            "matches": [item],
            "item_aliases": {item.id: "kb_7f3a"},
            "extra_context": "",
            "text": "legacy",
        },
    )()

    text = format_retrieval_response(response, mode="ask")

    assert "<b>From your knowledge base</b>" in text
    assert "Sentence three should be hidden" not in text
    assert "<b>Sources</b>" in text
    assert "RAG Search" in text
    assert "Extra context" not in text


def test_format_retrieval_response_uses_provided_alias_for_non_hex_ids() -> None:
    item = replace(
        _item(),
        id="item-a",
        title="Imported Item",
        summary="Imported summary. Hidden second sentence.",
    )
    response = type(
        "Response",
        (),
        {
            "question": "imported",
            "answer": "Imported answer. Hidden second sentence.",
            "matches": [item],
            "item_aliases": {item.id: "kb_custom"},
            "extra_context": "",
            "text": "legacy",
        },
    )()

    show_text = format_retrieval_response(response, mode="show", query="imported")
    ask_text = format_retrieval_response(response, mode="ask")

    assert "kb_custom" in show_text
    assert "kb_custom" in ask_text


def test_format_daily_digest_escapes_legacy_text() -> None:
    digest = type("Digest", (), {"text": "Daily <digest> & notes"})()

    assert format_daily_digest("Raw <digest> & notes") == "Raw &lt;digest&gt; &amp; notes"
    assert format_daily_digest(digest) == "Daily &lt;digest&gt; &amp; notes"


def test_format_daily_digest_uses_compact_cards() -> None:
    item = replace(_item(), id="7f3a9b8c1234", title="Daily Item", tags=["ai"])
    digest = type(
        "Digest",
        (),
        {
            "text": "legacy",
            "items": [item],
            "item_aliases": {item.id: "kb_7f3a"},
            "kind": "today",
        },
    )()

    text = format_daily_digest(digest)

    assert "<b>Daily tiny nudge</b>" in text
    assert "Daily Item" in text
    assert "<b>ID:</b> kb_7f3a" in text
    assert "Need more?" in text


def test_format_weekly_digest_groups_by_topic_compactly() -> None:
    item = replace(_item(), id="7f3a9b8c1234", title="Weekly Item", topic="AI Tools")
    digest = type(
        "Digest",
        (),
        {
            "text": "legacy",
            "items": [item],
            "item_aliases": {item.id: "kb_7f3a"},
            "kind": "week",
        },
    )()

    text = format_weekly_digest(digest)

    assert "<b>Weekly synthesis</b>" in text
    assert "<b>AI Tools</b>" in text
    assert "Weekly Item" in text


def test_format_archive_recommendations_escapes_html() -> None:
    item = replace(
        _item(),
        id="7f3a9b8c1234",
        title="Old <Link> & More",
    )

    text = format_archive_recommendations(
        [ArchiveRecommendation(item=item, reason="old <low> & stale")],
        alias_for_item=lambda _: "kb_<7f3a>&",
    )

    assert "<b>Archive recommendations</b>" in text
    assert "ID: kb_&lt;7f3a&gt;&amp;" in text
    assert "Old &lt;Link&gt; &amp; More" in text
    assert "Reason: old &lt;low&gt; &amp; stale" in text


def test_format_archive_recommendations_is_html_compact() -> None:
    item = replace(_item(), id="7f3a9b8c1234", title="Old Link")
    recommendation = ArchiveRecommendation(item=item, reason="old_low_priority")

    text = format_archive_recommendations([recommendation])

    assert "<b>Archive recommendations</b>" in text
    assert "ID: kb_7f3a" in text
    assert "old_low_priority" in text
    assert "https://example.com/brief" not in text


def test_format_archive_recommendations_uses_non_url_label_when_title_missing() -> None:
    item = replace(_item(), id="7f3a9b8c1234", title="")
    recommendation = ArchiveRecommendation(item=item, reason="old_low_priority")

    text = format_archive_recommendations([recommendation])

    assert "<b>kb_7f3a</b>" in text
    assert "ID: kb_7f3a" in text
    assert "https://example.com/brief" not in text


def test_format_learning_brief_is_compact_html_card() -> None:
    text = format_learning_brief(_item())

    assert text.startswith('<b><a href="https://example.com/brief">Learning Brief</a></b>')
    assert "<b>ID:</b> kb_7f3a" in text
    assert "<b>Tags:</b> gemini, claude, agents, repos, costs" in text
    assert "<b>Priority:</b> unset · 20 min" in text
    assert "This second sentence should be hidden" not in text
    assert "Key takeaways:" not in text
    assert '<b>Need more?</b> Reply "details" or send details kb_7f3a.' in text


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
    item = replace(_item(), title="Learning <Brief> & More")

    assert format_pending_learning_brief(item, alias="kb_<7f3a>&") == (
        "Saved: Learning &lt;Brief&gt; &amp; More\n"
        "<b>ID:</b> kb_&lt;7f3a&gt;&amp;\n"
        "Preparing learning brief..."
    )


def test_format_enrichment_retry_message_includes_alias() -> None:
    assert format_enrichment_retry_message(_item(), alias="kb_<7f3a>&") == (
        "Saved with basic enrichment. AI brief is pending retry.\n"
        "<b>ID:</b> kb_&lt;7f3a&gt;&amp;"
    )


def test_format_ai_status() -> None:
    text = format_ai_status(
        AIStatusSnapshot(
            chain=["gemini:lite", "ollama:qwen3:8b", "heuristic:heuristic"],
            selected_model="gemini:<lite>&",
            gemini_model="lite",
            ollama_base_url="http://localhost:11434",
            ollama_model="qwen3:8b",
            last_error="Ollama <unavailable> & retry",
        ),
        pending_retry_count=3,
    )

    assert "AI status" in text
    assert "gemini:lite -> ollama:qwen3:8b -> heuristic:heuristic" in text
    assert "Selected: gemini:&lt;lite&gt;&amp;" in text
    assert "Gemini model: lite" in text
    assert "Ollama: http://localhost:11434 (qwen3:8b)" in text
    assert "Pending retries: 3" in text
    assert "Last error: Ollama &lt;unavailable&gt; &amp; retry" in text
