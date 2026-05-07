# Telegram Compact Responses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Telegram responses compact, HTML-formatted, and expandable through a `details` flow.

**Architecture:** Keep retrieval, digest selection, and persistence responsibilities where they are, but make Telegram rendering own the compact presentation. Add parser support for `details` and `find`, add repository/service helpers for latest-item lookup and detail retrieval, and render save/show/ask/digest/archive responses through shared formatter helpers.

**Tech Stack:** Python 3.12, python-telegram-bot, SQLite, pytest, ruff.

---

## File Structure

- Modify: `src/kb_agent/telegram/parser.py` - parse `DetailsCommand` and `find` alias.
- Modify: `src/kb_agent/telegram/formatter.py` - Telegram HTML presentation helpers, compact cards, detail view, compact retrieval/digest/archive rendering.
- Modify: `src/kb_agent/telegram/bot.py` - details command handling, reply-to-message ID extraction, HTML parse mode wiring.
- Modify: `src/kb_agent/core/ports.py` - add latest saved item repository protocol method.
- Modify: `src/kb_agent/storage/sqlite.py` - implement latest saved item lookup.
- Modify: `src/kb_agent/core/service.py` - expose item detail and latest item methods.
- Modify: `src/kb_agent/core/retrieval.py` - return structured retrieval data and suppress extra context by default.
- Modify: `src/kb_agent/core/digests.py` - keep selection logic, reduce weekly limit to 5, carry aliases for formatter use.
- Modify: `src/kb_agent/ai/briefs.py` - strengthen prompt summary constraints.
- Modify tests under `tests/telegram`, `tests/core`, `tests/storage`, and `tests/ai`.

Do not stage unrelated uncommitted files. At plan creation time, `src/kb_agent/extraction/extractors.py`, `tests/extraction/test_extractors.py`, and `.env` are dirty and out of scope for this plan.

---

### Task 1: Parse Details And Find Commands

**Files:**
- Modify: `src/kb_agent/telegram/parser.py`
- Test: `tests/telegram/test_parser.py`

- [ ] **Step 1: Write failing parser tests**

Add these imports in `tests/telegram/test_parser.py`:

```python
from kb_agent.telegram.parser import DetailsCommand
```

Add these tests:

```python
def test_details_command_with_item_ref() -> None:
    command = parse_message("details kb_7f3a")

    assert isinstance(command, DetailsCommand)
    assert command.item_ref == "kb_7f3a"


def test_plain_details_command_has_empty_ref() -> None:
    command = parse_message("details")

    assert isinstance(command, DetailsCommand)
    assert command.item_ref == ""


def test_more_and_expand_are_details_aliases() -> None:
    more = parse_message("more")
    expand = parse_message("expand kb_9c11")

    assert isinstance(more, DetailsCommand)
    assert more.item_ref == ""
    assert isinstance(expand, DetailsCommand)
    assert expand.item_ref == "kb_9c11"


def test_find_command_reuses_show_command() -> None:
    command = parse_message("find claude code")

    assert isinstance(command, ShowCommand)
    assert command.query == "claude code"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/telegram/test_parser.py -q
```

Expected: FAIL because `DetailsCommand` does not exist and `find` parses as `AskCommand`.

- [ ] **Step 3: Implement parser support**

In `src/kb_agent/telegram/parser.py`, add:

```python
@dataclass(frozen=True)
class DetailsCommand:
    item_ref: str
```

Add `DetailsCommand` to the `parse_message` return union.

Inside `parse_message`, after archive handling and before show handling, add:

```python
    if lowered == "details" or lowered.startswith("details "):
        return DetailsCommand(item_ref=_after_command(text))
    if lowered == "more" or lowered.startswith("more "):
        return DetailsCommand(item_ref=_after_command(text))
    if lowered == "expand" or lowered.startswith("expand "):
        return DetailsCommand(item_ref=_after_command(text))
    if lowered == "find" or lowered.startswith("find "):
        return ShowCommand(query=_after_command(text))
```

- [ ] **Step 4: Run parser tests**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/telegram/test_parser.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit parser slice**

```bash
git add src/kb_agent/telegram/parser.py tests/telegram/test_parser.py
git commit -m "feat: parse details and find commands"
```

---

### Task 2: Add Latest Item And Detail Retrieval Helpers

**Files:**
- Modify: `src/kb_agent/core/ports.py`
- Modify: `src/kb_agent/storage/sqlite.py`
- Modify: `src/kb_agent/core/service.py`
- Test: `tests/storage/test_sqlite_repository.py`
- Test: `tests/core/test_knowledge_service.py`

- [ ] **Step 1: Write failing storage tests**

Add tests to `tests/storage/test_sqlite_repository.py`:

```python
from dataclasses import replace
from datetime import UTC, datetime

from kb_agent.core.models import SavedItem, SourceType
from kb_agent.storage.sqlite import SQLiteItemRepository


def _latest_test_item(item_id: str, user_id: str, created_at: datetime) -> SavedItem:
    return replace(
        SavedItem.new(
            user_id=user_id,
            url=f"https://example.com/{item_id}",
            source_type=SourceType.WEB,
            now=created_at,
        ),
        id=item_id,
        title=item_id,
    )


def test_latest_by_user_returns_newest_active_item(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    older = _latest_test_item("older1234", "telegram:123", datetime(2026, 5, 3, 9, tzinfo=UTC))
    newer = _latest_test_item("newer1234", "telegram:123", datetime(2026, 5, 3, 10, tzinfo=UTC))
    other_user = _latest_test_item("other1234", "telegram:999", datetime(2026, 5, 3, 11, tzinfo=UTC))
    repo.save(older)
    repo.save(newer)
    repo.save(other_user)

    assert repo.latest_by_user("telegram:123").id == "newer1234"


def test_latest_by_user_excludes_archived_by_default(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    active = _latest_test_item("active1234", "telegram:123", datetime(2026, 5, 3, 9, tzinfo=UTC))
    archived = replace(
        _latest_test_item("archived1234", "telegram:123", datetime(2026, 5, 3, 10, tzinfo=UTC)),
        archived=True,
        archived_at=datetime(2026, 5, 3, 11, tzinfo=UTC),
    )
    repo.save(active)
    repo.save(archived)

    assert repo.latest_by_user("telegram:123").id == "active1234"
    assert repo.latest_by_user("telegram:123", include_archived=True).id == "archived1234"
```

- [ ] **Step 2: Run storage tests to verify failure**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/storage/test_sqlite_repository.py::test_latest_by_user_returns_newest_active_item tests/storage/test_sqlite_repository.py::test_latest_by_user_excludes_archived_by_default -q
```

Expected: FAIL because `latest_by_user` is not implemented.

- [ ] **Step 3: Implement repository protocol and SQLite helper**

In `src/kb_agent/core/ports.py`, add to `ItemRepository`:

```python
    def latest_by_user(
        self,
        user_id: str,
        *,
        include_archived: bool = False,
    ) -> SavedItem | None: ...
```

In `src/kb_agent/storage/sqlite.py`, add this method inside `SQLiteItemRepository`:

```python
    def latest_by_user(
        self,
        user_id: str,
        *,
        include_archived: bool = False,
    ) -> SavedItem | None:
        if include_archived:
            sql = (
                "SELECT * FROM saved_items WHERE user_id = ? "
                "ORDER BY created_at DESC, id DESC LIMIT 1"
            )
            parameters = (user_id,)
        else:
            sql = (
                "SELECT * FROM saved_items WHERE user_id = ? AND archived = 0 "
                "ORDER BY created_at DESC, id DESC LIMIT 1"
            )
            parameters = (user_id,)

        with closing(self._connect()) as connection:
            with connection:
                row = connection.execute(sql, parameters).fetchone()

        if row is None:
            return None
        return self._from_row(row)
```

- [ ] **Step 4: Run storage tests**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/storage/test_sqlite_repository.py::test_latest_by_user_returns_newest_active_item tests/storage/test_sqlite_repository.py::test_latest_by_user_excludes_archived_by_default -q
```

Expected: PASS.

- [ ] **Step 5: Write failing service tests**

Add `SourceType` to the existing `kb_agent.core.models` import in `tests/core/test_knowledge_service.py`.

Add tests to `tests/core/test_knowledge_service.py`:

```python
def test_get_item_resolves_alias(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(None),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )
    item = service.create_link(
        user_id="telegram:123",
        url="https://example.com/detail",
    )
    alias = service.repository.item_alias("telegram:123", item.id)

    found = service.get_item(user_id="telegram:123", item_ref=alias)

    assert found.id == item.id


def test_latest_item_returns_latest_user_item(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(None),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )
    older = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/older",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, tzinfo=UTC),
        ),
        id="older1234",
    )
    newer = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/newer",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 10, tzinfo=UTC),
        ),
        id="newer1234",
    )
    repo.save(older)
    repo.save(newer)

    found = service.latest_item(user_id="telegram:123")

    assert found.id == newer.id
    assert found.id != older.id
```

- [ ] **Step 6: Run service tests to verify failure**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/core/test_knowledge_service.py::test_get_item_resolves_alias tests/core/test_knowledge_service.py::test_latest_item_returns_latest_user_item -q
```

Expected: FAIL because `get_item` and `latest_item` are not implemented.

- [ ] **Step 7: Implement service helpers**

In `src/kb_agent/core/service.py`, add public methods to `KnowledgeService`:

```python
    def get_item(self, *, user_id: str, item_ref: str) -> SavedItem:
        item_id = self.resolve_item_ref(user_id=user_id, item_ref=item_ref)
        return self._get_user_item(user_id=user_id, item_id=item_id)

    def latest_item(self, *, user_id: str) -> SavedItem:
        item = self.repository.latest_by_user(user_id)
        if item is None:
            raise ValueError("Saved item not found")
        return item
```

- [ ] **Step 8: Run storage and service tests**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/storage/test_sqlite_repository.py tests/core/test_knowledge_service.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit latest/detail slice**

```bash
git add src/kb_agent/core/ports.py src/kb_agent/storage/sqlite.py src/kb_agent/core/service.py tests/storage/test_sqlite_repository.py tests/core/test_knowledge_service.py
git commit -m "feat: resolve latest saved item details"
```

---

### Task 3: Build Compact HTML Formatting

**Files:**
- Modify: `src/kb_agent/telegram/formatter.py`
- Test: `tests/telegram/test_formatter.py`

- [ ] **Step 1: Write failing formatter tests**

Update `_brief()` in `tests/telegram/test_formatter.py` so the summary is intentionally long:

```python
summary=(
    "This is a long summary sentence about a useful saved item. "
    "This second sentence should be hidden from compact Telegram cards. "
    "This third sentence should only appear in details."
),
tags=["gemini", "claude", "agents", "repos", "costs", "extra"],
```

Add tests:

```python
from kb_agent.telegram.formatter import format_item_details


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
```

- [ ] **Step 2: Run formatter tests to verify failure**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/telegram/test_formatter.py -q
```

Expected: FAIL because formatting is plain text and `format_item_details` does not exist.

- [ ] **Step 3: Implement compact formatter helpers**

In `src/kb_agent/telegram/formatter.py`, add imports:

```python
from html import escape
from urllib.parse import urlparse
```

Add constants and helpers:

```python
_SUMMARY_SENTENCE_LIMIT = 2
_SUMMARY_CHAR_LIMIT = 220
_TAG_LIMIT = 5


def _html(text: object) -> str:
    return escape(str(text), quote=True)


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


def _tag_line(tags: Sequence[str]) -> str:
    selected = [tag for tag in tags if tag.strip()][:_TAG_LIMIT]
    if not selected:
        return "Tags: none"
    return "Tags: " + ", ".join(_html(tag) for tag in selected)


def _detail_hint(alias: str) -> str:
    return f'Need more? Reply "details" or send details {_html(alias)}.'
```

Add a public detail formatter:

```python
def format_item_details(item: SavedItem, *, alias: str | None = None) -> str:
    alias = alias or alias_for_item_id(item.id)
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
        lines.extend(["", "<b>Key takeaways</b>"])
        lines.extend(f"- {_html(takeaway)}" for takeaway in brief.key_takeaways)
        lines.extend(
            [
                "",
                "<b>Why it matters</b>",
                _html(brief.why_it_matters),
                "",
                f"Time: {_html(brief.estimated_time_minutes)} min",
                f"Next: {_html(brief.suggested_next_action)}",
            ],
        )
    return "\n".join(line for line in lines if line != "")
```

Update `format_learning_brief`:

```python
def format_learning_brief(item: SavedItem, *, alias: str | None = None) -> str:
    brief = item.learning_brief
    if brief is None:
        return format_save_confirmation(item, alias=alias)

    alias = alias or alias_for_item_id(item.id)
    summary = _compact_summary(brief.summary)
    return "\n".join(
        [
            f"<b>{_title_link(brief.title, item.url)}</b>",
            f"ID: {_html(alias)}",
            _tag_line(brief.tags),
            f"Priority: {_html(item.priority.value)} · {_html(brief.estimated_time_minutes)} min",
            "",
            _html(summary),
            "",
            _detail_hint(alias),
        ],
    )
```

Update `format_save_confirmation` to match compact card style for items without a brief:

```python
def format_save_confirmation(item: SavedItem, *, alias: str | None = None) -> str:
    title = item.title or item.url
    alias = alias or alias_for_item_id(item.id)
    summary = _compact_summary(item.summary or item.user_note or title)
    lines = [
        f"<b>{_title_link(title, item.url)}</b>",
        f"ID: {_html(alias)}",
        _tag_line(item.tags),
        f"Priority: {_html(item.priority.value)}",
    ]
    if summary:
        lines.extend(["", _html(summary)])
    lines.extend(["", _detail_hint(alias)])
    return "\n".join(lines)
```

- [ ] **Step 4: Run formatter tests**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/telegram/test_formatter.py -q
```

Expected: PASS after updating old assertions to compact HTML output.

- [ ] **Step 5: Commit formatter slice**

```bash
git add src/kb_agent/telegram/formatter.py tests/telegram/test_formatter.py
git commit -m "feat: render compact telegram cards"
```

---

### Task 4: Send Telegram Messages With HTML Parse Mode

**Files:**
- Modify: `src/kb_agent/telegram/bot.py`
- Test: `tests/telegram/test_bot_adapter.py`

- [ ] **Step 1: Write failing parse-mode test**

Update `RecordingMessage.reply_text` in `tests/telegram/test_bot_adapter.py`:

```python
    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append(text)
        self.reply_kwargs = kwargs
```

Add this test:

```python
@pytest.mark.asyncio
async def test_application_replies_with_html_parse_mode() -> None:
    handler = RecordingTelegramHandler()
    application = build_application(handler, "token", allowed_chat_id="123")
    update, message = _text_update(chat_id=123, text="hello")

    await _message_callback(application)(update, None)

    assert message.replies == ["handled"]
    assert message.reply_kwargs["parse_mode"] == "HTML"
    assert message.reply_kwargs["disable_web_page_preview"] is True
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/telegram/test_bot_adapter.py::test_application_replies_with_html_parse_mode -q
```

Expected: FAIL because `reply_text` is called without parse-mode kwargs.

- [ ] **Step 3: Implement HTML reply wrapper**

In `src/kb_agent/telegram/bot.py`, inside `build_application.handle_update`, replace the direct `reply=update.message.reply_text` usage with:

```python
        async def html_reply(text: str) -> None:
            await update.message.reply_text(
                text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )

        await handler.handle_text(
            user_id=user_id,
            text=update.message.text,
            reply=html_reply,
            reply_to_text=_reply_to_text(update),
        )
```

Add helper near `_chat_scoped_user_id`:

```python
def _reply_to_text(update: Update) -> str | None:
    message = update.message
    if message is None:
        return None
    reply_to_message = getattr(message, "reply_to_message", None)
    if reply_to_message is None:
        return None
    text = getattr(reply_to_message, "text", None)
    if not isinstance(text, str):
        return None
    return text
```

Update `TelegramMessageHandler.handle_text` signature:

```python
    async def handle_text(
        self,
        *,
        user_id: str,
        text: str,
        reply: Reply,
        reply_to_text: str | None = None,
    ) -> None:
```

No existing tests need `reply_to_text`, because it defaults to `None`.

- [ ] **Step 4: Run bot adapter parse-mode test**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/telegram/test_bot_adapter.py::test_application_replies_with_html_parse_mode -q
```

Expected: PASS.

- [ ] **Step 5: Commit parse-mode slice**

```bash
git add src/kb_agent/telegram/bot.py tests/telegram/test_bot_adapter.py
git commit -m "feat: send telegram html messages"
```

---

### Task 5: Implement Details Command Behavior

**Files:**
- Modify: `src/kb_agent/telegram/bot.py`
- Modify: `src/kb_agent/telegram/formatter.py`
- Test: `tests/telegram/test_bot_adapter.py`
- Test: `tests/telegram/test_formatter.py`

- [ ] **Step 1: Write failing details adapter tests**

Add methods to `FakeKnowledge`:

```python
    async def get_item(self, *, user_id, item_ref):
        if item_ref == "missing":
            raise ValueError("missing")
        return replace(_saved_item(title="Detailed Item"), id="7f3a9b8c1234")

    async def latest_item(self, *, user_id):
        return replace(_saved_item(title="Latest Item"), id="9c11aaaa1234")
```

Add tests:

```python
@pytest.mark.asyncio
async def test_handler_sends_details_by_alias() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="details kb_7f3a",
        reply=replies.append,
    )

    assert "<b>Details</b>" in replies[0]
    assert "Detailed Item" in replies[0]


@pytest.mark.asyncio
async def test_handler_sends_details_from_replied_message_id() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="more",
        reply=replies.append,
        reply_to_text="<b>Saved Item</b>\nID: kb_7f3a",
    )

    assert "<b>Details</b>" in replies[0]
    assert "Detailed Item" in replies[0]


@pytest.mark.asyncio
async def test_handler_plain_details_uses_latest_item() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="details",
        reply=replies.append,
    )

    assert "Latest Item" in replies[0]


@pytest.mark.asyncio
async def test_handler_details_reports_missing_item() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="details missing",
        reply=replies.append,
    )

    assert replies == ["I could not find that saved item."]
```

- [ ] **Step 2: Run details tests to verify failure**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/telegram/test_bot_adapter.py::test_handler_sends_details_by_alias tests/telegram/test_bot_adapter.py::test_handler_sends_details_from_replied_message_id tests/telegram/test_bot_adapter.py::test_handler_plain_details_uses_latest_item tests/telegram/test_bot_adapter.py::test_handler_details_reports_missing_item -q
```

Expected: FAIL because `DetailsCommand` is not handled.

- [ ] **Step 3: Implement details handler**

In `src/kb_agent/telegram/bot.py`, import `DetailsCommand` and `format_item_details`.

Add regex import:

```python
import re
```

Add module constant:

```python
_ITEM_ID_RE = re.compile(r"\bID:\s*(kb_[a-z0-9]+)\b", re.IGNORECASE)
```

In `handle_text`, before `DigestCommand`, add:

```python
        if isinstance(command, DetailsCommand):
            await self._handle_details(
                user_id=user_id,
                command=command,
                reply=reply,
                reply_to_text=reply_to_text,
            )
            return
```

Add method:

```python
    async def _handle_details(
        self,
        *,
        user_id: str,
        command: DetailsCommand,
        reply: Reply,
        reply_to_text: str | None,
    ) -> None:
        item_ref = command.item_ref.strip()
        if not item_ref and reply_to_text:
            item_ref = _item_ref_from_text(reply_to_text)

        try:
            if item_ref:
                item = await _maybe_await(
                    self.knowledge.get_item(user_id=user_id, item_ref=item_ref),
                )
            else:
                item = await _maybe_await(self.knowledge.latest_item(user_id=user_id))
        except ValueError:
            await _send(reply, "I could not find that saved item.")
            return

        await _send(reply, format_item_details(item, alias=self._item_alias(item)))
```

Add helper:

```python
def _item_ref_from_text(text: str) -> str:
    match = _ITEM_ID_RE.search(text)
    if match is None:
        return ""
    return match.group(1)
```

- [ ] **Step 4: Run details tests**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/telegram/test_bot_adapter.py::test_handler_sends_details_by_alias tests/telegram/test_bot_adapter.py::test_handler_sends_details_from_replied_message_id tests/telegram/test_bot_adapter.py::test_handler_plain_details_uses_latest_item tests/telegram/test_bot_adapter.py::test_handler_details_reports_missing_item -q
```

Expected: PASS.

- [ ] **Step 5: Commit details slice**

```bash
git add src/kb_agent/telegram/bot.py src/kb_agent/telegram/formatter.py tests/telegram/test_bot_adapter.py tests/telegram/test_formatter.py
git commit -m "feat: add telegram details flow"
```

---

### Task 6: Compact Ask, Show, And Find Rendering

**Files:**
- Modify: `src/kb_agent/core/retrieval.py`
- Modify: `src/kb_agent/telegram/formatter.py`
- Modify: `src/kb_agent/telegram/bot.py`
- Test: `tests/core/test_retrieval.py`
- Test: `tests/telegram/test_formatter.py`
- Test: `tests/telegram/test_bot_adapter.py`

- [ ] **Step 1: Write failing retrieval tests**

Add to `tests/core/test_retrieval.py`:

```python
@pytest.mark.asyncio
async def test_retrieval_response_carries_structured_answer_fields(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    repo.save(
        ready_item_with_id(
            "7f3a9b8c1234",
            "https://example.com/active",
            "RAG Search",
            "semantic retrieval notes",
        ),
    )

    response = await RetrievalService(repo, HeuristicAIProvider()).answer(
        user_id="telegram:123",
        question="What did I save about retrieval?",
    )

    assert response.question == "What did I save about retrieval?"
    assert response.answer
    assert response.extra_context == ""
    assert response.item_aliases[response.matches[0].id] == "kb_7f3a"
    assert response.matches[0].title == "RAG Search"


@pytest.mark.asyncio
async def test_retrieval_only_adds_extra_context_for_explanation_questions(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    repo.save(ready_item("https://example.com/active", "RAG Search", "semantic retrieval notes"))

    plain = await RetrievalService(repo, HeuristicAIProvider()).answer(
        user_id="telegram:123",
        question="retrieval",
    )
    explanatory = await RetrievalService(repo, HeuristicAIProvider()).answer(
        user_id="telegram:123",
        question="why retrieval matters",
    )

    assert plain.extra_context == ""
    assert explanatory.extra_context
```

- [ ] **Step 2: Run retrieval tests to verify failure**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/core/test_retrieval.py -q
```

Expected: FAIL because `RetrievalResponse` does not expose `question`, `answer`, or `extra_context`.

- [ ] **Step 3: Implement structured retrieval response**

In `src/kb_agent/core/retrieval.py`, update the dataclass:

```python
@dataclass(frozen=True)
class RetrievalResponse:
    text: str
    matches: list[SavedItem]
    question: str = ""
    answer: str = ""
    extra_context: str = ""
    item_aliases: dict[str, str] | None = None
```

In `answer`, replace:

```python
        if matches or _asks_for_explanation(question):
            extra_context = await self.ai_provider.synthesize_extra_context(question)
```

with:

```python
        if _asks_for_explanation(question):
            extra_context = await self.ai_provider.synthesize_extra_context(question)
```

Return:

```python
        text = _format_response(
            answer,
            matches,
            extra_context,
            repository=self.repository,
            user_id=user_id,
        )
        return RetrievalResponse(
            text=text,
            matches=matches,
            question=question,
            answer=answer,
            extra_context=extra_context,
            item_aliases={
                item.id: _item_alias(self.repository, user_id, item)
                for item in matches
            },
        )
```

- [ ] **Step 4: Write failing compact formatter tests for ask/show**

Add tests to `tests/telegram/test_formatter.py`:

```python
from kb_agent.telegram.formatter import format_retrieval_response


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
    assert 'Need more? Reply "details" to an item, or send details kb_7f3a.' in text


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
```

- [ ] **Step 5: Implement compact retrieval formatter**

In `src/kb_agent/telegram/formatter.py`, change signature:

```python
def format_retrieval_response(
    response: TextResult | str,
    *,
    mode: str = "ask",
    query: str = "",
) -> str:
```

Implement:

```python
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
            lines.append(_compact_item_card(item, alias=aliases.get(item.id, alias_for_item_id(item.id))))
            lines.append("")
        first_alias = aliases.get(matches[0].id, alias_for_item_id(matches[0].id))
        lines.append(f'Need more? Reply "details" to an item, or send details {_html(first_alias)}.')
        return "\n".join(lines).strip()

    aliases = getattr(response, "item_aliases", {}) or {}
    answer = _compact_summary(getattr(response, "answer", "") or response.text)
    lines = ["<b>From your knowledge base</b>", _html(answer), "", "<b>Sources</b>"]
    if matches:
        for item in matches:
            alias = aliases.get(item.id, alias_for_item_id(item.id))
            lines.append(f"- {_html(alias)}: {_title_link(item.title or item.url, item.url)}")
    else:
        lines.append("- No strong saved source match.")
    extra_context = getattr(response, "extra_context", "")
    if extra_context:
        lines.extend(["", "<b>Extra context</b>", _html(_compact_summary(extra_context))])
    if matches:
        first_alias = aliases.get(matches[0].id, alias_for_item_id(matches[0].id))
        lines.extend(["", f'Need more? Reply "details" to an item, or send details {_html(first_alias)}.'])
    return "\n".join(lines)
```

Add helper used above:

```python
def _compact_item_card(item: SavedItem, *, alias: str) -> str:
    title = item.title or item.url
    summary = _compact_summary(item.summary or item.user_note or item.extracted_text or title)
    return "\n".join(
        [
            f"<b>{_title_link(title, item.url)}</b>",
            f"ID: {_html(alias)}",
            _tag_line(item.tags),
            _html(summary),
        ],
    )
```

- [ ] **Step 6: Update Telegram handler mode calls**

In `src/kb_agent/telegram/bot.py`, for `AskCommand`:

```python
            await _send(reply, format_retrieval_response(response, mode="ask"))
```

For `ShowCommand`:

```python
        await _send(reply, format_retrieval_response(response, mode="show", query=command.query))
```

- [ ] **Step 7: Run retrieval, formatter, and adapter tests**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/core/test_retrieval.py tests/telegram/test_formatter.py tests/telegram/test_bot_adapter.py -q
```

Expected: PASS after updating old assertions to HTML compact text.

- [ ] **Step 8: Commit retrieval rendering slice**

```bash
git add src/kb_agent/core/retrieval.py src/kb_agent/telegram/formatter.py src/kb_agent/telegram/bot.py tests/core/test_retrieval.py tests/telegram/test_formatter.py tests/telegram/test_bot_adapter.py
git commit -m "feat: compact ask and show responses"
```

---

### Task 7: Compact Daily And Weekly Digests

**Files:**
- Modify: `src/kb_agent/core/digests.py`
- Modify: `src/kb_agent/telegram/formatter.py`
- Test: `tests/core/test_digests.py`
- Test: `tests/telegram/test_formatter.py`

- [ ] **Step 1: Write failing digest tests**

In `tests/core/test_digests.py`, update `test_daily_digest_includes_item_aliases` expectation:

```python
    assert digest.item_aliases[saved.id] == "kb_7f3a"
```

Add:

```python
def test_weekly_digest_selects_up_to_five_items(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    for index in range(7):
        repo.save(item(f"item-{index}", Priority.HIGH, index))

    digest = DigestService(repo).weekly(user_id="telegram:123")

    assert len(digest.items) == 5
```

In `tests/telegram/test_formatter.py`, add:

```python
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
    assert "ID: kb_7f3a" in text
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
```

- [ ] **Step 2: Run digest tests to verify failure**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/core/test_digests.py tests/telegram/test_formatter.py -q
```

Expected: FAIL because `Digest.item_aliases` and compact digest rendering do not exist.

- [ ] **Step 3: Update digest dataclass and selection**

In `src/kb_agent/core/digests.py`, update:

```python
@dataclass(frozen=True)
class Digest:
    text: str
    items: list[SavedItem]
    item_aliases: dict[str, str]
    kind: str
```

Set:

```python
_WEEKLY_LIMIT = 5
```

Add helper:

```python
def _item_aliases(repository: ItemRepository, user_id: str, items: list[SavedItem]) -> dict[str, str]:
    return {item.id: _item_alias(repository, user_id, item) for item in items}
```

Return from `daily`:

```python
        return Digest(
            text="\n".join(lines),
            items=items,
            item_aliases=_item_aliases(self.repository, user_id, items),
            kind="today",
        )
```

Return from `weekly`:

```python
        return Digest(
            text="\n".join(lines),
            items=items,
            item_aliases=_item_aliases(self.repository, user_id, items),
            kind="week",
        )
```

- [ ] **Step 4: Implement compact digest formatters**

In `src/kb_agent/telegram/formatter.py`, update `format_daily_digest`:

```python
def format_daily_digest(digest: TextResult | str) -> str:
    if isinstance(digest, str) or not hasattr(digest, "items"):
        return _format_text_result(digest)
    items = list(getattr(digest, "items", []))
    aliases = getattr(digest, "item_aliases", {})
    lines = ["<b>Daily tiny nudge</b>"]
    for item in items:
        alias = aliases.get(item.id, alias_for_item_id(item.id))
        lines.extend(["", _compact_item_card(item, alias=alias)])
    if items:
        lines.extend(["", f'Need more? Reply "details" to an item, or send details {_html(aliases.get(items[0].id, alias_for_item_id(items[0].id)))}.'])
    return "\n".join(lines)
```

Update `format_weekly_digest`:

```python
def format_weekly_digest(digest: TextResult | str) -> str:
    if isinstance(digest, str) or not hasattr(digest, "items"):
        return _format_text_result(digest)
    items = list(getattr(digest, "items", []))
    aliases = getattr(digest, "item_aliases", {})
    lines = ["<b>Weekly synthesis</b>"]
    grouped: dict[str, list[SavedItem]] = {}
    for item in items:
        topic = item.topic or (item.tags[0] if item.tags else "general")
        grouped.setdefault(topic, []).append(item)
    for topic, topic_items in grouped.items():
        lines.extend(["", f"<b>{_html(topic)}</b>"])
        for item in topic_items:
            alias = aliases.get(item.id, alias_for_item_id(item.id))
            lines.extend(["", _compact_item_card(item, alias=alias)])
    if items:
        first_alias = aliases.get(items[0].id, alias_for_item_id(items[0].id))
        lines.extend(["", f'Need more? Reply "details" to an item, or send details {_html(first_alias)}.'])
    return "\n".join(lines)
```

- [ ] **Step 5: Run digest tests**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/core/test_digests.py tests/telegram/test_formatter.py -q
```

Expected: PASS after updating older digest text assertions to compact HTML.

- [ ] **Step 6: Commit digest slice**

```bash
git add src/kb_agent/core/digests.py src/kb_agent/telegram/formatter.py tests/core/test_digests.py tests/telegram/test_formatter.py
git commit -m "feat: compact digest messages"
```

---

### Task 8: Compact Archive Recommendations And Failure Messages

**Files:**
- Modify: `src/kb_agent/telegram/formatter.py`
- Modify: `src/kb_agent/telegram/bot.py`
- Test: `tests/telegram/test_formatter.py`
- Test: `tests/telegram/test_bot_adapter.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/telegram/test_formatter.py`:

```python
from kb_agent.core.archive_review import ArchiveRecommendation


def test_format_archive_recommendations_is_html_compact() -> None:
    item = replace(_item(), id="7f3a9b8c1234", title="Old Link")
    recommendation = ArchiveRecommendation(item=item, reason="old_low_priority")

    text = format_archive_recommendations([recommendation])

    assert "<b>Archive recommendations</b>" in text
    assert "ID: kb_7f3a" in text
    assert "old_low_priority" in text
    assert "https://example.com/brief" not in text
```

Update bot adapter assertions for archive help messages to expect escaped angle brackets:

```python
assert replies == ["Tell me which item to archive, like: archive &lt;item_id&gt;."]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/telegram/test_formatter.py tests/telegram/test_bot_adapter.py -q
```

Expected: FAIL because archive recommendations are plain text and archive help contains raw angle brackets.

- [ ] **Step 3: Implement compact archive formatting and escaped help**

In `src/kb_agent/telegram/formatter.py`, update `format_archive_recommendations`:

```python
    lines = ["<b>Archive recommendations</b>"]
    for recommendation in recommendations:
        item = recommendation.item
        alias = alias_for_item(item) if alias_for_item is not None else None
        alias = alias or alias_for_item_id(item.id)
        lines.extend(
            [
                "",
                f"<b>{_title_link(item.title or item.url, item.url)}</b>",
                f"ID: {_html(alias)}",
                f"Reason: {_html(recommendation.reason)}",
            ],
        )
    return "\n".join(lines)
```

In `src/kb_agent/telegram/bot.py`, update:

```python
_ARCHIVE_MISSING_ID = "Tell me which item to archive, like: archive &lt;item_id&gt;."
```

- [ ] **Step 4: Run Telegram tests**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/telegram -q
```

Expected: PASS.

- [ ] **Step 5: Commit archive/failure slice**

```bash
git add src/kb_agent/telegram/formatter.py src/kb_agent/telegram/bot.py tests/telegram/test_formatter.py tests/telegram/test_bot_adapter.py
git commit -m "feat: compact archive recommendation messages"
```

---

### Task 9: Tighten AI Summary Prompt

**Files:**
- Modify: `src/kb_agent/ai/briefs.py`
- Test: `tests/ai/test_briefs.py`

- [ ] **Step 1: Write failing prompt test**

Add to `tests/ai/test_briefs.py`:

```python
def test_enrichment_prompt_requests_short_display_summary() -> None:
    item = _item()
    context = build_request_context(
        item=item,
        extracted=ExtractedContent(
            title="Short Summary Source",
            text="Useful source text.",
            metadata={},
        ),
    )

    prompt = build_enrichment_prompt(context)

    assert "summary must be 1-2 short sentences" in prompt
    assert "suggested_next_action must be short" in prompt
```

- [ ] **Step 2: Run prompt test to verify failure**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/ai/test_briefs.py::test_enrichment_prompt_requests_short_display_summary -q
```

Expected: FAIL because the prompt does not include those constraints.

- [ ] **Step 3: Update prompt wording**

In `src/kb_agent/ai/briefs.py`, update `build_enrichment_prompt`:

```python
def build_enrichment_prompt(context: dict[str, Any]) -> str:
    return (
        "Create a concise learning brief for this saved item. "
        "Return JSON only using the provided schema fields. "
        "Use the source content, but preserve the user's intent from their note. "
        "The summary must be 1-2 short sentences for Telegram display. "
        "The suggested_next_action must be short, concrete, and action-oriented. "
        "Key takeaways may contain deeper detail for the details view.\n\n"
        f"Context:\n{json.dumps(context, ensure_ascii=False, sort_keys=True)}"
    )
```

- [ ] **Step 4: Run AI tests**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/ai -q
```

Expected: PASS.

- [ ] **Step 5: Commit prompt slice**

```bash
git add src/kb_agent/ai/briefs.py tests/ai/test_briefs.py
git commit -m "feat: request compact ai summaries"
```

---

### Task 10: Full Verification And Manual Smoke

**Files:**
- No code changes unless verification exposes a bug in touched files.

- [ ] **Step 1: Run full test suite**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run lint**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 3: Check whitespace**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 4: Run a local Telegram-format smoke through tests or bot**

Restart the bot after implementation:

```bash
cd "/Users/himanshu.sin/Documents/New project/.worktrees/personal-kb-agent"
/private/tmp/personal-kb-agent-venv/bin/python -m kb_agent.app
```

In Telegram, send:

```text
show claude
```

Expected: compact HTML-formatted result cards with bold/clickable titles, IDs, tags, short summaries, and a details hint.

Reply to one result with:

```text
details
```

Expected: full detail view for the replied item.

Send:

```text
details
```

Expected: full detail view for the latest saved item in the chat.

- [ ] **Step 5: Commit verification fixes only if needed**

If verification required a fix, stage only touched files:

For example, if the fix touched only formatter tests and formatter code:

```bash
git add src/kb_agent/telegram/formatter.py tests/telegram/test_formatter.py
git commit -m "fix: verify compact telegram responses"
```

If no fix was needed, do not create an empty commit.

---

## Self-Review Notes

Spec coverage:

- Compact save cards: Task 3.
- HTML formatting and escaping: Tasks 3 and 4.
- Details explicit, reply, and latest fallback: Tasks 2 and 5.
- Show/find compact list: Tasks 1 and 6.
- Ask short answer plus compact sources: Task 6.
- Daily and weekly compact digests: Task 7.
- Archive recommendation cleanup: Task 8.
- AI summary prompt constraints: Task 9.
- Verification and restart guidance: Task 10.

The plan intentionally leaves advanced natural-language intent parsing out of scope. Plain natural-language questions still use `ask` behavior, but the answer renderer becomes much shorter and less cluttered.
