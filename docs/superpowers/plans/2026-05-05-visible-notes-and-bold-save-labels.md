# Visible Notes And Bold Save Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show saved notes in compact Telegram cards/details and bold the key metadata labels in save-style responses.

**Architecture:** Keep the change in the Telegram presentation layer. `SavedItem.user_note` is already parsed, persisted, and used by retrieval, so this plan only updates formatter output and Telegram adapter expectations. Add small formatter helpers for bold labels and compact note rendering, then reuse them across save cards, retrieval cards, pending/retry save states, and details.

**Tech Stack:** Python 3.12, pytest, python-telegram-bot HTML parse mode, existing `kb_agent.telegram.formatter` helpers.

---

## File Structure

- `src/kb_agent/telegram/formatter.py`
  - Owns Telegram HTML presentation.
  - Add helpers for bold labels and note lines.
  - Update existing formatter functions without changing parser/service/storage behavior.
- `tests/telegram/test_formatter.py`
  - Unit coverage for exact formatter output, HTML escaping, compact note behavior, blank-note omission, and full details note.
- `tests/telegram/test_bot_adapter.py`
  - Adapter-level coverage that saved-link messages visibly include notes and bold labels.

Do not modify:

- `src/kb_agent/telegram/parser.py`: note parsing remains unchanged.
- `src/kb_agent/core/service.py`: note storage already works.
- `src/kb_agent/extraction/extractors.py`, `tests/extraction/test_extractors.py`, `.env`: these are pre-existing dirty files and must not be touched in this slice.

---

### Task 1: Bold Labels And Visible Notes In Compact Cards

**Files:**
- Modify: `src/kb_agent/telegram/formatter.py`
- Test: `tests/telegram/test_formatter.py`

- [ ] **Step 1: Write failing formatter tests for save cards and show/find cards**

In `tests/telegram/test_formatter.py`, update `test_save_confirmation_is_compact` so the item has a note and the assertions expect bold labels:

```python
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
```

Add this test below `test_save_confirmation_is_compact`:

```python
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
```

Add this test after `test_format_retrieval_response_show_mode_is_compact_list`:

```python
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
```

Add this escaping test after the new show-mode note test:

```python
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
```

- [ ] **Step 2: Run formatter tests to verify failure**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/telegram/test_formatter.py::test_save_confirmation_is_compact tests/telegram/test_formatter.py::test_save_confirmation_omits_blank_note tests/telegram/test_formatter.py::test_format_retrieval_response_show_mode_includes_compact_note tests/telegram/test_formatter.py::test_compact_note_escapes_html -q
```

Expected: FAIL because the formatter still emits plain labels and does not render a visible compact `Note:` line.

- [ ] **Step 3: Implement formatter helpers and compact card note rendering**

In `src/kb_agent/telegram/formatter.py`, add these helpers near `_tag_line`:

```python
def _label(name: str) -> str:
    return f"<b>{_html(name)}:</b>"


def _labeled_line(name: str, value: object) -> str:
    return f"{_label(name)} {_html(value)}"


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


def _detail_hint(alias: str) -> str:
    return f'{_label("Need more")} Reply "details" or send details {_html(alias)}.'
```

Replace the existing `_tag_line` and `_detail_hint` implementations with the helper block in this step.

In `format_save_confirmation`, build metadata lines with bold labels and insert the note line only when present:

```python
def format_save_confirmation(item: SavedItem, *, alias: str | None = None) -> str:
    title = item.title or item.url
    alias = alias or alias_for_item_id(item.id)
    summary = _compact_summary(item.summary or item.user_note or title)
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
```

In `_compact_item_card`, include the compact note line after tags:

```python
def _compact_item_card(item: SavedItem, *, alias: str) -> str:
    title = item.title or item.url
    summary = _compact_summary(item.summary or item.user_note or item.extracted_text or title)
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
```

Update these existing label lines in the same file:

```python
f"ID: {_html(alias)}"
```

to:

```python
_labeled_line("ID", alias)
```

and update:

```python
f"Priority: {_html(item.priority.value)} · {_html(brief.estimated_time_minutes)} min"
```

to:

```python
f"{_label('Priority')} {_html(item.priority.value)} · {_html(brief.estimated_time_minutes)} min"
```

Do this in compact save/card contexts in `format_learning_brief`, `format_pending_learning_brief`, and `format_enrichment_retry_message`.

- [ ] **Step 4: Run formatter tests to verify pass**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/telegram/test_formatter.py -q
```

Expected: PASS after updating existing assertions in this file from plain labels to bold labels, for example:

```python
assert "<b>ID:</b> kb_7f3a" in text
assert "<b>Tags:</b> gemini, claude, agents, repos, costs" in text
assert "<b>Priority:</b> unset · 20 min" in text
assert '<b>Need more?</b> Reply "details" or send details kb_7f3a.' in text
```

- [ ] **Step 5: Commit compact formatter slice**

```bash
git add src/kb_agent/telegram/formatter.py tests/telegram/test_formatter.py
git commit -m "feat: show notes in compact telegram cards"
```

---

### Task 2: Full Notes In Details View

**Files:**
- Modify: `src/kb_agent/telegram/formatter.py`
- Test: `tests/telegram/test_formatter.py`

- [ ] **Step 1: Write failing details tests**

Update `test_format_item_details_includes_full_brief` in `tests/telegram/test_formatter.py`:

```python
def test_format_item_details_includes_full_brief() -> None:
    item = replace(_item(), user_note="Remember this for weekly agent planning.")

    text = format_item_details(item)

    assert "<b>Details</b>" in text
    assert "<b>ID:</b> kb_7f3a" in text
    assert "<b>Note</b>" in text
    assert "Remember this for weekly agent planning." in text
    assert "Key takeaways:" in text
    assert "- Takeaway one." in text
    assert "Why it matters:" in text
    assert "Source: https://example.com/brief" in text
```

Add this test below it:

```python
def test_format_item_details_omits_blank_note_section() -> None:
    text = format_item_details(_item())

    assert "<b>Note</b>" not in text
```

Add this escaping test below the blank-note test:

```python
def test_format_item_details_escapes_note() -> None:
    item = replace(_item(), user_note='Use <raw> & "quoted" note.')

    text = format_item_details(item)

    assert "Use &lt;raw&gt; &amp; &quot;quoted&quot; note." in text
```

- [ ] **Step 2: Run details tests to verify failure**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/telegram/test_formatter.py::test_format_item_details_includes_full_brief tests/telegram/test_formatter.py::test_format_item_details_omits_blank_note_section tests/telegram/test_formatter.py::test_format_item_details_escapes_note -q
```

Expected: FAIL because `format_item_details` does not render a note section yet.

- [ ] **Step 3: Implement full note section**

In `src/kb_agent/telegram/formatter.py`, update `format_item_details` so the metadata labels are bold and the full note appears before summary:

```python
def format_item_details(item: SavedItem, *, alias: str | None = None) -> str:
    alias = _alias_or_item_id(item, alias)
    brief = item.learning_brief
    title = brief.title if brief is not None else item.title or item.url
    summary = brief.summary if brief is not None else item.summary
    lines = [
        "<b>Details</b>",
        f"<b>{_title_link(title, item.url)}</b>",
        _labeled_line("ID", alias),
        _tag_line(brief.tags if brief is not None else item.tags),
        _labeled_line("Priority", item.priority.value),
        f"{_label('Source')} {_html(item.url)}",
    ]
    if item.user_note.strip():
        lines.extend(["", "<b>Note</b>", _html(item.user_note.strip())])
    lines.extend(
        [
            "",
            "<b>Summary</b>",
            _html(summary or title),
        ],
    )
    if brief is not None:
        lines.extend(["", "<b>Key takeaways:</b>"])
        lines.extend(f"- {_html(takeaway)}" for takeaway in brief.key_takeaways)
        lines.extend(
            [
                "",
                "<b>Why it matters:</b>",
                _html(brief.why_it_matters),
                "",
                f"{_label('Time')} {_html(brief.estimated_time_minutes)} min",
                f"{_label('Next')} {_html(brief.suggested_next_action)}",
            ],
        )
    return "\n".join(line for line in lines if line != "")
```

- [ ] **Step 4: Run formatter tests**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/telegram/test_formatter.py -q
```

Expected: PASS after any remaining old plain-label assertions in this file are updated to bold-label assertions.

- [ ] **Step 5: Commit details note slice**

```bash
git add src/kb_agent/telegram/formatter.py tests/telegram/test_formatter.py
git commit -m "feat: show saved notes in details"
```

---

### Task 3: Telegram Adapter Expectations And Full Verification

**Files:**
- Test: `tests/telegram/test_bot_adapter.py`
- Modify: `src/kb_agent/telegram/formatter.py`

- [ ] **Step 1: Write failing adapter expectations for visible save notes and bold labels**

Update `_assert_compact_card` in `tests/telegram/test_bot_adapter.py`:

```python
def _assert_compact_card(
    text: str,
    *,
    title: str,
    url: str = "https://example.com/rag",
    alias: str | None = None,
    tags: str = "saved",
) -> None:
    assert text.startswith(f'<b><a href="{url}">{title}</a></b>')
    if alias is None:
        assert "<b>ID:</b> kb_" in text
        assert '<b>Need more?</b> Reply "details" or send details kb_' in text
    else:
        assert f"<b>ID:</b> {alias}" in text
        assert f'<b>Need more?</b> Reply "details" or send details {alias}.' in text
    assert f"<b>Tags:</b> {tags}" in text
    assert "<b>Priority:</b> unset" in text
```

Update `test_handler_note_save_uses_split_enrichment_for_split_knowledge` to assert the note is visible:

```python
@pytest.mark.asyncio
async def test_handler_note_save_uses_split_enrichment_for_split_knowledge() -> None:
    replies = []
    knowledge = RecordingSplitKnowledge()
    handler = TelegramMessageHandler(
        knowledge=knowledge,
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="save https://example.com/rag note: manual text",
        reply=replies.append,
    )

    assert knowledge.save_link_calls == []
    assert knowledge.create_link_calls == [
        {
            "user_id": "telegram:123",
            "url": "https://example.com/rag",
            "note": "manual text",
            "priority": Priority.UNSET,
        },
    ]
    assert knowledge.enrich_saved_item_calls == [
        {"user_id": "telegram:123", "item_id": "7f3a9b8c1234"},
    ]
    _assert_compact_card(replies[0], title="Finished Brief", alias="kb_7f3a")
    assert "<b>Note:</b> manual text" in replies[0]
```

Update exact string assertions for pending/retry save states to bold `ID`:

```python
assert replies[0] == (
    "Saved: https://example.com/rag\n"
    "<b>ID:</b> kb_7f3a\n"
    "Preparing learning brief..."
)
```

and:

```python
assert replies == [
    (
        "Saved with basic enrichment. AI brief is pending retry.\n"
        "<b>ID:</b> kb_7f3a"
    ),
]
```

- [ ] **Step 2: Run adapter tests to verify failure**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/telegram/test_bot_adapter.py -q
```

Expected: FAIL until every old plain-label assertion in the adapter tests is updated and the note is visible in enriched save replies.

- [ ] **Step 3: Ensure enriched learning brief cards include notes**

In `src/kb_agent/telegram/formatter.py`, replace `format_learning_brief` with this implementation so enriched save replies show the note after tags and before priority:

```python
def format_learning_brief(item: SavedItem, *, alias: str | None = None) -> str:
    brief = item.learning_brief
    if brief is None:
        return format_save_confirmation(item, alias=alias)

    alias = _alias_or_item_id(item, alias)
    summary = _compact_summary(brief.summary)
    lines = [
        f"<b>{_title_link(brief.title, item.url)}</b>",
        _labeled_line("ID", alias),
        _tag_line(brief.tags),
    ]
    note_line = _compact_note_line(item.user_note)
    if note_line:
        lines.append(note_line)
    lines.extend(
        [
            f"{_label('Priority')} {_html(item.priority.value)} · {_html(brief.estimated_time_minutes)} min",
            "",
            _html(summary),
            "",
            _detail_hint(alias),
        ],
    )
    return "\n".join(lines)
```

- [ ] **Step 4: Run focused Telegram tests**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/telegram -q
```

Expected: PASS.

- [ ] **Step 5: Run full verification**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest -q
/private/tmp/personal-kb-agent-venv/bin/ruff check .
git diff --check
```

Expected:

```text
All tests pass.
All checks passed!
git diff --check prints no output.
```

- [ ] **Step 6: Commit adapter and verification slice**

```bash
git add src/kb_agent/telegram/formatter.py tests/telegram/test_bot_adapter.py
git commit -m "test: align telegram adapter with visible notes"
```

---

## Manual Smoke

After implementation, run the bot:

```bash
cd "/Users/himanshu.sin/Documents/New project/.worktrees/personal-kb-agent"
/private/tmp/personal-kb-agent-venv/bin/python -m kb_agent.app
```

In Telegram, send:

```text
https://example.com/article note: learn this for agent memory priority: low
```

Expected response includes:

```text
<b>ID:</b>
<b>Tags:</b>
<b>Priority:</b> low
<b>Note:</b> learn this for agent memory
<b>Need more?</b>
```

Then send:

```text
show agent memory
```

Expected: the matching compact card includes `<b>Note:</b> learn this for agent memory`.

Then send:

```text
details
```

Expected: the details view includes:

```text
<b>Note</b>
learn this for agent memory
```
