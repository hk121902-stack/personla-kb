# Personal Knowledge Base Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram-first personal knowledge base agent that saves links, enriches them when possible, resurfaces them through digests, answers from saved knowledge first, and supports item-level archive review.

**Architecture:** Use a thin Telegram adapter over a tested knowledge core. Keep extraction, AI, storage, search, scheduling, and chat formatting behind focused modules so the bot surface remains simple and AI/storage providers can be swapped later.

**Tech Stack:** Python 3.12, SQLite, pytest, pytest-asyncio, ruff, pydantic, python-telegram-bot, httpx, beautifulsoup4, apscheduler, optional OpenAI-compatible provider through an adapter interface.

---

## Source Spec

- `docs/superpowers/specs/2026-05-03-personal-knowledge-base-agent-design.md`

## File Structure

- `pyproject.toml` - package metadata, dependencies, test and lint config.
- `.env.example` - local environment variables for Telegram, storage, AI provider, and digest schedule.
- `README.md` - local setup, bot commands, and development commands.
- `src/kb_agent/__init__.py` - package marker and version.
- `src/kb_agent/config.py` - environment-driven settings.
- `src/kb_agent/app.py` - runtime composition for bot, storage, providers, and scheduler.
- `src/kb_agent/core/models.py` - domain objects and enums.
- `src/kb_agent/core/ports.py` - storage, extractor, AI provider, clock, and scheduler protocols.
- `src/kb_agent/core/service.py` - save, note, priority, archive, enrich, and orchestration use cases.
- `src/kb_agent/core/retrieval.py` - saved-first retrieval and answer building.
- `src/kb_agent/core/digests.py` - daily and weekly digest selection and rendering data.
- `src/kb_agent/core/archive_review.py` - archive recommendation rules.
- `src/kb_agent/storage/schema.sql` - SQLite schema.
- `src/kb_agent/storage/sqlite.py` - SQLite repository implementation.
- `src/kb_agent/extraction/url_parser.py` - URL and source type detection.
- `src/kb_agent/extraction/extractors.py` - webpage extraction and manual fallback result handling.
- `src/kb_agent/ai/providers.py` - deterministic test provider and optional configured provider adapter.
- `src/kb_agent/telegram/parser.py` - Telegram text to command parsing.
- `src/kb_agent/telegram/formatter.py` - chat response formatting.
- `src/kb_agent/telegram/bot.py` - python-telegram-bot handlers.
- `src/kb_agent/scheduler/jobs.py` - scheduled daily and weekly job wiring.
- `tests/` - unit and adapter tests matching the modules above.

## Task 1: Project Skeleton And Tooling

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `README.md`
- Create: `src/kb_agent/__init__.py`
- Test: `tests/test_package_import.py`

- [ ] **Step 1: Write the failing import test**

Create `tests/test_package_import.py`:

```python
import kb_agent


def test_package_exposes_version() -> None:
    assert kb_agent.__version__ == "0.1.0"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_package_import.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'kb_agent'`.

- [ ] **Step 3: Add package skeleton and tooling**

Create `pyproject.toml` with this baseline:

```toml
[project]
name = "personal-kb-agent"
version = "0.1.0"
description = "Telegram-first personal knowledge base agent"
requires-python = ">=3.12"
dependencies = [
  "apscheduler>=3.10",
  "beautifulsoup4>=4.12",
  "httpx>=0.27",
  "pydantic>=2.7",
  "python-dotenv>=1.0",
  "python-telegram-bot>=21.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2",
  "pytest-asyncio>=0.23",
  "ruff>=0.5",
]
ai = [
  "openai>=1.40",
]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

Create `src/kb_agent/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `.env.example`:

```dotenv
TELEGRAM_BOT_TOKEN=
KB_DATABASE_PATH=./data/kb.sqlite3
KB_TIMEZONE=Asia/Kolkata
KB_DAILY_DIGEST_HOUR=9
KB_WEEKLY_DIGEST_DAY=sun
KB_WEEKLY_DIGEST_HOUR=10
KB_AI_PROVIDER=heuristic
OPENAI_API_KEY=
OPENAI_MODEL=
```

Create `README.md`:

````markdown
# Personal Knowledge Base Agent

Telegram-first personal knowledge base agent for saving links, resurfacing them, and asking saved-first questions.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```

## Runtime

Copy `.env.example` to `.env`, fill `TELEGRAM_BOT_TOKEN`, then run the bot after implementation:

```bash
python -m kb_agent.app
```
````

- [ ] **Step 4: Run the test and lint**

Run: `pytest tests/test_package_import.py -v`

Expected: PASS.

Run: `ruff check .`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example README.md src/kb_agent/__init__.py tests/test_package_import.py
git commit -m "chore: add project skeleton"
```

## Task 2: Domain Models And Ports

**Files:**
- Create: `src/kb_agent/core/models.py`
- Create: `src/kb_agent/core/ports.py`
- Test: `tests/core/test_models.py`

- [ ] **Step 1: Write failing model tests**

Create `tests/core/test_models.py`:

```python
from datetime import UTC, datetime

from kb_agent.core.models import Priority, SavedItem, SourceType, Status


def test_saved_item_defaults_to_active_processing_item() -> None:
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://youtu.be/demo",
        source_type=SourceType.YOUTUBE,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )

    assert item.id
    assert item.priority is Priority.UNSET
    assert item.status is Status.PROCESSING
    assert item.archived is False
    assert item.created_at == datetime(2026, 5, 3, 9, 0, tzinfo=UTC)


def test_saved_item_can_be_archived() -> None:
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/post",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )

    archived = item.archive(datetime(2026, 5, 4, 9, 0, tzinfo=UTC))

    assert archived.archived is True
    assert archived.archived_at == datetime(2026, 5, 4, 9, 0, tzinfo=UTC)
    assert archived.status is Status.PROCESSING
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_models.py -v`

Expected: FAIL with `ModuleNotFoundError` or import errors for `kb_agent.core.models`.

- [ ] **Step 3: Implement models and provider ports**

Create `src/kb_agent/core/models.py` with enums and immutable dataclasses:

```python
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import uuid4


class SourceType(StrEnum):
    X = "x"
    YOUTUBE = "youtube"
    LINKEDIN = "linkedin"
    WEB = "web"


class Priority(StrEnum):
    UNSET = "unset"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Status(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    NEEDS_TEXT = "needs_text"
    FAILED_ENRICHMENT = "failed_enrichment"


@dataclass(frozen=True)
class ExtractedContent:
    title: str
    text: str
    metadata: dict[str, str]


@dataclass(frozen=True)
class Enrichment:
    title: str
    tags: list[str]
    topic: str
    summary: str
    embedding: list[float]


@dataclass(frozen=True)
class SavedItem:
    id: str
    user_id: str
    url: str
    source_type: SourceType
    title: str
    extracted_text: str
    user_note: str
    tags: list[str]
    topic: str
    summary: str
    priority: Priority
    status: Status
    archived: bool
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    last_surfaced_at: datetime | None
    surface_count: int
    source_metadata: dict[str, str]
    embedding: list[float]

    @classmethod
    def new(
        cls,
        *,
        user_id: str,
        url: str,
        source_type: SourceType,
        now: datetime,
        note: str = "",
        priority: Priority = Priority.UNSET,
    ) -> SavedItem:
        return cls(
            id=uuid4().hex,
            user_id=user_id,
            url=url,
            source_type=source_type,
            title=url,
            extracted_text="",
            user_note=note,
            tags=[],
            topic="",
            summary="",
            priority=priority,
            status=Status.PROCESSING,
            archived=False,
            archived_at=None,
            created_at=now,
            updated_at=now,
            last_surfaced_at=None,
            surface_count=0,
            source_metadata={},
            embedding=[],
        )

    def archive(self, now: datetime) -> SavedItem:
        return replace(self, archived=True, archived_at=now, updated_at=now)
```

Create `src/kb_agent/core/ports.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from kb_agent.core.models import ExtractedContent, SavedItem


class Clock(Protocol):
    def now(self) -> datetime: ...


class ItemRepository(Protocol):
    def save(self, item: SavedItem) -> SavedItem: ...
    def get(self, item_id: str) -> SavedItem | None: ...
    def list_by_user(self, user_id: str, *, include_archived: bool = False) -> list[SavedItem]: ...


class Extractor(Protocol):
    async def extract(self, url: str) -> ExtractedContent | None: ...


class AIProvider(Protocol):
    async def enrich(self, item: SavedItem, extracted: ExtractedContent | None) -> SavedItem: ...
    async def synthesize_answer(self, question: str, matches: list[SavedItem]) -> str: ...
    async def synthesize_extra_context(self, question: str) -> str: ...
```

- [ ] **Step 4: Run model tests**

Run: `pytest tests/core/test_models.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kb_agent/core/models.py src/kb_agent/core/ports.py tests/core/test_models.py
git commit -m "feat: add knowledge domain models"
```

## Task 3: SQLite Storage

**Files:**
- Create: `src/kb_agent/storage/schema.sql`
- Create: `src/kb_agent/storage/sqlite.py`
- Create: `src/kb_agent/storage/__init__.py`
- Test: `tests/storage/test_sqlite_repository.py`

- [ ] **Step 1: Write failing repository tests**

Create `tests/storage/test_sqlite_repository.py`:

```python
from datetime import UTC, datetime

from kb_agent.core.models import Priority, SavedItem, SourceType
from kb_agent.storage.sqlite import SQLiteItemRepository


def test_repository_round_trips_saved_item(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/a",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        note="read for RAG evaluation",
        priority=Priority.HIGH,
    )

    repo.save(item)
    loaded = repo.get(item.id)

    assert loaded == item


def test_list_by_user_excludes_archived_items_by_default(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    active = SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/active",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )
    archived = SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/archive",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    ).archive(datetime(2026, 5, 4, 9, 0, tzinfo=UTC))

    repo.save(active)
    repo.save(archived)

    assert repo.list_by_user("telegram:123") == [active]
    assert repo.list_by_user("telegram:123", include_archived=True) == [active, archived]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/storage/test_sqlite_repository.py -v`

Expected: FAIL because `kb_agent.storage.sqlite` does not exist.

- [ ] **Step 3: Implement schema and repository**

Create `src/kb_agent/storage/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS saved_items (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  url TEXT NOT NULL,
  source_type TEXT NOT NULL,
  title TEXT NOT NULL,
  extracted_text TEXT NOT NULL,
  user_note TEXT NOT NULL,
  tags_json TEXT NOT NULL,
  topic TEXT NOT NULL,
  summary TEXT NOT NULL,
  priority TEXT NOT NULL,
  status TEXT NOT NULL,
  archived INTEGER NOT NULL,
  archived_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_surfaced_at TEXT,
  surface_count INTEGER NOT NULL,
  source_metadata_json TEXT NOT NULL,
  embedding_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_saved_items_user_archived
ON saved_items(user_id, archived, created_at);
```

Create `src/kb_agent/storage/__init__.py`:

```python
__all__ = ["sqlite"]
```

Create `src/kb_agent/storage/sqlite.py` with these required methods:

```python
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from kb_agent.core.models import Priority, SavedItem, SourceType, Status


class SQLiteItemRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        schema = Path(__file__).with_name("schema.sql").read_text()
        with self._connect() as connection:
            connection.executescript(schema)

    def save(self, item: SavedItem) -> SavedItem:
        payload = self._to_row(item)
        columns = ", ".join(payload)
        placeholders = ", ".join(":" + key for key in payload)
        updates = ", ".join(f"{key}=excluded.{key}" for key in payload if key != "id")
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO saved_items ({columns})
                VALUES ({placeholders})
                ON CONFLICT(id) DO UPDATE SET {updates}
                """,
                payload,
            )
        return item

    def get(self, item_id: str) -> SavedItem | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM saved_items WHERE id = ?", (item_id,)).fetchone()
        return self._from_row(row) if row else None

    def list_by_user(self, user_id: str, *, include_archived: bool = False) -> list[SavedItem]:
        query = "SELECT * FROM saved_items WHERE user_id = ?"
        params: list[object] = [user_id]
        if not include_archived:
            query += " AND archived = 0"
        query += " ORDER BY created_at ASC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._from_row(row) for row in rows]

    def _to_row(self, item: SavedItem) -> dict[str, object]:
        return {
            "id": item.id,
            "user_id": item.user_id,
            "url": item.url,
            "source_type": item.source_type.value,
            "title": item.title,
            "extracted_text": item.extracted_text,
            "user_note": item.user_note,
            "topic": item.topic,
            "summary": item.summary,
            "priority": item.priority.value,
            "status": item.status.value,
            "archived": 1 if item.archived else 0,
            "archived_at": item.archived_at.isoformat() if item.archived_at else None,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
            "last_surfaced_at": item.last_surfaced_at.isoformat() if item.last_surfaced_at else None,
            "tags_json": json.dumps(item.tags),
            "source_metadata_json": json.dumps(item.source_metadata),
            "embedding_json": json.dumps(item.embedding),
        }

    def _from_row(self, row: sqlite3.Row) -> SavedItem:
        return SavedItem(
            id=row["id"],
            user_id=row["user_id"],
            url=row["url"],
            source_type=SourceType(row["source_type"]),
            title=row["title"],
            extracted_text=row["extracted_text"],
            user_note=row["user_note"],
            tags=json.loads(row["tags_json"]),
            topic=row["topic"],
            summary=row["summary"],
            priority=Priority(row["priority"]),
            status=Status(row["status"]),
            archived=bool(row["archived"]),
            archived_at=datetime.fromisoformat(row["archived_at"]) if row["archived_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            last_surfaced_at=datetime.fromisoformat(row["last_surfaced_at"]) if row["last_surfaced_at"] else None,
            surface_count=row["surface_count"],
            source_metadata=json.loads(row["source_metadata_json"]),
            embedding=json.loads(row["embedding_json"]),
        )
```

- [ ] **Step 4: Run storage tests**

Run: `pytest tests/storage/test_sqlite_repository.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kb_agent/storage tests/storage/test_sqlite_repository.py
git commit -m "feat: persist saved items in sqlite"
```

## Task 4: URL Parsing And Extraction Fallback

**Files:**
- Create: `src/kb_agent/extraction/__init__.py`
- Create: `src/kb_agent/extraction/url_parser.py`
- Create: `src/kb_agent/extraction/extractors.py`
- Test: `tests/extraction/test_url_parser.py`
- Test: `tests/extraction/test_extractors.py`

- [ ] **Step 1: Write failing parser and extractor tests**

Create `tests/extraction/test_url_parser.py`:

```python
from kb_agent.core.models import SourceType
from kb_agent.extraction.url_parser import detect_source_type, find_first_url


def test_find_first_url_from_message() -> None:
    assert find_first_url("save https://x.com/user/status/1 note this") == "https://x.com/user/status/1"


def test_detects_primary_source_types() -> None:
    assert detect_source_type("https://x.com/user/status/1") is SourceType.X
    assert detect_source_type("https://youtube.com/watch?v=abc") is SourceType.YOUTUBE
    assert detect_source_type("https://youtu.be/abc") is SourceType.YOUTUBE
    assert detect_source_type("https://linkedin.com/posts/demo") is SourceType.LINKEDIN
    assert detect_source_type("https://example.com/article") is SourceType.WEB
```

Create `tests/extraction/test_extractors.py`:

```python
import httpx
import pytest

from kb_agent.extraction.extractors import WebpageExtractor


@pytest.mark.asyncio
async def test_webpage_extractor_reads_title_and_text() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            html="<html><head><title>RAG Notes</title></head><body><main>Hello retrieval</main></body></html>",
        )

    extractor = WebpageExtractor(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    result = await extractor.extract("https://example.com/rag")

    assert result is not None
    assert result.title == "RAG Notes"
    assert "Hello retrieval" in result.text


@pytest.mark.asyncio
async def test_webpage_extractor_returns_none_when_blocked() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    extractor = WebpageExtractor(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    assert await extractor.extract("https://example.com/private") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/extraction -v`

Expected: FAIL because extraction modules do not exist.

- [ ] **Step 3: Implement URL parser and webpage extractor**

Implement `find_first_url()` with a conservative `https?://` regex. Implement `detect_source_type()` using hostname checks for `x.com`, `twitter.com`, `youtube.com`, `youtu.be`, and `linkedin.com`.

Implement `WebpageExtractor.extract()` so it:

- Uses the injected `httpx.AsyncClient`.
- Returns `None` for non-2xx responses.
- Parses `<title>` and visible text with BeautifulSoup.
- Returns `ExtractedContent(title=..., text=..., metadata={"status_code": "200"})`.

- [ ] **Step 4: Run extraction tests**

Run: `pytest tests/extraction -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kb_agent/extraction tests/extraction
git commit -m "feat: detect links and extract webpage content"
```

## Task 5: Deterministic AI Provider

**Files:**
- Create: `src/kb_agent/ai/__init__.py`
- Create: `src/kb_agent/ai/providers.py`
- Test: `tests/ai/test_heuristic_provider.py`

- [ ] **Step 1: Write failing provider tests**

Create `tests/ai/test_heuristic_provider.py`:

```python
from datetime import UTC, datetime

import pytest

from kb_agent.ai.providers import HeuristicAIProvider
from kb_agent.core.models import ExtractedContent, SavedItem, SourceType, Status


@pytest.mark.asyncio
async def test_heuristic_provider_enriches_from_extracted_content() -> None:
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/rag",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        note="useful for retrieval evaluation",
    )
    extracted = ExtractedContent(
        title="RAG Evaluation Guide",
        text="Retrieval augmented generation evaluation uses recall and precision.",
        metadata={"status_code": "200"},
    )

    enriched = await HeuristicAIProvider().enrich(item, extracted)

    assert enriched.status is Status.READY
    assert enriched.title == "RAG Evaluation Guide"
    assert "retrieval" in enriched.tags
    assert enriched.topic
    assert enriched.summary
    assert enriched.embedding


@pytest.mark.asyncio
async def test_heuristic_provider_marks_missing_content_as_needs_text() -> None:
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://linkedin.com/posts/private",
        source_type=SourceType.LINKEDIN,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )

    enriched = await HeuristicAIProvider().enrich(item, None)

    assert enriched.status is Status.NEEDS_TEXT
    assert enriched.title == item.url
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ai/test_heuristic_provider.py -v`

Expected: FAIL because `kb_agent.ai.providers` does not exist.

- [ ] **Step 3: Implement the deterministic provider**

Create a provider that is good enough for tests and local development without external keys:

- Title comes from extracted content title.
- Tags come from normalized frequent words across title, text, and note, excluding common stop words.
- Topic is the first two generated tags joined with a space, or source type value.
- Summary is the first sentence or first 180 characters.
- Embedding is a deterministic bag-of-words vector with fixed length 32.
- Missing extraction sets status `needs_text`.

Keep an `OpenAIProvider` class out of this task unless the provider can be added without network calls in tests. The provider port is already present, so a real provider can be added after the MVP core works.

- [ ] **Step 4: Run provider tests**

Run: `pytest tests/ai/test_heuristic_provider.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kb_agent/ai tests/ai/test_heuristic_provider.py
git commit -m "feat: add deterministic ai provider"
```

## Task 6: Knowledge Core Save, Note, Priority, And Archive

**Files:**
- Create: `src/kb_agent/core/service.py`
- Test: `tests/core/test_knowledge_service.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/core/test_knowledge_service.py`:

```python
from datetime import UTC, datetime

import pytest

from kb_agent.ai.providers import HeuristicAIProvider
from kb_agent.core.models import ExtractedContent, Priority, Status
from kb_agent.core.service import KnowledgeService, SystemClock
from kb_agent.extraction.extractors import StaticExtractor
from kb_agent.storage.sqlite import SQLiteItemRepository


class FixedClock(SystemClock):
    def now(self):
        return datetime(2026, 5, 3, 9, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_save_link_with_note_and_priority_enriches_item(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(
            ExtractedContent(
                title="Vector DB Notes",
                text="Vector search helps semantic retrieval.",
                metadata={},
            )
        ),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )

    item = await service.save_link(
        user_id="telegram:123",
        url="https://example.com/vector",
        note="learn for personal search",
        priority=Priority.HIGH,
    )

    assert item.status is Status.READY
    assert item.priority is Priority.HIGH
    assert item.user_note == "learn for personal search"
    assert repo.get(item.id) == item


@pytest.mark.asyncio
async def test_save_link_survives_extraction_failure(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(None),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )

    item = await service.save_link(
        user_id="telegram:123",
        url="https://linkedin.com/posts/private",
    )

    assert item.status is Status.NEEDS_TEXT
    assert repo.get(item.id) == item


@pytest.mark.asyncio
async def test_archive_excludes_item_from_active_list(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    service = KnowledgeService(
        repository=repo,
        extractor=StaticExtractor(None),
        ai_provider=HeuristicAIProvider(),
        clock=FixedClock(),
    )
    item = await service.save_link(user_id="telegram:123", url="https://example.com/old")

    archived = service.archive_item(user_id="telegram:123", item_id=item.id)

    assert archived.archived is True
    assert repo.list_by_user("telegram:123") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_knowledge_service.py -v`

Expected: FAIL because `KnowledgeService` and `StaticExtractor` do not exist.

- [ ] **Step 3: Implement service orchestration**

Add `StaticExtractor` to `src/kb_agent/extraction/extractors.py` for tests:

```python
class StaticExtractor:
    def __init__(self, content: ExtractedContent | None) -> None:
        self.content = content

    async def extract(self, url: str) -> ExtractedContent | None:
        return self.content
```

Create `src/kb_agent/core/service.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime

from kb_agent.core.models import Priority, SavedItem
from kb_agent.core.ports import AIProvider, Clock, Extractor, ItemRepository
from kb_agent.extraction.url_parser import detect_source_type


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class KnowledgeService:
    def __init__(
        self,
        *,
        repository: ItemRepository,
        extractor: Extractor,
        ai_provider: AIProvider,
        clock: Clock,
    ) -> None:
        self.repository = repository
        self.extractor = extractor
        self.ai_provider = ai_provider
        self.clock = clock

    async def save_link(
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
        extracted = await self.extractor.extract(url)
        enriched = await self.ai_provider.enrich(item, extracted)
        self.repository.save(enriched)
        return enriched

    def archive_item(self, *, user_id: str, item_id: str) -> SavedItem:
        item = self.repository.get(item_id)
        if item is None or item.user_id != user_id:
            raise ValueError("Saved item not found")
        archived = item.archive(self.clock.now())
        self.repository.save(archived)
        return archived
```

Add note and priority update methods in the same service using `dataclasses.replace()` and repository persistence.

- [ ] **Step 4: Run service tests**

Run: `pytest tests/core/test_knowledge_service.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kb_agent/core/service.py src/kb_agent/extraction/extractors.py tests/core/test_knowledge_service.py
git commit -m "feat: save and archive knowledge items"
```

## Task 7: Saved-First Retrieval

**Files:**
- Create: `src/kb_agent/core/retrieval.py`
- Test: `tests/core/test_retrieval.py`

- [ ] **Step 1: Write failing retrieval tests**

Create `tests/core/test_retrieval.py`:

```python
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from kb_agent.ai.providers import HeuristicAIProvider
from kb_agent.core.models import SavedItem, SourceType, Status
from kb_agent.core.retrieval import RetrievalService
from kb_agent.storage.sqlite import SQLiteItemRepository


def ready_item(url: str, title: str, text: str, *, archived: bool = False) -> SavedItem:
    item = SavedItem.new(
        user_id="telegram:123",
        url=url,
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )
    return replace(
        item,
        title=title,
        extracted_text=text,
        tags=["retrieval", "rag"],
        topic="retrieval rag",
        summary=text,
        status=Status.READY,
        archived=archived,
    )


@pytest.mark.asyncio
async def test_retrieval_excludes_archived_by_default(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    active = ready_item("https://example.com/active", "RAG Search", "semantic retrieval notes")
    archived = ready_item("https://example.com/archived", "Old RAG", "semantic retrieval archive", archived=True)
    repo.save(active)
    repo.save(archived)

    response = await RetrievalService(repo, HeuristicAIProvider()).answer(
        user_id="telegram:123",
        question="What did I save about retrieval?",
    )

    assert "From your knowledge base" in response.text
    assert "RAG Search" in response.text
    assert "Old RAG" not in response.text


@pytest.mark.asyncio
async def test_retrieval_can_include_archived(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    archived = ready_item("https://example.com/archived", "Old RAG", "semantic retrieval archive", archived=True)
    repo.save(archived)

    response = await RetrievalService(repo, HeuristicAIProvider()).answer(
        user_id="telegram:123",
        question="include archived retrieval",
        include_archived=True,
    )

    assert "Old RAG" in response.text


@pytest.mark.asyncio
async def test_retrieval_reports_weak_matches(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    repo.save(ready_item("https://example.com/cooking", "Cooking", "sourdough starter"))

    response = await RetrievalService(repo, HeuristicAIProvider()).answer(
        user_id="telegram:123",
        question="kubernetes autoscaling",
    )

    assert "I did not find a strong match" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_retrieval.py -v`

Expected: FAIL because `RetrievalService` does not exist.

- [ ] **Step 3: Implement retrieval**

Create `src/kb_agent/core/retrieval.py` with:

- `RetrievalResponse(text: str, matches: list[SavedItem])`.
- Token overlap scoring across title, tags, topic, summary, note, and extracted text.
- Archived exclusion by default through repository `list_by_user()`.
- Weak match threshold of `0.15`.
- Response format with `From your knowledge base`, `Sources`, and `Extra context`.

Use `AIProvider.synthesize_answer()` for the grounded paragraph and `AIProvider.synthesize_extra_context()` for the second section only when there is at least one match or the question asks for explanation.

- [ ] **Step 4: Run retrieval tests**

Run: `pytest tests/core/test_retrieval.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kb_agent/core/retrieval.py tests/core/test_retrieval.py
git commit -m "feat: answer questions from saved knowledge first"
```

## Task 8: Digests And Archive Recommendations

**Files:**
- Create: `src/kb_agent/core/digests.py`
- Create: `src/kb_agent/core/archive_review.py`
- Test: `tests/core/test_digests.py`
- Test: `tests/core/test_archive_review.py`

- [ ] **Step 1: Write failing digest and archive tests**

Create `tests/core/test_digests.py`:

```python
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from kb_agent.core.digests import DigestService
from kb_agent.core.models import Priority, SavedItem, SourceType, Status
from kb_agent.storage.sqlite import SQLiteItemRepository


def item(title: str, priority: Priority, days_old: int) -> SavedItem:
    created = datetime(2026, 5, 3, 9, 0, tzinfo=UTC) - timedelta(days=days_old)
    return replace(
        SavedItem.new(user_id="telegram:123", url=f"https://example.com/{title}", source_type=SourceType.WEB, now=created),
        title=title,
        tags=["ai"],
        topic="ai",
        summary=f"{title} summary",
        priority=priority,
        status=Status.READY,
    )


def test_daily_digest_selects_up_to_three_active_items(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    for saved in [item("one", Priority.HIGH, 1), item("two", Priority.MEDIUM, 2), item("three", Priority.UNSET, 3), item("four", Priority.LOW, 4)]:
        repo.save(saved)

    digest = DigestService(repo).daily(user_id="telegram:123")

    assert len(digest.items) == 3
    assert "Daily tiny nudge" in digest.text


def test_weekly_digest_groups_items_by_topic(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    repo.save(item("rag", Priority.HIGH, 1))
    repo.save(replace(item("eval", Priority.MEDIUM, 2), topic="ai eval"))

    digest = DigestService(repo).weekly(user_id="telegram:123")

    assert "Weekly synthesis" in digest.text
    assert "ai" in digest.text
```

Create `tests/core/test_archive_review.py`:

```python
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from kb_agent.core.archive_review import ArchiveReviewService
from kb_agent.core.models import Priority, SavedItem, SourceType, Status
from kb_agent.storage.sqlite import SQLiteItemRepository


def saved(title: str, text: str, priority: Priority, days_old: int) -> SavedItem:
    created = datetime(2026, 5, 3, 9, 0, tzinfo=UTC) - timedelta(days=days_old)
    return replace(
        SavedItem.new(user_id="telegram:123", url=f"https://example.com/{title}", source_type=SourceType.WEB, now=created),
        title=title,
        extracted_text=text,
        priority=priority,
        status=Status.READY,
    )


def test_recommends_old_low_priority_items(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    old_low = saved("old", "old low priority", Priority.LOW, 61)
    recent_low = saved("recent", "recent low priority", Priority.LOW, 10)
    repo.save(old_low)
    repo.save(recent_low)

    recommendations = ArchiveReviewService(repo).recommend(user_id="telegram:123", now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC))

    assert [rec.item.id for rec in recommendations] == [old_low.id]
    assert recommendations[0].reason == "old_low_priority"


def test_recommends_older_duplicate_items(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    older = saved("older rag", "retrieval augmented generation evaluation guide", Priority.UNSET, 20)
    newer = saved("newer rag", "retrieval augmented generation evaluation guide", Priority.HIGH, 1)
    repo.save(older)
    repo.save(newer)

    recommendations = ArchiveReviewService(repo).recommend(user_id="telegram:123", now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC))

    assert recommendations[0].item.id == older.id
    assert recommendations[0].reason == "duplicate_overlap"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_digests.py tests/core/test_archive_review.py -v`

Expected: FAIL because digest and archive review modules do not exist.

- [ ] **Step 3: Implement digest and archive services**

Implement `DigestService.daily()`:

- Pull active ready items.
- Sort high, medium, unset, low priority first, then by least recent `last_surfaced_at`, then newest created date.
- Return at most 3 items.
- Render text starting with `Daily tiny nudge`.

Implement `DigestService.weekly()`:

- Pull active ready items.
- Group by `topic` falling back to first tag or `general`.
- Return at most 7 items.
- Render text starting with `Weekly synthesis`.

Implement `ArchiveReviewService.recommend()`:

- Recommend items at least 60 days old with priority `low`.
- Recommend older duplicate items when token overlap with a newer item is at least `0.80`.
- Return recommendation objects with `item` and `reason`.
- Do not mutate or archive items.

- [ ] **Step 4: Run digest and archive tests**

Run: `pytest tests/core/test_digests.py tests/core/test_archive_review.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kb_agent/core/digests.py src/kb_agent/core/archive_review.py tests/core/test_digests.py tests/core/test_archive_review.py
git commit -m "feat: add digests and archive recommendations"
```

## Task 9: Telegram Command Parser And Formatters

**Files:**
- Create: `src/kb_agent/telegram/__init__.py`
- Create: `src/kb_agent/telegram/parser.py`
- Create: `src/kb_agent/telegram/formatter.py`
- Test: `tests/telegram/test_parser.py`
- Test: `tests/telegram/test_formatter.py`

- [ ] **Step 1: Write failing parser and formatter tests**

Create `tests/telegram/test_parser.py`:

```python
from kb_agent.core.models import Priority
from kb_agent.telegram.parser import AskCommand, ParseCommand, SaveCommand, parse_message


def test_plain_link_becomes_save_command() -> None:
    command = parse_message("https://youtu.be/abc note: watch this priority: high")

    assert isinstance(command, SaveCommand)
    assert command.url == "https://youtu.be/abc"
    assert command.note == "watch this"
    assert command.priority is Priority.HIGH


def test_plain_question_becomes_ask_command() -> None:
    command = parse_message("what did I save about vector databases?")

    assert isinstance(command, AskCommand)
    assert command.question == "what did I save about vector databases?"


def test_include_archived_flag() -> None:
    command = parse_message("ask include archived vector databases")

    assert isinstance(command, AskCommand)
    assert command.include_archived is True


def test_unknown_empty_message_is_parse_command() -> None:
    assert isinstance(parse_message("   "), ParseCommand)
```

Create `tests/telegram/test_formatter.py`:

```python
from dataclasses import replace
from datetime import UTC, datetime

from kb_agent.core.models import Priority, SavedItem, SourceType, Status
from kb_agent.telegram.formatter import format_save_confirmation


def test_save_confirmation_is_compact() -> None:
    item = replace(
        SavedItem.new(user_id="telegram:123", url="https://example.com/rag", source_type=SourceType.WEB, now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC)),
        title="RAG Notes",
        tags=["rag", "retrieval"],
        priority=Priority.HIGH,
        status=Status.READY,
    )

    text = format_save_confirmation(item)

    assert "Saved: RAG Notes" in text
    assert "Tags: rag, retrieval" in text
    assert "Priority: high" in text
    assert "Status: ready" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/telegram -v`

Expected: FAIL because Telegram parser and formatter modules do not exist.

- [ ] **Step 3: Implement parser and formatter**

Create command dataclasses:

- `SaveCommand(url: str, note: str, priority: Priority)`
- `AskCommand(question: str, include_archived: bool)`
- `DigestCommand(kind: Literal["today", "week"])`
- `ArchiveCommand(item_id: str)`
- `ReviewArchiveCommand()`
- `ShowCommand(query: str)`
- `ParseCommand(message: str)`

Implement `parse_message()`:

- Empty text returns `ParseCommand`.
- Text containing a URL returns `SaveCommand`.
- `priority: high|medium|low` sets priority and removes the token from note text.
- `note:` captures the rest of the note until `priority:` or end.
- Text starting `digest today`, `digest week`, `review archive`, `archive`, and `show` maps to command classes.
- Everything else maps to `AskCommand`.

Implement formatters for:

- Save confirmation.
- `needs_text` extraction fallback prompt.
- Retrieval response pass-through.
- Daily and weekly digest text pass-through.
- Archive recommendation list.

- [ ] **Step 4: Run parser and formatter tests**

Run: `pytest tests/telegram -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kb_agent/telegram tests/telegram
git commit -m "feat: parse and format telegram messages"
```

## Task 10: Telegram Bot Adapter

**Files:**
- Create: `src/kb_agent/telegram/bot.py`
- Test: `tests/telegram/test_bot_adapter.py`

- [ ] **Step 1: Write failing adapter tests**

Create `tests/telegram/test_bot_adapter.py` using fake services instead of Telegram network calls:

```python
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from kb_agent.core.models import SavedItem, SourceType, Status
from kb_agent.telegram.bot import TelegramMessageHandler


class FakeKnowledge:
    async def save_link(self, *, user_id, url, note="", priority=None):
        item = SavedItem.new(user_id=user_id, url=url, source_type=SourceType.WEB, now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC))
        return replace(item, title="Saved Title", status=Status.READY, tags=["saved"])


class FakeRetrieval:
    async def answer(self, *, user_id, question, include_archived=False):
        return type("Response", (), {"text": "From your knowledge base\nAnswer", "matches": []})()


@pytest.mark.asyncio
async def test_handler_saves_plain_link() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="https://example.com/rag",
        reply=replies.append,
    )

    assert "Saved: Saved Title" in replies[0]


@pytest.mark.asyncio
async def test_handler_answers_plain_question() -> None:
    replies = []
    handler = TelegramMessageHandler(
        knowledge=FakeKnowledge(),
        retrieval=FakeRetrieval(),
        digest_service=None,
        archive_review_service=None,
    )

    await handler.handle_text(
        user_id="telegram:123",
        text="what did I save about rag?",
        reply=replies.append,
    )

    assert replies == ["From your knowledge base\nAnswer"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/telegram/test_bot_adapter.py -v`

Expected: FAIL because `TelegramMessageHandler` does not exist.

- [ ] **Step 3: Implement handler class and runtime builder**

Implement `TelegramMessageHandler.handle_text()` so it:

- Parses text with `parse_message()`.
- Calls `KnowledgeService.save_link()` for save commands.
- Calls `RetrievalService.answer()` for ask commands.
- Calls digest and archive services for their commands.
- Sends user-facing text through the injected `reply` callable.

Add `build_application(handler, token)` that creates a `python-telegram-bot` `Application`, registers a text message handler, and converts Telegram user id to `telegram:<id>`.

- [ ] **Step 4: Run adapter tests**

Run: `pytest tests/telegram/test_bot_adapter.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kb_agent/telegram/bot.py tests/telegram/test_bot_adapter.py
git commit -m "feat: add telegram bot adapter"
```

## Task 11: Scheduler And Runtime Composition

**Files:**
- Create: `src/kb_agent/config.py`
- Create: `src/kb_agent/scheduler/__init__.py`
- Create: `src/kb_agent/scheduler/jobs.py`
- Create: `src/kb_agent/app.py`
- Test: `tests/test_config.py`
- Test: `tests/scheduler/test_jobs.py`

- [ ] **Step 1: Write failing config and scheduler tests**

Create `tests/test_config.py`:

```python
from kb_agent.config import Settings


def test_settings_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("KB_DATABASE_PATH", "./tmp/kb.sqlite3")

    settings = Settings.from_env()

    assert settings.telegram_bot_token == "token"
    assert settings.database_path == "./tmp/kb.sqlite3"
    assert settings.ai_provider == "heuristic"
```

Create `tests/scheduler/test_jobs.py`:

```python
from kb_agent.scheduler.jobs import build_digest_jobs


def test_build_digest_jobs_returns_daily_and_weekly_jobs() -> None:
    jobs = build_digest_jobs(user_id="telegram:123", daily_hour=9, weekly_day="sun", weekly_hour=10)

    assert [job.name for job in jobs] == ["daily_digest", "weekly_digest"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py tests/scheduler/test_jobs.py -v`

Expected: FAIL because config and scheduler modules do not exist.

- [ ] **Step 3: Implement settings, scheduler descriptors, and app composition**

Implement `Settings.from_env()`:

- Reads `.env` with `python-dotenv`.
- Requires `TELEGRAM_BOT_TOKEN`.
- Defaults database path to `./data/kb.sqlite3`.
- Defaults timezone to `Asia/Kolkata`.
- Defaults AI provider to `heuristic`.

Implement `build_digest_jobs()` as pure job descriptors first. Wire APScheduler in `app.py` after tests pass.

Implement `src/kb_agent/app.py` so `python -m kb_agent.app`:

- Builds settings.
- Builds SQLite repository.
- Builds `WebpageExtractor`.
- Builds `HeuristicAIProvider`.
- Builds knowledge, retrieval, digest, and archive services.
- Builds Telegram handler and application.
- Starts polling.

- [ ] **Step 4: Run config and scheduler tests**

Run: `pytest tests/test_config.py tests/scheduler/test_jobs.py -v`

Expected: PASS.

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/kb_agent/config.py src/kb_agent/scheduler src/kb_agent/app.py tests/test_config.py tests/scheduler/test_jobs.py
git commit -m "feat: wire runtime settings and scheduled digests"
```

## Task 12: Documentation, Manual QA, And MVP Readiness

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Create: `docs/manual-qa.md`

- [ ] **Step 1: Update README with final command reference**

Add these sections to `README.md`:

```markdown
## Telegram Commands

- Send a plain link to save it.
- `save <link> note: <note> priority: high|medium|low`
- `ask <question>`
- `digest today`
- `digest week`
- `review archive`
- `archive <item_id>`
- `show <topic-or-tag>`

Archived items are excluded from default answers and digests.

## Extraction Fallback

Some X and LinkedIn content may be blocked by platform access rules. The bot still saves the link and asks you to paste the useful text when extraction fails.
```

- [ ] **Step 2: Add manual QA checklist**

Create `docs/manual-qa.md`:

```markdown
# Manual QA

## Local Bot Smoke Test

1. Create a Telegram bot token with BotFather.
2. Copy `.env.example` to `.env`.
3. Set `TELEGRAM_BOT_TOKEN`.
4. Run `python -m kb_agent.app`.
5. Send `https://example.com`.
6. Confirm the bot replies with `Saved:`.
7. Send `ask what did I save?`.
8. Confirm the bot replies with `From your knowledge base`.
9. Send `digest today`.
10. Confirm the bot returns 1-3 active items.
11. Send `review archive`.
12. Confirm the bot returns recommendations or says none are ready.

## Trust Checks

- Extraction failure keeps the link saved.
- Archived items do not appear in default answers.
- Weak search matches are labelled clearly.
- Archive recommendations do not archive automatically.
```

- [ ] **Step 3: Run verification**

Run: `pytest -v`

Expected: PASS.

Run: `ruff check .`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md .env.example docs/manual-qa.md
git commit -m "docs: document telegram kb agent usage"
```

## Final Verification

- [ ] Run `pytest -v` and confirm all tests pass.
- [ ] Run `ruff check .` and confirm lint passes.
- [ ] Run `git status --short` and confirm only intended files are changed.
- [ ] Start the bot locally with a real token and complete the manual QA smoke test.

## Plan Self-Review

- Spec coverage: capture, extraction fallback, notes, priority, saved-first retrieval, digest cadence, archive recommendations, item-level archive, provider swapping, Telegram adapter, scheduler, and trust behavior are covered by tasks.
- Placeholder scan: no unresolved placeholders are intended in this plan.
- Type consistency: models use `Priority`, `Status`, `SourceType`, `SavedItem`, `ExtractedContent`, and `Enrichment` consistently across tasks.
