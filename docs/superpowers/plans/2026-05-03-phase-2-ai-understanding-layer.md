# Phase 2 AI Understanding Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured AI learning briefs with a Gemini/Ollama/heuristic provider router, item aliases, retryable enrichment, and Telegram controls.

**Architecture:** Keep Telegram as a thin adapter over the knowledge core. Split capture from enrichment so links are saved immediately, then enrichment can complete inline or in the background. Add a router that implements the existing AI provider boundary while delegating structured brief generation to Gemini, Ollama, or heuristic providers.

**Tech Stack:** Python 3.12, SQLite, httpx, pytest, pytest-asyncio, ruff, python-telegram-bot, APScheduler, Gemini REST `generateContent`, Ollama local REST `/api/generate`.

---

## Source Spec

- `docs/superpowers/specs/2026-05-03-phase-2-ai-understanding-layer-design.md`

## File Structure

- Modify `src/kb_agent/core/models.py` - add AI status enum and structured learning brief fields to `SavedItem`.
- Create `src/kb_agent/core/aliases.py` - generate and resolve short stable item aliases such as `kb_7f3a`.
- Modify `src/kb_agent/core/ports.py` - add repository methods for alias resolution and AI retry queries.
- Modify `src/kb_agent/storage/schema.sql` - add AI enrichment columns for new databases.
- Modify `src/kb_agent/storage/sqlite.py` - migrate existing databases, persist brief JSON and AI retry fields.
- Create `src/kb_agent/ai/briefs.py` - define learning brief validation, prompt/context building, and item syncing.
- Create `src/kb_agent/ai/router.py` - parse provider chains, apply fallback rules, expose status/model selection.
- Create `src/kb_agent/ai/gemini.py` - Gemini structured-output provider using httpx.
- Create `src/kb_agent/ai/ollama.py` - Ollama JSON-mode provider using httpx.
- Modify `src/kb_agent/ai/providers.py` - add heuristic learning brief generation while preserving existing answer synthesis.
- Modify `src/kb_agent/core/service.py` - split immediate capture from enrichment, add refresh and retry operations.
- Modify `src/kb_agent/scheduler/jobs.py` - add AI retry job descriptor.
- Modify `src/kb_agent/app.py` - compose provider router, retry scheduler job, and async follow-up dependencies.
- Modify `src/kb_agent/config.py` - add AI provider chain, Gemini, Ollama, sync-wait, and retry settings.
- Modify `.env.example` - document Phase 2 AI settings.
- Modify `src/kb_agent/telegram/parser.py` - parse `ai status`, `refresh`, and `model`.
- Modify `src/kb_agent/telegram/formatter.py` - render aliases, learning briefs, AI status, and pending retry messages.
- Modify `src/kb_agent/telegram/bot.py` - implement hybrid save, background follow-up, model command, AI status, and refresh.
- Modify `README.md` - document Phase 2 setup and commands.
- Modify `docs/manual-qa.md` - add Gemini/Ollama manual QA checks.

## Task 1: Domain Models And Item Aliases

**Files:**
- Modify: `src/kb_agent/core/models.py`
- Create: `src/kb_agent/core/aliases.py`
- Test: `tests/core/test_models.py`
- Test: `tests/core/test_aliases.py`

- [ ] **Step 1: Write failing model tests**

Add these tests to `tests/core/test_models.py`:

```python
import pytest

from kb_agent.core.models import AIStatus, LearningBrief


def test_saved_item_tracks_default_ai_state() -> None:
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/ai",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )

    assert item.ai_status is AIStatus.PENDING
    assert item.ai_attempt_count == 0
    assert item.ai_last_attempt_at is None
    assert item.ai_last_error == ""
    assert item.learning_brief is None


def test_learning_brief_is_frozen_and_normalized() -> None:
    brief = LearningBrief(
        brief_version=1,
        provider="gemini",
        model="gemini-2.5-flash-lite",
        generated_at=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
        title=" Retrieval Guide ",
        topic=" Search ",
        tags=["RAG", " Search ", "RAG"],
        summary=" How retrieval evaluation works. ",
        key_takeaways=[" Use recall. ", " Check precision. "],
        why_it_matters="It improves saved-first answers.",
        estimated_time_minutes=20,
        suggested_next_action="Try a small evaluation example.",
    )

    assert brief.title == "Retrieval Guide"
    assert brief.topic == "Search"
    assert brief.tags == ["rag", "search"]
    assert brief.summary == "How retrieval evaluation works."
    assert brief.key_takeaways == ["Use recall.", "Check precision."]

    with pytest.raises(TypeError):
        brief.tags.append("new")
```

- [ ] **Step 2: Write failing alias tests**

Create `tests/core/test_aliases.py`:

```python
from kb_agent.core.aliases import is_item_alias


def test_alias_for_item_id_uses_short_stable_prefix() -> None:
    assert alias_for_item_id("7f3a9b8c1234") == "kb_7f3a"


def test_alias_for_item_id_accepts_longer_prefix() -> None:
    assert alias_for_item_id("7f3a9b8c1234", length=8) == "kb_7f3a9b8c"


def test_is_item_alias_accepts_kb_prefix() -> None:
    assert is_item_alias("kb_7f3a") is True
    assert is_item_alias("7f3a") is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
pytest tests/core/test_models.py::test_saved_item_tracks_default_ai_state tests/core/test_models.py::test_learning_brief_is_frozen_and_normalized tests/core/test_aliases.py -v
```

Expected: FAIL because `AIStatus`, `LearningBrief`, and `kb_agent.core.aliases` do not exist.

- [ ] **Step 4: Add model fields and alias helpers**

In `src/kb_agent/core/models.py`, add:

```python
class AIStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RETRY_PENDING = "retry_pending"
    FAILED = "failed"


@dataclass(frozen=True)
class LearningBrief:
    brief_version: int
    provider: str
    model: str
    generated_at: datetime
    title: str
    topic: str
    tags: list[str]
    summary: str
    key_takeaways: list[str]
    why_it_matters: str
    estimated_time_minutes: int
    suggested_next_action: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", self.provider.strip())
        object.__setattr__(self, "model", self.model.strip())
        object.__setattr__(self, "title", self.title.strip())
        object.__setattr__(self, "topic", self.topic.strip())
        object.__setattr__(self, "summary", self.summary.strip())
        object.__setattr__(
            self,
            "tags",
            FrozenList(dict.fromkeys(tag.strip().lower() for tag in self.tags if tag.strip())),
        )
        object.__setattr__(
            self,
            "key_takeaways",
            FrozenList(takeaway.strip() for takeaway in self.key_takeaways if takeaway.strip()),
        )
        object.__setattr__(self, "why_it_matters", self.why_it_matters.strip())
        object.__setattr__(
            self,
            "estimated_time_minutes",
            max(1, int(self.estimated_time_minutes)),
        )
        object.__setattr__(self, "suggested_next_action", self.suggested_next_action.strip())
```

Then add these fields to `SavedItem`:

```python
    learning_brief: LearningBrief | None
    ai_status: AIStatus
    ai_attempt_count: int
    ai_last_attempt_at: datetime | None
    ai_last_error: str
```

Set defaults inside `SavedItem.new()`:

```python
            learning_brief=None,
            ai_status=AIStatus.PENDING,
            ai_attempt_count=0,
            ai_last_attempt_at=None,
            ai_last_error="",
```

Create `src/kb_agent/core/aliases.py`:

```python
from __future__ import annotations

import re

_ALIAS_RE = re.compile(r"^kb_[0-9a-f]{4,32}$")


def alias_for_item_id(item_id: str, *, length: int = 4) -> str:
    normalized = item_id.strip().lower()
    return f"kb_{normalized[:length]}"


def is_item_alias(value: str) -> bool:
    return bool(_ALIAS_RE.match(value.strip().lower()))
```

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/core/test_models.py tests/core/test_aliases.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/kb_agent/core/models.py src/kb_agent/core/aliases.py tests/core/test_models.py tests/core/test_aliases.py
git commit -m "feat: add learning brief models and item aliases"
```

## Task 2: SQLite Persistence And Alias Resolution

**Files:**
- Modify: `src/kb_agent/core/ports.py`
- Modify: `src/kb_agent/storage/schema.sql`
- Modify: `src/kb_agent/storage/sqlite.py`
- Test: `tests/storage/test_sqlite_repository.py`

- [ ] **Step 1: Write failing storage tests**

Add to `tests/storage/test_sqlite_repository.py`:

```python
from kb_agent.core.models import AIStatus, LearningBrief


def test_repository_round_trips_ai_fields(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    now = datetime(2026, 5, 3, 9, 0, tzinfo=UTC)
    brief = LearningBrief(
        brief_version=1,
        provider="gemini",
        model="gemini-2.5-flash-lite",
        generated_at=now,
        title="AI Brief",
        topic="retrieval",
        tags=["rag"],
        summary="A structured summary.",
        key_takeaways=["Use structured output."],
        why_it_matters="It makes review easier.",
        estimated_time_minutes=15,
        suggested_next_action="Refresh one saved item.",
    )
    item = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/brief",
            source_type=SourceType.WEB,
            now=now,
        ),
        learning_brief=brief,
        ai_status=AIStatus.READY,
        ai_attempt_count=2,
        ai_last_attempt_at=now,
        ai_last_error="",
    )

    repo.save(item)

    assert repo.get(item.id) == item


def test_repository_resolves_short_aliases(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    item = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/alias",
            source_type=SourceType.WEB,
            now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        ),
        id="7f3a9b8c1234",
    )
    repo.save(item)

    assert repo.resolve_item_ref("telegram:123", "kb_7f3a") == item.id
    assert repo.resolve_item_ref("telegram:999", "kb_7f3a") is None


def test_repository_lists_ai_retry_candidates(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    now = datetime(2026, 5, 3, 9, 0, tzinfo=UTC)
    retryable = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/retry",
            source_type=SourceType.WEB,
            now=now,
        ),
        id="retry",
        ai_status=AIStatus.RETRY_PENDING,
        ai_attempt_count=1,
    )
    archived = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/archive",
            source_type=SourceType.WEB,
            now=now,
        ).archive(now),
        id="archived",
        ai_status=AIStatus.RETRY_PENDING,
    )
    ready = replace(
        SavedItem.new(
            user_id="telegram:123",
            url="https://example.com/ready",
            source_type=SourceType.WEB,
            now=now,
        ),
        id="ready",
        ai_status=AIStatus.READY,
    )
    repo.save(ready)
    repo.save(archived)
    repo.save(retryable)

    assert repo.list_ai_retry_candidates(limit=10, max_attempts=3) == [retryable]
    assert repo.count_ai_retry_pending() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/storage/test_sqlite_repository.py -v
```

Expected: FAIL because SQLite rows do not contain the new AI fields and repository methods.

- [ ] **Step 3: Extend repository port**

In `src/kb_agent/core/ports.py`, extend `ItemRepository`:

```python
    def resolve_item_ref(self, user_id: str, item_ref: str) -> str | None: ...
    def list_ai_retry_candidates(self, *, limit: int, max_attempts: int) -> list[SavedItem]: ...
    def count_ai_retry_pending(self) -> int: ...
    def last_ai_error(self) -> str: ...
```

- [ ] **Step 4: Add schema columns**

In `src/kb_agent/storage/schema.sql`, add these columns to `saved_items`:

```sql
  learning_brief_json TEXT NOT NULL DEFAULT '{}',
  ai_status TEXT NOT NULL DEFAULT 'pending',
  ai_attempt_count INTEGER NOT NULL DEFAULT 0,
  ai_last_attempt_at TEXT,
  ai_last_error TEXT NOT NULL DEFAULT '',
```

Place them before `embedding_json` so the schema groups enrichment fields together.

- [ ] **Step 5: Add migration and serialization helpers**

In `src/kb_agent/storage/sqlite.py`, import:

```python
from kb_agent.core.aliases import is_item_alias
from kb_agent.core.models import AIStatus, LearningBrief, Priority, SavedItem, SourceType, Status
```

After `connection.executescript(schema)` in `_initialize_schema()`, call:

```python
                _ensure_column(connection, "saved_items", "learning_brief_json", "TEXT NOT NULL DEFAULT '{}'")
                _ensure_column(connection, "saved_items", "ai_status", "TEXT NOT NULL DEFAULT 'pending'")
                _ensure_column(connection, "saved_items", "ai_attempt_count", "INTEGER NOT NULL DEFAULT 0")
                _ensure_column(connection, "saved_items", "ai_last_attempt_at", "TEXT")
                _ensure_column(connection, "saved_items", "ai_last_error", "TEXT NOT NULL DEFAULT ''")
```

Add helper functions:

```python
def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _brief_to_json(brief: LearningBrief | None) -> str:
    if brief is None:
        return "{}"
    return json.dumps(
        {
            "brief_version": brief.brief_version,
            "provider": brief.provider,
            "model": brief.model,
            "generated_at": brief.generated_at.isoformat(),
            "title": brief.title,
            "topic": brief.topic,
            "tags": list(brief.tags),
            "summary": brief.summary,
            "key_takeaways": list(brief.key_takeaways),
            "why_it_matters": brief.why_it_matters,
            "estimated_time_minutes": brief.estimated_time_minutes,
            "suggested_next_action": brief.suggested_next_action,
        },
    )


def _json_to_brief(value: str) -> LearningBrief | None:
    data = json.loads(value or "{}")
    if not data:
        return None
    return LearningBrief(
        brief_version=data["brief_version"],
        provider=data["provider"],
        model=data["model"],
        generated_at=datetime.fromisoformat(data["generated_at"]),
        title=data["title"],
        topic=data["topic"],
        tags=data["tags"],
        summary=data["summary"],
        key_takeaways=data["key_takeaways"],
        why_it_matters=data["why_it_matters"],
        estimated_time_minutes=data["estimated_time_minutes"],
        suggested_next_action=data["suggested_next_action"],
    )
```

Add new fields in `_to_row()`:

```python
            "learning_brief_json": _brief_to_json(item.learning_brief),
            "ai_status": item.ai_status.value,
            "ai_attempt_count": item.ai_attempt_count,
            "ai_last_attempt_at": _datetime_to_text(item.ai_last_attempt_at),
            "ai_last_error": item.ai_last_error,
```

Add new constructor fields in `_from_row()`:

```python
            learning_brief=_json_to_brief(row["learning_brief_json"]),
            ai_status=AIStatus(row["ai_status"]),
            ai_attempt_count=row["ai_attempt_count"],
            ai_last_attempt_at=_text_to_datetime(row["ai_last_attempt_at"]),
            ai_last_error=row["ai_last_error"],
```

- [ ] **Step 6: Add repository query methods**

Add methods to `SQLiteItemRepository`:

```python
    def resolve_item_ref(self, user_id: str, item_ref: str) -> str | None:
        ref = item_ref.strip().lower()
        if not ref:
            return None
        if not is_item_alias(ref):
            item = self.get(ref)
            if item is None or item.user_id != user_id:
                return None
            return item.id

        prefix = ref.removeprefix("kb_")
        with closing(self._connect()) as connection:
            with connection:
                rows = connection.execute(
                    "SELECT id FROM saved_items WHERE user_id = ? AND lower(id) LIKE ? "
                    "ORDER BY length(id) ASC, id ASC",
                    (user_id, f"{prefix}%"),
                ).fetchall()
        if len(rows) != 1:
            return None
        return rows[0]["id"]

    def list_ai_retry_candidates(self, *, limit: int, max_attempts: int) -> list[SavedItem]:
        with closing(self._connect()) as connection:
            with connection:
                rows = connection.execute(
                    "SELECT * FROM saved_items "
                    "WHERE archived = 0 "
                    "AND ai_status IN ('pending', 'retry_pending') "
                    "AND ai_attempt_count < ? "
                    "ORDER BY ai_last_attempt_at ASC NULLS FIRST, created_at ASC, id ASC "
                    "LIMIT ?",
                    (max_attempts, limit),
                ).fetchall()
        return [self._from_row(row) for row in rows]

    def count_ai_retry_pending(self) -> int:
        with closing(self._connect()) as connection:
            with connection:
                row = connection.execute(
                    "SELECT COUNT(*) AS count FROM saved_items "
                    "WHERE archived = 0 AND ai_status IN ('pending', 'retry_pending')",
                ).fetchone()
        return int(row["count"])

    def last_ai_error(self) -> str:
        with closing(self._connect()) as connection:
            with connection:
                row = connection.execute(
                    "SELECT ai_last_error FROM saved_items "
                    "WHERE ai_last_error != '' "
                    "ORDER BY ai_last_attempt_at DESC NULLS LAST, updated_at DESC "
                    "LIMIT 1",
                ).fetchone()
        if row is None:
            return ""
        return str(row["ai_last_error"])
```

- [ ] **Step 7: Run tests**

Run:

```bash
pytest tests/storage/test_sqlite_repository.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/kb_agent/core/ports.py src/kb_agent/storage/schema.sql src/kb_agent/storage/sqlite.py tests/storage/test_sqlite_repository.py
git commit -m "feat: persist ai enrichment state"
```

## Task 3: Learning Brief Context And Heuristic Briefs

**Files:**
- Create: `src/kb_agent/ai/briefs.py`
- Modify: `src/kb_agent/ai/providers.py`
- Test: `tests/ai/test_briefs.py`
- Test: `tests/ai/test_heuristic_provider.py`

- [ ] **Step 1: Write failing brief tests**

Create `tests/ai/test_briefs.py`:

```python
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
from kb_agent.core.models import AIStatus, ExtractedContent, LearningBrief, Priority, SavedItem, SourceType


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

    synced = sync_brief_to_item(item, brief, ready=True, now=datetime(2026, 5, 3, 10, 0, tzinfo=UTC))

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
```

- [ ] **Step 2: Add failing heuristic provider test**

Add to `tests/ai/test_heuristic_provider.py`:

```python
@pytest.mark.asyncio
async def test_heuristic_provider_generates_basic_learning_brief() -> None:
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/rag",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        note="focus on retrieval evaluation",
    )
    extracted = ExtractedContent(
        title="RAG Evaluation Guide",
        text="Retrieval augmented generation evaluation uses recall and precision.",
        metadata={},
    )

    brief = await HeuristicAIProvider().generate_learning_brief(item, extracted)

    assert brief.provider == "heuristic"
    assert brief.model == "heuristic"
    assert brief.title == "RAG Evaluation Guide"
    assert brief.summary
    assert brief.key_takeaways
    assert brief.estimated_time_minutes >= 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
pytest tests/ai/test_briefs.py tests/ai/test_heuristic_provider.py -v
```

Expected: FAIL because `kb_agent.ai.briefs` and `generate_learning_brief()` do not exist.

- [ ] **Step 4: Implement brief helpers**

Create `src/kb_agent/ai/briefs.py`:

```python
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from kb_agent.core.models import AIStatus, ExtractedContent, LearningBrief, Priority, SavedItem, Status


class AIErrorCategory(StrEnum):
    MISSING_API_KEY = "missing_api_key"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    INVALID_MODEL = "invalid_model"
    INVALID_RESPONSE = "invalid_ai_response"
    LOCAL_UNAVAILABLE = "local_provider_unavailable"
    UNKNOWN = "unknown_provider_error"


class AIProviderError(RuntimeError):
    def __init__(self, category: AIErrorCategory, message: str) -> None:
        super().__init__(message)
        self.category = category


def build_request_context(
    *,
    item: SavedItem,
    extracted: ExtractedContent | None,
    normal_char_limit: int = 4000,
    extended_char_limit: int = 12000,
) -> dict[str, Any]:
    text = ""
    title = item.title
    metadata: dict[str, str] = {}
    if extracted is not None:
        title = extracted.title or item.title
        text = extracted.text
        metadata = dict(extracted.metadata)
    limit = extended_char_limit if item.priority is Priority.HIGH or len(text) <= normal_char_limit else normal_char_limit
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
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "topic": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
            "key_takeaways": {"type": "array", "items": {"type": "string"}},
            "why_it_matters": {"type": "string"},
            "estimated_time_minutes": {"type": "integer"},
            "suggested_next_action": {"type": "string"},
        },
        "required": [
            "title",
            "topic",
            "tags",
            "summary",
            "key_takeaways",
            "why_it_matters",
            "estimated_time_minutes",
            "suggested_next_action",
        ],
    }


def build_enrichment_prompt(context: dict[str, Any]) -> str:
    return (
        "Return JSON only for a personal learning brief. "
        "Use the provided schema fields exactly. "
        "Treat the user's note as high-signal context and preserve the user's intent "
        "if it conflicts with extracted content.\n\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}"
    )


def validate_learning_brief(
    data: dict[str, Any],
    *,
    provider: str,
    model: str,
    now: datetime | None = None,
) -> LearningBrief:
    schema = build_learning_brief_schema()
    missing = [key for key in schema["required"] if key not in data]
    if missing:
        raise AIProviderError(
            AIErrorCategory.INVALID_RESPONSE,
            f"AI response missing required fields: {', '.join(missing)}",
        )
    generated_at = now or datetime.now().astimezone()
    return LearningBrief(
        brief_version=1,
        provider=provider,
        model=model,
        generated_at=generated_at,
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
    status = AIStatus.READY if ready else AIStatus.RETRY_PENDING
    extracted_text = item.extracted_text
    source_metadata = dict(item.source_metadata)
    if extracted is not None:
        extracted_text = extracted.text
        source_metadata = dict(extracted.metadata)
    return replace(
        item,
        title=brief.title or item.title,
        topic=brief.topic,
        tags=list(brief.tags),
        summary=brief.summary,
        learning_brief=brief,
        ai_status=status,
        ai_last_error="" if ready else item.ai_last_error,
        extracted_text=extracted_text,
        source_metadata=source_metadata,
        status=Status.READY,
        updated_at=now,
    )
```

- [ ] **Step 5: Add heuristic brief generation**

In `src/kb_agent/ai/providers.py`, import `LearningBrief` and `datetime`:

```python
from datetime import UTC, datetime
from kb_agent.core.models import ExtractedContent, LearningBrief, SavedItem, Status
```

Add method to `HeuristicAIProvider`:

```python
    async def generate_learning_brief(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> LearningBrief:
        title = item.url
        text = item.user_note
        if extracted is not None:
            title = extracted.title.strip() or item.url
            text = extracted.text.strip() or item.user_note
        tags = _generate_tags(title, text, item.user_note)
        summary = _summarize(text) or title
        return LearningBrief(
            brief_version=1,
            provider="heuristic",
            model="heuristic",
            generated_at=datetime.now(UTC),
            title=title,
            topic=" ".join(tags[:2]) if tags else item.source_type.value,
            tags=tags,
            summary=summary,
            key_takeaways=[summary],
            why_it_matters=item.user_note or "This item was saved for later review.",
            estimated_time_minutes=max(1, min(30, len(text.split()) // 180 + 1)),
            suggested_next_action="Review the source and add a note with the useful details.",
        )
```

- [ ] **Step 6: Run tests**

Run:

```bash
pytest tests/ai/test_briefs.py tests/ai/test_heuristic_provider.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/kb_agent/ai/briefs.py src/kb_agent/ai/providers.py tests/ai/test_briefs.py tests/ai/test_heuristic_provider.py
git commit -m "feat: add learning brief context and heuristic generation"
```

## Task 4: Provider Router

**Files:**
- Create: `src/kb_agent/ai/router.py`
- Modify: `src/kb_agent/core/ports.py`
- Test: `tests/ai/test_router.py`

- [ ] **Step 1: Write failing router tests**

Create `tests/ai/test_router.py`:

```python
from datetime import UTC, datetime

import pytest

from kb_agent.ai.briefs import AIErrorCategory, AIProviderError
from kb_agent.ai.router import AIProviderRouter, BriefProvider, ProviderChainEntry
from kb_agent.core.models import AIStatus, ExtractedContent, LearningBrief, SavedItem, SourceType


class FakeProvider(BriefProvider):
    def __init__(self, name: str, model: str, result: LearningBrief | Exception) -> None:
        self.name = name
        self.model = model
        self.result = result
        self.calls = 0

    async def generate_learning_brief(self, item, extracted):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _item() -> SavedItem:
    return SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/router",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )


def _brief(provider: str, model: str) -> LearningBrief:
    return LearningBrief(
        brief_version=1,
        provider=provider,
        model=model,
        generated_at=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
        title="Router Brief",
        topic="ai",
        tags=["router"],
        summary="Router summary.",
        key_takeaways=["First success wins."],
        why_it_matters="Predictable cost.",
        estimated_time_minutes=10,
        suggested_next_action="Inspect ai status.",
    )


@pytest.mark.asyncio
async def test_router_stops_after_first_success() -> None:
    first = FakeProvider("gemini", "fast", _brief("gemini", "fast"))
    second = FakeProvider("ollama", "qwen3:8b", _brief("ollama", "qwen3:8b"))
    router = AIProviderRouter(
        chain=[
            ProviderChainEntry(provider="gemini", model="fast"),
            ProviderChainEntry(provider="ollama", model="qwen3:8b"),
        ],
        providers={"gemini:fast": first, "ollama:qwen3:8b": second},
    )

    enriched = await router.enrich(_item(), ExtractedContent(title="T", text="Body", metadata={}))

    assert enriched.ai_status is AIStatus.READY
    assert enriched.learning_brief.provider == "gemini"
    assert first.calls == 1
    assert second.calls == 0


@pytest.mark.asyncio
async def test_router_falls_back_on_rate_limit() -> None:
    first = FakeProvider(
        "gemini",
        "lite",
        AIProviderError(AIErrorCategory.RATE_LIMIT, "rate limited"),
    )
    second = FakeProvider("gemini", "flash", _brief("gemini", "flash"))
    router = AIProviderRouter(
        chain=[
            ProviderChainEntry(provider="gemini", model="lite"),
            ProviderChainEntry(provider="gemini", model="flash"),
        ],
        providers={"gemini:lite": first, "gemini:flash": second},
    )

    enriched = await router.enrich(_item(), None)

    assert enriched.learning_brief.model == "flash"
    assert router.status().last_error == "rate limited"


@pytest.mark.asyncio
async def test_router_heuristic_after_real_failure_is_retry_pending() -> None:
    first = FakeProvider(
        "ollama",
        "qwen3:8b",
        AIProviderError(AIErrorCategory.LOCAL_UNAVAILABLE, "ollama unavailable"),
    )
    heuristic = FakeProvider("heuristic", "heuristic", _brief("heuristic", "heuristic"))
    router = AIProviderRouter(
        chain=[
            ProviderChainEntry(provider="ollama", model="qwen3:8b"),
            ProviderChainEntry(provider="heuristic", model="heuristic"),
        ],
        providers={"ollama:qwen3:8b": first, "heuristic:heuristic": heuristic},
    )

    enriched = await router.enrich(_item(), None)

    assert enriched.learning_brief.provider == "heuristic"
    assert enriched.ai_status is AIStatus.RETRY_PENDING
    assert "ollama unavailable" in enriched.ai_last_error


def test_router_updates_runtime_model_only_inside_configured_chain() -> None:
    router = AIProviderRouter(
        chain=[
            ProviderChainEntry(provider="gemini", model="lite"),
            ProviderChainEntry(provider="gemini", model="flash"),
        ],
        providers={},
    )

    router.select_model("gemini:flash")

    assert router.status().chain[0] == "gemini:flash"
    with pytest.raises(ValueError, match="not in configured provider chain"):
        router.select_model("gemini:expensive")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/ai/test_router.py -v
```

Expected: FAIL because `kb_agent.ai.router` does not exist.

- [ ] **Step 3: Add router implementation**

Create `src/kb_agent/ai/router.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from kb_agent.ai.briefs import AIProviderError, sync_brief_to_item
from kb_agent.core.models import AIStatus, ExtractedContent, LearningBrief, SavedItem, Status


class BriefProvider(Protocol):
    async def generate_learning_brief(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> LearningBrief: ...


@dataclass(frozen=True)
class ProviderChainEntry:
    provider: str
    model: str

    @classmethod
    def parse(cls, value: str) -> ProviderChainEntry:
        text = value.strip()
        if text == "heuristic":
            return cls(provider="heuristic", model="heuristic")
        provider, separator, model = text.partition(":")
        if not separator or not provider or not model:
            raise ValueError(f"Invalid provider chain entry: {value}")
        return cls(provider=provider, model=model)

    def key(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass(frozen=True)
class AIStatusSnapshot:
    chain: list[str]
    last_error: str


class AIProviderRouter:
    def __init__(
        self,
        *,
        chain: list[ProviderChainEntry],
        providers: dict[str, BriefProvider],
    ) -> None:
        if not chain:
            raise ValueError("AI provider chain must not be empty")
        self._configured_chain = list(chain)
        self._chain = list(chain)
        self._providers = providers
        self._last_error = ""

    async def enrich(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> SavedItem:
        last_error = ""
        real_provider_failed = False
        now = item.updated_at
        for entry in self._chain:
            provider = self._providers.get(entry.key())
            if provider is None:
                last_error = f"No provider configured for {entry.key()}"
                real_provider_failed = real_provider_failed or entry.provider != "heuristic"
                continue
            try:
                brief = await provider.generate_learning_brief(item, extracted)
            except AIProviderError as error:
                last_error = str(error)
                real_provider_failed = real_provider_failed or entry.provider != "heuristic"
                self._last_error = last_error
                continue

            ready = entry.provider != "heuristic" or not real_provider_failed
            enriched = sync_brief_to_item(item, brief, ready=ready, now=now, extracted=extracted)
            if not ready:
                enriched = replace(
                    enriched,
                    ai_status=AIStatus.RETRY_PENDING,
                    ai_last_error=last_error,
                    status=Status.READY,
                )
            self._last_error = last_error
            return enriched

        self._last_error = last_error
        return replace(
            item,
            ai_status=AIStatus.RETRY_PENDING,
            ai_last_error=last_error,
            status=Status.FAILED_ENRICHMENT,
        )

    async def synthesize_answer(self, question: str, matches: list[SavedItem]) -> str:
        provider = self._providers.get("heuristic:heuristic")
        if provider is None or not hasattr(provider, "synthesize_answer"):
            return f"No saved items match {question!r}." if not matches else matches[0].summary
        return await provider.synthesize_answer(question, matches)

    async def synthesize_extra_context(self, question: str) -> str:
        provider = self._providers.get("heuristic:heuristic")
        if provider is None or not hasattr(provider, "synthesize_extra_context"):
            return "No external context is available from the configured AI router."
        return await provider.synthesize_extra_context(question)

    def select_model(self, provider_model: str) -> None:
        requested = ProviderChainEntry.parse(provider_model)
        matches = [entry for entry in self._configured_chain if entry.key() == requested.key()]
        if not matches:
            raise ValueError(f"{provider_model} is not in configured provider chain")
        remaining = [entry for entry in self._configured_chain if entry.key() != requested.key()]
        self._chain = [matches[0], *remaining]

    def status(self) -> AIStatusSnapshot:
        return AIStatusSnapshot(
            chain=[entry.key() for entry in self._chain],
            last_error=self._last_error,
        )
```

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/ai/test_router.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kb_agent/ai/router.py tests/ai/test_router.py
git commit -m "feat: add ai provider router"
```

## Task 5: Gemini And Ollama Providers

**Files:**
- Create: `src/kb_agent/ai/gemini.py`
- Create: `src/kb_agent/ai/ollama.py`
- Test: `tests/ai/test_gemini_provider.py`
- Test: `tests/ai/test_ollama_provider.py`

- [ ] **Step 1: Write failing Gemini tests**

Create `tests/ai/test_gemini_provider.py`:

```python
import json
from datetime import UTC, datetime

import httpx
import pytest

from kb_agent.ai.briefs import AIErrorCategory, AIProviderError
from kb_agent.ai.gemini import GeminiBriefProvider
from kb_agent.core.models import ExtractedContent, SavedItem, SourceType


def _item() -> SavedItem:
    return SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/gemini",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        note="use for learning",
    )


@pytest.mark.asyncio
async def test_gemini_provider_parses_structured_text_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "gemini-2.5-flash-lite:generateContent" in str(request.url)
        assert request.headers["x-goog-api-key"] == "key"
        body = json.loads(request.content.decode())
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"title":"Gemini Brief","topic":"ai","tags":["gemini"],'
                                        '"summary":"Summary","key_takeaways":["Takeaway"],'
                                        '"why_it_matters":"Useful","estimated_time_minutes":10,'
                                        '"suggested_next_action":"Try it"}'
                                    )
                                }
                            ]
                        }
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        brief = await GeminiBriefProvider(
            http_client=client,
            api_key="key",
            model="gemini-2.5-flash-lite",
        ).generate_learning_brief(_item(), ExtractedContent(title="T", text="Body", metadata={}))

    assert brief.provider == "gemini"
    assert brief.model == "gemini-2.5-flash-lite"
    assert brief.title == "Gemini Brief"


@pytest.mark.asyncio
async def test_gemini_provider_classifies_rate_limit() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(429, json={"error": {"message": "quota"}}))
    ) as client:
        provider = GeminiBriefProvider(http_client=client, api_key="key", model="gemini-2.5-flash-lite")

        with pytest.raises(AIProviderError) as error:
            await provider.generate_learning_brief(_item(), None)

    assert error.value.category is AIErrorCategory.RATE_LIMIT


@pytest.mark.asyncio
async def test_gemini_provider_requires_api_key() -> None:
    async with httpx.AsyncClient() as client:
        provider = GeminiBriefProvider(http_client=client, api_key="", model="gemini-2.5-flash-lite")

        with pytest.raises(AIProviderError) as error:
            await provider.generate_learning_brief(_item(), None)

    assert error.value.category is AIErrorCategory.MISSING_API_KEY
```

- [ ] **Step 2: Write failing Ollama tests**

Create `tests/ai/test_ollama_provider.py`:

```python
import json
from datetime import UTC, datetime

import httpx
import pytest

from kb_agent.ai.briefs import AIErrorCategory, AIProviderError
from kb_agent.ai.ollama import OllamaBriefProvider
from kb_agent.core.models import SavedItem, SourceType


def _item() -> SavedItem:
    return SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/ollama",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_ollama_provider_uses_json_mode_and_non_streaming_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://localhost:11434/api/generate"
        body = json.loads(request.content.decode())
        assert body["model"] == "qwen3:8b"
        assert body["stream"] is False
        assert body["format"] == "json"
        return httpx.Response(
            200,
            json={
                "response": (
                    '{"title":"Ollama Brief","topic":"local ai","tags":["ollama"],'
                    '"summary":"Summary","key_takeaways":["Takeaway"],'
                    '"why_it_matters":"Private","estimated_time_minutes":8,'
                    '"suggested_next_action":"Run locally"}'
                )
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        brief = await OllamaBriefProvider(
            http_client=client,
            base_url="http://localhost:11434",
            model="qwen3:8b",
        ).generate_learning_brief(_item(), None)

    assert brief.provider == "ollama"
    assert brief.model == "qwen3:8b"
    assert brief.title == "Ollama Brief"


@pytest.mark.asyncio
async def test_ollama_provider_classifies_unavailable_local_server() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connect failed", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaBriefProvider(
            http_client=client,
            base_url="http://localhost:11434",
            model="qwen3:8b",
        )

        with pytest.raises(AIProviderError) as error:
            await provider.generate_learning_brief(_item(), None)

    assert error.value.category is AIErrorCategory.LOCAL_UNAVAILABLE
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
pytest tests/ai/test_gemini_provider.py tests/ai/test_ollama_provider.py -v
```

Expected: FAIL because Gemini and Ollama provider modules do not exist.

- [ ] **Step 4: Implement Gemini provider**

Create `src/kb_agent/ai/gemini.py`:

```python
from __future__ import annotations

import json

import httpx

from kb_agent.ai.briefs import (
    AIErrorCategory,
    AIProviderError,
    build_enrichment_prompt,
    build_learning_brief_schema,
    build_request_context,
    validate_learning_brief,
)
from kb_agent.core.models import ExtractedContent, LearningBrief, SavedItem


class GeminiBriefProvider:
    def __init__(self, *, http_client: httpx.AsyncClient, api_key: str, model: str) -> None:
        self.http_client = http_client
        self.api_key = api_key
        self.model = model

    async def generate_learning_brief(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> LearningBrief:
        if not self.api_key:
            raise AIProviderError(AIErrorCategory.MISSING_API_KEY, "Gemini API key is missing")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": build_enrichment_prompt(build_request_context(item=item, extracted=extracted))}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": build_learning_brief_schema(),
            },
        }
        try:
            response = await self.http_client.post(
                url,
                headers={"x-goog-api-key": self.api_key},
                json=payload,
                timeout=30,
            )
        except httpx.TimeoutException as error:
            raise AIProviderError(AIErrorCategory.TIMEOUT, "Gemini request timed out") from error
        except httpx.HTTPError as error:
            raise AIProviderError(AIErrorCategory.UNKNOWN, str(error)) from error

        if response.status_code == 429:
            raise AIProviderError(AIErrorCategory.RATE_LIMIT, "Gemini hit a rate limit")
        if response.status_code == 404:
            raise AIProviderError(AIErrorCategory.INVALID_MODEL, f"Gemini model is invalid: {self.model}")
        if response.status_code >= 400:
            raise AIProviderError(AIErrorCategory.UNKNOWN, f"Gemini failed with HTTP {response.status_code}")

        text = _extract_text(response.json())
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise AIProviderError(AIErrorCategory.INVALID_RESPONSE, "Gemini returned invalid JSON") from error
        return validate_learning_brief(data, provider="gemini", model=self.model)


def _extract_text(payload: dict) -> str:
    try:
        return payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as error:
        raise AIProviderError(AIErrorCategory.INVALID_RESPONSE, "Gemini returned no structured text") from error
```

- [ ] **Step 5: Implement Ollama provider**

Create `src/kb_agent/ai/ollama.py`:

```python
from __future__ import annotations

import json

import httpx

from kb_agent.ai.briefs import (
    AIErrorCategory,
    AIProviderError,
    build_enrichment_prompt,
    build_request_context,
    validate_learning_brief,
)
from kb_agent.core.models import ExtractedContent, LearningBrief, SavedItem


class OllamaBriefProvider:
    def __init__(self, *, http_client: httpx.AsyncClient, base_url: str, model: str) -> None:
        self.http_client = http_client
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def generate_learning_brief(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> LearningBrief:
        payload = {
            "model": self.model,
            "prompt": build_enrichment_prompt(build_request_context(item=item, extracted=extracted)),
            "format": "json",
            "stream": False,
        }
        try:
            response = await self.http_client.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=60,
            )
        except (httpx.ConnectError, httpx.ConnectTimeout) as error:
            raise AIProviderError(
                AIErrorCategory.LOCAL_UNAVAILABLE,
                f"Ollama unavailable at {self.base_url}",
            ) from error
        except httpx.TimeoutException as error:
            raise AIProviderError(AIErrorCategory.TIMEOUT, "Ollama request timed out") from error
        except httpx.HTTPError as error:
            raise AIProviderError(AIErrorCategory.UNKNOWN, str(error)) from error

        if response.status_code == 404:
            raise AIProviderError(AIErrorCategory.INVALID_MODEL, f"Ollama model is invalid: {self.model}")
        if response.status_code >= 400:
            raise AIProviderError(AIErrorCategory.UNKNOWN, f"Ollama failed with HTTP {response.status_code}")

        data = response.json()
        text = data.get("response", "")
        if not text:
            raise AIProviderError(AIErrorCategory.INVALID_RESPONSE, "Ollama returned an empty response")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise AIProviderError(AIErrorCategory.INVALID_RESPONSE, "Ollama returned invalid JSON") from error
        return validate_learning_brief(data, provider="ollama", model=self.model)
```

- [ ] **Step 6: Run tests**

Run:

```bash
pytest tests/ai/test_gemini_provider.py tests/ai/test_ollama_provider.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/kb_agent/ai/gemini.py src/kb_agent/ai/ollama.py tests/ai/test_gemini_provider.py tests/ai/test_ollama_provider.py
git commit -m "feat: add gemini and ollama brief providers"
```

## Task 6: Knowledge Service Capture, Refresh, And Retry

**Files:**
- Modify: `src/kb_agent/core/service.py`
- Test: `tests/core/test_knowledge_service.py`

- [ ] **Step 1: Write failing service tests**

Add to `tests/core/test_knowledge_service.py`:

```python
from kb_agent.core.models import AIStatus, LearningBrief


class RecordingAIProvider(HeuristicAIProvider):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def enrich(self, item: SavedItem, extracted: ExtractedContent | None) -> SavedItem:
        self.calls.append(item.id)
        return await super().enrich(item, extracted)


def _brief_item(item: SavedItem, *, now: datetime) -> SavedItem:
    brief = LearningBrief(
        brief_version=1,
        provider="gemini",
        model="gemini-2.5-flash-lite",
        generated_at=now,
        title="Refreshed Brief",
        topic="ai",
        tags=["refresh"],
        summary="Refreshed summary.",
        key_takeaways=["Refresh works."],
        why_it_matters="Model prompts improve.",
        estimated_time_minutes=5,
        suggested_next_action="Review the result.",
    )
    return replace(
        item,
        title=brief.title,
        topic=brief.topic,
        tags=list(brief.tags),
        summary=brief.summary,
        learning_brief=brief,
        ai_status=AIStatus.READY,
        status=Status.READY,
        updated_at=now,
    )


class BriefAIProvider(HeuristicAIProvider):
    async def enrich(self, item: SavedItem, extracted: ExtractedContent | None) -> SavedItem:
        return _brief_item(item, now=FixedClock().now())


@pytest.mark.asyncio
async def test_create_link_saves_without_running_extraction_or_ai(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    ai = RecordingAIProvider()
    service = KnowledgeService(
        repository=repo,
        extractor=ThrowingExtractor(),
        ai_provider=ai,
        clock=FixedClock(),
    )

    item = service.create_link(
        user_id="telegram:123",
        url="https://example.com/immediate",
        note="capture now",
        priority=Priority.HIGH,
    )

    assert item.status is Status.PROCESSING
    assert item.ai_status is AIStatus.PENDING
    assert item.user_note == "capture now"
    assert ai.calls == []
    assert repo.get(item.id) == item


@pytest.mark.asyncio
async def test_enrich_saved_item_updates_existing_item(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(ExtractedContent(title="Source", text="Body", metadata={})),
        ai_provider=BriefAIProvider(),
        clock=FixedClock(),
    )
    item = service.create_link(user_id="telegram:123", url="https://example.com/source")

    enriched = await service.enrich_saved_item(user_id="telegram:123", item_id=item.id)

    assert enriched.id == item.id
    assert enriched.ai_status is AIStatus.READY
    assert enriched.learning_brief.title == "Refreshed Brief"
    assert repo.get(item.id) == enriched


@pytest.mark.asyncio
async def test_refresh_item_accepts_alias(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(ExtractedContent(title="Source", text="Body", metadata={})),
        ai_provider=BriefAIProvider(),
        clock=FixedClock(),
    )
    item = replace(
        service.create_link(user_id="telegram:123", url="https://example.com/source"),
        id="7f3a9b8c1234",
    )
    repo.save(item)

    refreshed = await service.refresh_item(user_id="telegram:123", item_ref="kb_7f3a")

    assert refreshed.id == "7f3a9b8c1234"
    assert refreshed.learning_brief.title == "Refreshed Brief"


@pytest.mark.asyncio
async def test_retry_pending_ai_skips_archived_items_and_caps_attempts(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(ExtractedContent(title="Source", text="Body", metadata={})),
        ai_provider=BriefAIProvider(),
        clock=FixedClock(),
    )
    retryable = replace(
        service.create_link(user_id="telegram:123", url="https://example.com/retry"),
        ai_status=AIStatus.RETRY_PENDING,
        ai_attempt_count=1,
    )
    archived = replace(
        service.create_link(user_id="telegram:123", url="https://example.com/archive").archive(FixedClock().now()),
        ai_status=AIStatus.RETRY_PENDING,
    )
    repo.save(retryable)
    repo.save(archived)

    results = await service.retry_pending_ai(limit=10, max_attempts=3)

    assert [item.id for item in results] == [retryable.id]
    assert repo.get(retryable.id).ai_status is AIStatus.READY
    assert repo.get(archived.id).ai_status is AIStatus.RETRY_PENDING
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/core/test_knowledge_service.py -v
```

Expected: FAIL because `create_link`, `enrich_saved_item`, `refresh_item`, and `retry_pending_ai` do not exist.

- [ ] **Step 3: Add capture and reference resolution methods**

In `src/kb_agent/core/service.py`, add:

```python
    def create_link(
        self,
        *,
        user_id: str,
        url: str,
        note: str = "",
        priority: Priority = Priority.UNSET,
    ) -> SavedItem:
        now = self.clock.now()
        item = SavedItem.new(
            user_id=user_id,
            url=url,
            source_type=detect_source_type(url),
            now=now,
            note=note,
            priority=priority,
        )
        self.repository.save(item)
        return item

    def resolve_item_ref(self, *, user_id: str, item_ref: str) -> str:
        item_id = self.repository.resolve_item_ref(user_id, item_ref)
        if item_id is None:
            raise ValueError("Saved item not found")
        return item_id
```

- [ ] **Step 4: Add enrichment, refresh, and retry methods**

In `KnowledgeService`, add:

```python
    async def enrich_saved_item(self, *, user_id: str, item_id: str) -> SavedItem:
        item = self._get_user_item(user_id=user_id, item_id=item_id)
        extracted = await self._extract_for_item(item)
        return await self._enrich_and_save(item, extracted)

    async def refresh_item(self, *, user_id: str, item_ref: str) -> SavedItem:
        item_id = self.resolve_item_ref(user_id=user_id, item_ref=item_ref)
        return await self.enrich_saved_item(user_id=user_id, item_id=item_id)

    async def retry_pending_ai(self, *, limit: int, max_attempts: int) -> list[SavedItem]:
        results: list[SavedItem] = []
        for item in self.repository.list_ai_retry_candidates(limit=limit, max_attempts=max_attempts):
            updated = replace(
                item,
                ai_attempt_count=item.ai_attempt_count + 1,
                ai_last_attempt_at=self.clock.now(),
                updated_at=self.clock.now(),
            )
            self.repository.save(updated)
            results.append(
                await self.enrich_saved_item(user_id=item.user_id, item_id=item.id),
            )
        return results

    async def _extract_for_item(self, item: SavedItem) -> ExtractedContent | None:
        try:
            extracted = await self.extractor.extract(item.url)
        except Exception:
            extracted = _manual_extracted_content(item)
        if extracted is None:
            extracted = _manual_extracted_content(item)
        if extracted is None and item.extracted_text:
            extracted = ExtractedContent(
                title=item.title,
                text=item.extracted_text,
                metadata=dict(item.source_metadata),
            )
        return extracted
```

Update `save_link()` so it uses `create_link()` for new items, then calls `enrich_saved_item()` for backward compatibility:

```python
        if item is None:
            item = self.create_link(
                user_id=user_id,
                url=url,
                note=note,
                priority=priority,
            )
        else:
            self.repository.save(item)
        return await self.enrich_saved_item(user_id=user_id, item_id=item.id)
```

- [ ] **Step 5: Update archive, note, and priority methods to resolve aliases**

Change `archive_item`, `add_note`, and `set_priority` to resolve references before `_get_user_item()`:

```python
        item_id = self.resolve_item_ref(user_id=user_id, item_ref=item_id)
        item = self._get_user_item(user_id=user_id, item_id=item_id)
```

Use the same pattern for `add_note` and `set_priority`.

- [ ] **Step 6: Run tests**

Run:

```bash
pytest tests/core/test_knowledge_service.py tests/storage/test_sqlite_repository.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/kb_agent/core/service.py tests/core/test_knowledge_service.py
git commit -m "feat: split capture from ai enrichment"
```

## Task 7: Telegram Commands And Learning Brief Formatting

**Files:**
- Modify: `src/kb_agent/telegram/parser.py`
- Modify: `src/kb_agent/telegram/formatter.py`
- Modify: `src/kb_agent/telegram/bot.py`
- Test: `tests/telegram/test_parser.py`
- Test: `tests/telegram/test_formatter.py`
- Test: `tests/telegram/test_bot_adapter.py`

- [ ] **Step 1: Write failing parser tests**

Add to `tests/telegram/test_parser.py`:

```python
from kb_agent.telegram.parser import AIStatusCommand, ModelCommand, RefreshCommand


def test_ai_status_command() -> None:
    assert isinstance(parse_message("ai status"), AIStatusCommand)


def test_refresh_command() -> None:
    command = parse_message("refresh kb_7f3a")

    assert isinstance(command, RefreshCommand)
    assert command.item_ref == "kb_7f3a"


def test_model_command() -> None:
    command = parse_message("model gemini:gemini-2.5-flash")

    assert isinstance(command, ModelCommand)
    assert command.provider_model == "gemini:gemini-2.5-flash"
```

- [ ] **Step 2: Write failing formatter tests**

Add to `tests/telegram/test_formatter.py`:

```python
from dataclasses import replace
from datetime import UTC, datetime

from kb_agent.ai.router import AIStatusSnapshot
from kb_agent.core.models import AIStatus, LearningBrief, SavedItem, SourceType, Status
from kb_agent.telegram.formatter import (
    format_ai_status,
    format_learning_brief,
    format_pending_learning_brief,
)


def _brief() -> LearningBrief:
    return LearningBrief(
        brief_version=1,
        provider="gemini",
        model="gemini-2.5-flash-lite",
        generated_at=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
        title="Learning Brief",
        topic="ai",
        tags=["gemini"],
        summary="Summary text.",
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


def test_format_learning_brief_includes_alias_and_fields() -> None:
    text = format_learning_brief(_item())

    assert "Learning brief: Learning Brief" in text
    assert "ID: kb_7f3a" in text
    assert "Key takeaways:" in text
    assert "Time: 20 min" in text
    assert "Next: Try it." in text


def test_format_pending_learning_brief_includes_alias() -> None:
    assert format_pending_learning_brief(_item()) == (
        "Saved: Learning Brief\nID: kb_7f3a\nPreparing learning brief..."
    )


def test_format_ai_status() -> None:
    text = format_ai_status(
        AIStatusSnapshot(
            chain=["gemini:lite", "ollama:qwen3:8b", "heuristic:heuristic"],
            last_error="Ollama unavailable",
        ),
        pending_retry_count=3,
    )

    assert "AI status" in text
    assert "gemini:lite -> ollama:qwen3:8b -> heuristic:heuristic" in text
    assert "Pending retries: 3" in text
    assert "Last error: Ollama unavailable" in text
```

- [ ] **Step 3: Write failing Telegram handler tests**

Add to `tests/telegram/test_bot_adapter.py`:

```python
class FakeAIRouter:
    def __init__(self) -> None:
        self.selected: str | None = None

    def status(self):
        return type("Status", (), {"chain": ["gemini:lite", "heuristic:heuristic"], "last_error": ""})()

    def select_model(self, provider_model: str) -> None:
        self.selected = provider_model


@pytest.mark.asyncio
async def test_handler_sends_ai_status() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
        ai_router=FakeAIRouter(),
    )

    await handler.handle_text(user_id="telegram:123", text="ai status", reply=replies.append)

    assert "AI status" in replies[0]
    assert "gemini:lite -> heuristic:heuristic" in replies[0]


@pytest.mark.asyncio
async def test_handler_refreshes_item_by_alias() -> None:
    replies = []
    knowledge = FakeKnowledge()
    brief = LearningBrief(
        brief_version=1,
        provider="gemini",
        model="gemini-2.5-flash-lite",
        generated_at=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
        title="Learning Brief",
        topic="ai",
        tags=["brief"],
        summary="Summary.",
        key_takeaways=["Takeaway."],
        why_it_matters="Useful.",
        estimated_time_minutes=10,
        suggested_next_action="Review it.",
    )
    knowledge.refresh_item = lambda **_: replace(
        _saved_item(title="Learning Brief"),
        id="7f3a9b8c1234",
        learning_brief=brief,
    )
    handler = TelegramMessageHandler(
        knowledge=knowledge,
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
        ai_router=FakeAIRouter(),
    )

    await handler.handle_text(user_id="telegram:123", text="refresh kb_7f3a", reply=replies.append)

    assert "Learning brief: Learning Brief" in replies[0]
    assert "ID: kb_7f3a" in replies[0]


@pytest.mark.asyncio
async def test_handler_selects_model() -> None:
    replies = []
    router = FakeAIRouter()
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
        ai_router=router,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="model gemini:lite",
        reply=replies.append,
    )

    assert router.selected == "gemini:lite"
    assert replies == ["Model selected: gemini:lite"]
```

- [ ] **Step 4: Run tests to verify they fail**

Run:

```bash
pytest tests/telegram/test_parser.py tests/telegram/test_formatter.py tests/telegram/test_bot_adapter.py -v
```

Expected: FAIL because commands and formatters do not exist.

- [ ] **Step 5: Implement parser commands**

In `src/kb_agent/telegram/parser.py`, add dataclasses:

```python
@dataclass(frozen=True)
class AIStatusCommand:
    pass


@dataclass(frozen=True)
class RefreshCommand:
    item_ref: str


@dataclass(frozen=True)
class ModelCommand:
    provider_model: str
```

Update the return union and add command parsing before archive/show:

```python
    if lowered == "ai status" or lowered.startswith("ai status "):
        return AIStatusCommand()
    if lowered == "refresh" or lowered.startswith("refresh "):
        return RefreshCommand(item_ref=_after_command(text))
    if lowered == "model" or lowered.startswith("model "):
        return ModelCommand(provider_model=_after_command(text))
```

- [ ] **Step 6: Implement formatter functions**

In `src/kb_agent/telegram/formatter.py`, import alias helper:

```python
from kb_agent.core.aliases import alias_for_item_id
```

Add:

```python
def format_learning_brief(item: SavedItem) -> str:
    brief = item.learning_brief
    if brief is None:
        return format_save_confirmation(item)
    lines = [
        f"Learning brief: {brief.title}",
        f"ID: {alias_for_item_id(item.id)}",
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


def format_pending_learning_brief(item: SavedItem) -> str:
    return "\n".join(
        [
            f"Saved: {item.title or item.url}",
            f"ID: {alias_for_item_id(item.id)}",
            "Preparing learning brief...",
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
```

Update `format_save_confirmation()` and `format_archive_recommendations()` to include aliases:

```python
            f"ID: {alias_for_item_id(item.id)}",
```

Use aliases in archive recommendation lines:

```python
        lines.append(f"- {alias_for_item_id(item.id)}: {title} ({recommendation.reason})")
```

- [ ] **Step 7: Implement handler commands**

In `src/kb_agent/telegram/bot.py`, import new commands and formatters:

```python
import asyncio
```

```python
    AIStatusCommand,
    ModelCommand,
    RefreshCommand,
```

```python
    format_ai_status,
    format_learning_brief,
    format_pending_learning_brief,
```

Update `TelegramMessageHandler.__init__` signature:

```python
        ai_router: Any | None = None,
```

Set:

```python
        self.ai_router = ai_router
```

Handle commands:

```python
        if isinstance(command, AIStatusCommand):
            if self.ai_router is None:
                await _send(reply, "AI router is not available right now.")
                return
            pending_count = 0
            if hasattr(self.knowledge.repository, "count_ai_retry_pending"):
                pending_count = self.knowledge.repository.count_ai_retry_pending()
            await _send(
                reply,
                format_ai_status(self.ai_router.status(), pending_retry_count=pending_count),
            )
            return

        if isinstance(command, RefreshCommand):
            if not command.item_ref:
                await _send(reply, "Tell me which item to refresh, like: refresh kb_7f3a.")
                return
            try:
                item = await _maybe_await(
                    self.knowledge.refresh_item(user_id=user_id, item_ref=command.item_ref),
                )
            except ValueError:
                await _send(reply, "I could not find that saved item.")
                return
            await _send(reply, format_learning_brief(item))
            return

        if isinstance(command, ModelCommand):
            if self.ai_router is None:
                await _send(reply, "AI router is not available right now.")
                return
            try:
                self.ai_router.select_model(command.provider_model)
            except ValueError as error:
                await _send(reply, str(error))
                return
            await _send(reply, f"Model selected: {command.provider_model}")
            return
```

- [ ] **Step 8: Run tests**

Run:

```bash
pytest tests/telegram/test_parser.py tests/telegram/test_formatter.py tests/telegram/test_bot_adapter.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/kb_agent/telegram/parser.py src/kb_agent/telegram/formatter.py src/kb_agent/telegram/bot.py tests/telegram/test_parser.py tests/telegram/test_formatter.py tests/telegram/test_bot_adapter.py
git commit -m "feat: add ai telegram commands and brief formatting"
```

## Task 8: Hybrid Telegram Save Follow-Up

**Files:**
- Modify: `src/kb_agent/telegram/bot.py`
- Test: `tests/telegram/test_bot_adapter.py`

- [ ] **Step 1: Write failing hybrid save tests**

Add to `tests/telegram/test_bot_adapter.py`:

```python
import asyncio


class SlowKnowledge(FakeKnowledge):
    def __init__(self) -> None:
        super().__init__()
        self.created = replace(_saved_item(title="https://example.com/rag"), id="7f3a9b8c1234")

    def create_link(self, *, user_id, url, note="", priority=None):
        return self.created

    async def enrich_saved_item(self, *, user_id, item_id):
        await asyncio.sleep(0.01)
        return replace(self.created, title="Finished Brief")


@pytest.mark.asyncio
async def test_handler_replies_pending_then_follow_up_for_slow_save() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=SlowKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
        ai_router=FakeAIRouter(),
        ai_sync_wait_seconds=0,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="https://example.com/rag",
        reply=replies.append,
    )
    await asyncio.sleep(0.02)

    assert replies[0] == "Saved: https://example.com/rag\nID: kb_7f3a\nPreparing learning brief..."
    assert "Saved: Finished Brief" in replies[1] or "Learning brief: Finished Brief" in replies[1]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/telegram/test_bot_adapter.py::test_handler_replies_pending_then_follow_up_for_slow_save -v
```

Expected: FAIL because save still waits for `knowledge.save_link()`.

- [ ] **Step 3: Implement hybrid save path**

In `TelegramMessageHandler.__init__`, add:

```python
        ai_sync_wait_seconds: float = 6.0,
```

Set:

```python
        self.ai_sync_wait_seconds = ai_sync_wait_seconds
```

Replace the save command branch with:

```python
        if isinstance(command, SaveCommand):
            if hasattr(self.knowledge, "create_link") and hasattr(self.knowledge, "enrich_saved_item"):
                item = self.knowledge.create_link(
                    user_id=user_id,
                    url=command.url,
                    note=command.note,
                    priority=command.priority,
                )
                task = asyncio.create_task(
                    self.knowledge.enrich_saved_item(user_id=user_id, item_id=item.id),
                )
                try:
                    enriched = await asyncio.wait_for(
                        asyncio.shield(task),
                        timeout=self.ai_sync_wait_seconds,
                    )
                except TimeoutError:
                    await _send(reply, format_pending_learning_brief(item))
                    task.add_done_callback(
                        lambda done: asyncio.create_task(
                            _send_enrichment_follow_up(done, reply),
                        ),
                    )
                    return
                await _send(reply, format_learning_brief(enriched))
                if enriched.status is Status.NEEDS_TEXT:
                    await _send(reply, format_needs_text_prompt(enriched))
                return
```

Add helper near `_send`:

```python
async def _send_enrichment_follow_up(done: asyncio.Task, reply: Reply) -> None:
    try:
        item = done.result()
    except Exception:
        await _send(reply, "Saved with basic enrichment. AI brief is pending retry.")
        return
    await _send(reply, format_learning_brief(item))
```

Keep the old `knowledge.save_link()` branch after this block for tests or callers that do not expose split capture methods.

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/telegram/test_bot_adapter.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kb_agent/telegram/bot.py tests/telegram/test_bot_adapter.py
git commit -m "feat: send learning brief follow ups"
```

## Task 9: Runtime Configuration And Scheduler Wiring

**Files:**
- Modify: `src/kb_agent/config.py`
- Modify: `src/kb_agent/app.py`
- Modify: `src/kb_agent/scheduler/jobs.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`
- Test: `tests/test_app.py`
- Test: `tests/scheduler/test_jobs.py`

- [ ] **Step 1: Write failing config tests**

Add to `tests/test_config.py`:

```python
def test_settings_reads_phase_two_ai_config(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("KB_TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("KB_AI_PROVIDER_CHAIN", "gemini:lite,ollama:qwen3:8b,heuristic")
    monkeypatch.setenv("KB_GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("KB_GEMINI_MODEL", "lite")
    monkeypatch.setenv("KB_OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("KB_OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.setenv("KB_AI_SYNC_WAIT_SECONDS", "4")
    monkeypatch.setenv("KB_AI_RETRY_INTERVAL_MINUTES", "15")

    settings = Settings.from_env()

    assert settings.ai_provider_chain == "gemini:lite,ollama:qwen3:8b,heuristic"
    assert settings.gemini_api_key == "gemini-key"
    assert settings.gemini_model == "lite"
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.ollama_model == "qwen3:8b"
    assert settings.ai_sync_wait_seconds == 4.0
    assert settings.ai_retry_interval_minutes == 15
```

- [ ] **Step 2: Write failing scheduler test**

Add to `tests/scheduler/test_jobs.py`:

```python
from kb_agent.scheduler.jobs import build_ai_retry_job


def test_build_ai_retry_job() -> None:
    job = build_ai_retry_job(interval_minutes=30)

    assert job.name == "ai_retry"
    assert job.kind == "ai_retry"
    assert job.interval_minutes == 30
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
pytest tests/test_config.py tests/scheduler/test_jobs.py -v
```

Expected: FAIL because settings and AI retry job do not exist.

- [ ] **Step 4: Add settings**

In `src/kb_agent/config.py`, add fields to `Settings`:

```python
    ai_provider_chain: str = "gemini:gemini-2.5-flash-lite,gemini:gemini-2.5-flash,ollama:qwen3:8b,heuristic"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ai_sync_wait_seconds: float = 6.0
    ai_retry_interval_minutes: int = 30
```

Add helpers:

```python
def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error
    if parsed < 0:
        raise ValueError(f"{name} must be zero or greater")
    return parsed
```

Populate these fields in `from_env()`:

```python
            ai_provider_chain=os.getenv("KB_AI_PROVIDER_CHAIN", cls.ai_provider_chain),
            gemini_api_key=os.getenv("KB_GEMINI_API_KEY", ""),
            gemini_model=os.getenv("KB_GEMINI_MODEL", cls.gemini_model),
            ollama_base_url=os.getenv("KB_OLLAMA_BASE_URL", cls.ollama_base_url),
            ollama_model=os.getenv("KB_OLLAMA_MODEL", cls.ollama_model),
            ai_sync_wait_seconds=_env_float("KB_AI_SYNC_WAIT_SECONDS", cls.ai_sync_wait_seconds),
            ai_retry_interval_minutes=int(
                _env_float("KB_AI_RETRY_INTERVAL_MINUTES", float(cls.ai_retry_interval_minutes)),
            ),
```

- [ ] **Step 5: Add scheduler job descriptor**

In `src/kb_agent/scheduler/jobs.py`, add:

```python
@dataclass(frozen=True)
class AIRetryJob:
    name: str
    kind: str
    interval_minutes: int


def build_ai_retry_job(*, interval_minutes: int) -> AIRetryJob:
    return AIRetryJob(name="ai_retry", kind="ai_retry", interval_minutes=interval_minutes)
```

- [ ] **Step 6: Wire runtime providers**

In `src/kb_agent/app.py`, import:

```python
from apscheduler.triggers.interval import IntervalTrigger
from kb_agent.ai.gemini import GeminiBriefProvider
from kb_agent.ai.ollama import OllamaBriefProvider
from kb_agent.ai.router import AIProviderRouter, ProviderChainEntry
```

Replace the heuristic-only provider setup with a builder:

```python
def build_ai_router(settings: Settings, http_client: httpx.AsyncClient) -> AIProviderRouter:
    chain = [ProviderChainEntry.parse(entry) for entry in settings.ai_provider_chain.split(",") if entry.strip()]
    heuristic = HeuristicAIProvider()
    providers = {"heuristic:heuristic": heuristic}
    for entry in chain:
        if entry.provider == "gemini":
            providers[entry.key()] = GeminiBriefProvider(
                http_client=http_client,
                api_key=settings.gemini_api_key,
                model=entry.model,
            )
        elif entry.provider == "ollama":
            providers[entry.key()] = OllamaBriefProvider(
                http_client=http_client,
                base_url=settings.ollama_base_url,
                model=entry.model,
            )
        elif entry.provider == "heuristic":
            providers[entry.key()] = heuristic
        else:
            raise ValueError(f"Unsupported AI provider in chain: {entry.provider}")
    return AIProviderRouter(chain=chain, providers=providers)
```

Use `ai_provider = build_ai_router(settings, http_client)` and pass it into `KnowledgeService`, `RetrievalService`, and `TelegramMessageHandler(ai_router=ai_provider, ai_sync_wait_seconds=settings.ai_sync_wait_seconds)`.

Register AI retry job after digest jobs:

```python
        async def retry_ai() -> None:
            await knowledge.retry_pending_ai(limit=10, max_attempts=3)

        scheduler.add_job(
            retry_ai,
            IntervalTrigger(minutes=settings.ai_retry_interval_minutes, timezone=settings.timezone),
            id="ai_retry",
            name="ai_retry",
            replace_existing=True,
        )
```

- [ ] **Step 7: Update `.env.example`**

Add:

```dotenv
KB_AI_PROVIDER_CHAIN=gemini:gemini-2.5-flash-lite,gemini:gemini-2.5-flash,ollama:qwen3:8b,heuristic
KB_GEMINI_API_KEY=
KB_GEMINI_MODEL=gemini-2.5-flash-lite
KB_OLLAMA_BASE_URL=http://localhost:11434
KB_OLLAMA_MODEL=qwen3:8b
KB_AI_SYNC_WAIT_SECONDS=6
KB_AI_RETRY_INTERVAL_MINUTES=30
```

- [ ] **Step 8: Run tests**

Run:

```bash
pytest tests/test_config.py tests/scheduler/test_jobs.py tests/test_app.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/kb_agent/config.py src/kb_agent/app.py src/kb_agent/scheduler/jobs.py .env.example tests/test_config.py tests/scheduler/test_jobs.py tests/test_app.py
git commit -m "feat: wire ai provider runtime config"
```

## Task 10: Documentation And Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/manual-qa.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update README**

Add a Phase 2 AI configuration section:

````markdown
## AI Understanding Layer

Phase 2 supports a provider chain for structured learning briefs:

```dotenv
KB_AI_PROVIDER_CHAIN=gemini:gemini-2.5-flash-lite,gemini:gemini-2.5-flash,ollama:qwen3:8b,heuristic
KB_GEMINI_API_KEY=
KB_OLLAMA_BASE_URL=http://localhost:11434
KB_OLLAMA_MODEL=qwen3:8b
```

Gemini is the default cloud path. Ollama is the local/private path. The heuristic provider is the final safe fallback.

Useful Telegram commands:

- `ai status`
- `model gemini:gemini-2.5-flash`
- `model ollama:qwen3:8b`
- `refresh kb_7f3a`
````

- [ ] **Step 2: Update manual QA**

Add:

```markdown
## Phase 2 AI Brief QA

1. Set `KB_AI_PROVIDER_CHAIN=gemini:gemini-2.5-flash-lite,heuristic`.
2. Set `KB_GEMINI_API_KEY`.
3. Save a link with a note and priority.
4. Confirm the bot shows an `ID: kb_...` alias.
5. Confirm the bot returns or follows up with a learning brief.
6. Send `ai status` and confirm the provider chain and pending retry count are shown.
7. Send `model gemini:gemini-2.5-flash` and confirm the bot acknowledges the selection.
8. Send `refresh <alias>` and confirm a new brief is returned.
9. Stop Ollama if using it, save another link, and confirm the bot says local AI is unavailable without losing the saved item.
```

- [ ] **Step 3: Update changelog**

Add an unreleased section:

```markdown
## Unreleased

### Added

- Structured AI learning briefs with Gemini, Ollama, and heuristic provider fallback.
- Telegram aliases for saved items.
- `ai status`, `model`, and `refresh` commands.
- Retryable AI enrichment state.
```

- [ ] **Step 4: Run focused and full verification**

Run:

```bash
pytest tests/ai tests/core tests/storage tests/telegram tests/scheduler tests/test_config.py tests/test_app.py -v
```

Expected: PASS.

Run:

```bash
pytest -v
```

Expected: PASS.

Run:

```bash
ruff check .
```

Expected: PASS.

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 5: Commit docs**

```bash
git add README.md docs/manual-qa.md CHANGELOG.md
git commit -m "docs: document phase 2 ai understanding"
```

## Implementation Notes

- Gemini structured output should use `responseMimeType: application/json` and `responseJsonSchema` in the REST request body.
- Ollama local generation should use `/api/generate` with `stream: false` and `format: json`.
- Existing retrieval can remain keyword/field-based in Phase 2. AI-generated title, topic, tags, summary, and takeaways improve the fields it already searches.
- The `heuristic` provider means rule-based local logic. It uses title/text/note word counts and simple summarization rules, not a real model call.
- If Codex cannot reach `http://localhost:11434`, test Ollama from the normal Mac terminal and rely on unit tests with `httpx.MockTransport` for automated verification.
