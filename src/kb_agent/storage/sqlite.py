from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any

from kb_agent.core.aliases import alias_for_item_id, is_item_alias
from kb_agent.core.models import AIStatus, LearningBrief, Priority, SavedItem, SourceType, Status

_AI_RETRY_WHERE = (
    "archived = 0 "
    "AND ai_status IN ('pending', 'retry_pending') "
    "AND (status != 'needs_text' OR trim(user_note) != '' OR trim(extracted_text) != '')"
)


class SQLiteItemRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def save(self, item: SavedItem) -> SavedItem:
        row = self._to_row(item)
        columns = tuple(row)
        placeholders = ", ".join(f":{column}" for column in columns)
        updates = ", ".join(
            f"{column} = excluded.{column}" for column in columns if column != "id"
        )
        sql = (
            f"INSERT INTO saved_items ({', '.join(columns)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}"
        )

        with closing(self._connect()) as connection:
            with connection:
                connection.execute(sql, row)

        return item

    def get(self, item_id: str) -> SavedItem | None:
        with closing(self._connect()) as connection:
            with connection:
                row = connection.execute(
                    "SELECT * FROM saved_items WHERE id = ?",
                    (item_id,),
                ).fetchone()

        if row is None:
            return None

        return self._from_row(row)

    def list_by_user(
        self,
        user_id: str,
        include_archived: bool = False,
    ) -> list[SavedItem]:
        if include_archived:
            sql = "SELECT * FROM saved_items WHERE user_id = ? ORDER BY created_at ASC, id ASC"
            parameters = (user_id,)
        else:
            sql = (
                "SELECT * FROM saved_items "
                "WHERE user_id = ? AND archived = 0 "
                "ORDER BY created_at ASC, id ASC"
            )
            parameters = (user_id,)

        with closing(self._connect()) as connection:
            with connection:
                rows = connection.execute(sql, parameters).fetchall()

        return [self._from_row(row) for row in rows]

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
                assigned_rows = connection.execute(
                    "SELECT id FROM saved_items WHERE user_id = ? AND item_alias = ? "
                    "ORDER BY created_at ASC, id ASC",
                    (user_id, ref),
                ).fetchall()
                if len(assigned_rows) == 1:
                    return assigned_rows[0]["id"]

                rows = connection.execute(
                    "SELECT id FROM saved_items WHERE user_id = ? AND lower(id) LIKE ? "
                    "ORDER BY length(id) ASC, id ASC",
                    (user_id, f"{prefix}%"),
                ).fetchall()
        if len(rows) != 1:
            return None
        return rows[0]["id"]

    def item_alias(self, user_id: str, item_id: str) -> str:
        with closing(self._connect()) as connection:
            with connection:
                row = connection.execute(
                    "SELECT id, user_id, item_alias FROM saved_items WHERE id = ?",
                    (item_id,),
                ).fetchone()
                if row is None or row["user_id"] != user_id:
                    return _fallback_alias(item_id)
                if row["item_alias"]:
                    return str(row["item_alias"])

                alias = _allocate_item_alias(connection, user_id=user_id, item_id=row["id"])
                connection.execute(
                    "UPDATE saved_items SET item_alias = ? WHERE id = ?",
                    (alias, row["id"]),
                )
                return alias

    def list_ai_retry_candidates(self, *, limit: int, max_attempts: int) -> list[SavedItem]:
        with closing(self._connect()) as connection:
            with connection:
                rows = connection.execute(
                    "SELECT * FROM saved_items "
                    f"WHERE {_AI_RETRY_WHERE} "
                    "AND ai_attempt_count < ? "
                    "ORDER BY ai_last_attempt_at IS NOT NULL, ai_last_attempt_at ASC, "
                    "created_at ASC, id ASC "
                    "LIMIT ?",
                    (max_attempts, limit),
                ).fetchall()
        return [self._from_row(row) for row in rows]

    def count_ai_retry_pending(self) -> int:
        with closing(self._connect()) as connection:
            with connection:
                row = connection.execute(
                    "SELECT COUNT(*) AS count FROM saved_items "
                    f"WHERE {_AI_RETRY_WHERE}",
                ).fetchone()
        return int(row["count"])

    def last_ai_error(self) -> str:
        with closing(self._connect()) as connection:
            with connection:
                row = connection.execute(
                    "SELECT ai_last_error FROM saved_items "
                    "WHERE ai_last_error != '' "
                    "ORDER BY ai_last_attempt_at IS NULL, ai_last_attempt_at DESC, "
                    "updated_at DESC "
                    "LIMIT 1",
                ).fetchone()
        if row is None:
            return ""
        return str(row["ai_last_error"])

    def _initialize_schema(self) -> None:
        schema = resources.files("kb_agent.storage").joinpath("schema.sql").read_text()
        with closing(self._connect()) as connection:
            with connection:
                connection.executescript(schema)
                _ensure_column(
                    connection,
                    "saved_items",
                    "learning_brief_json",
                    "TEXT NOT NULL DEFAULT '{}'",
                )
                _ensure_column(
                    connection,
                    "saved_items",
                    "ai_status",
                    "TEXT NOT NULL DEFAULT 'pending'",
                )
                _ensure_column(
                    connection,
                    "saved_items",
                    "ai_attempt_count",
                    "INTEGER NOT NULL DEFAULT 0",
                )
                _ensure_column(connection, "saved_items", "ai_last_attempt_at", "TEXT")
                _ensure_column(
                    connection,
                    "saved_items",
                    "ai_last_error",
                    "TEXT NOT NULL DEFAULT ''",
                )
                _ensure_column(
                    connection,
                    "saved_items",
                    "item_alias",
                    "TEXT NOT NULL DEFAULT ''",
                )
                _ensure_item_aliases(connection)
                _mark_blocked_ai_rows_non_retryable(connection)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _to_row(item: SavedItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "user_id": item.user_id,
            "url": item.url,
            "source_type": item.source_type.value,
            "title": item.title,
            "extracted_text": item.extracted_text,
            "user_note": item.user_note,
            "tags_json": json.dumps(list(item.tags)),
            "topic": item.topic,
            "summary": item.summary,
            "priority": item.priority.value,
            "status": item.status.value,
            "archived": int(item.archived),
            "archived_at": _datetime_to_text(item.archived_at),
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
            "last_surfaced_at": _datetime_to_text(item.last_surfaced_at),
            "surface_count": item.surface_count,
            "source_metadata_json": json.dumps(dict(item.source_metadata)),
            "learning_brief_json": _brief_to_json(item.learning_brief),
            "ai_status": item.ai_status.value,
            "ai_attempt_count": item.ai_attempt_count,
            "ai_last_attempt_at": _datetime_to_text(item.ai_last_attempt_at),
            "ai_last_error": item.ai_last_error,
            "embedding_json": json.dumps(list(item.embedding)),
        }

    @staticmethod
    def _from_row(row: Mapping[str, Any]) -> SavedItem:
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
            archived_at=_text_to_datetime(row["archived_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            last_surfaced_at=_text_to_datetime(row["last_surfaced_at"]),
            surface_count=row["surface_count"],
            source_metadata=json.loads(row["source_metadata_json"]),
            learning_brief=_json_to_brief(row["learning_brief_json"]),
            ai_status=AIStatus(row["ai_status"]),
            ai_attempt_count=row["ai_attempt_count"],
            ai_last_attempt_at=_text_to_datetime(row["ai_last_attempt_at"]),
            ai_last_error=row["ai_last_error"],
            embedding=json.loads(row["embedding_json"]),
        )


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


def _ensure_item_aliases(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        "SELECT id, user_id FROM saved_items "
        "WHERE item_alias = '' "
        "ORDER BY created_at ASC, id ASC",
    ).fetchall()
    for row in rows:
        alias = _allocate_item_alias(connection, user_id=row["user_id"], item_id=row["id"])
        connection.execute(
            "UPDATE saved_items SET item_alias = ? WHERE id = ?",
            (alias, row["id"]),
        )


def _allocate_item_alias(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    item_id: str,
) -> str:
    normalized = item_id.strip().lower()
    for length in range(4, min(32, len(normalized)) + 1):
        try:
            alias = alias_for_item_id(item_id, length=length)
        except ValueError:
            return item_id

        assigned = connection.execute(
            "SELECT id FROM saved_items WHERE user_id = ? AND item_alias = ?",
            (user_id, alias),
        ).fetchall()
        if assigned and any(row["id"] != item_id for row in assigned):
            continue

        prefix_rows = connection.execute(
            "SELECT id, item_alias FROM saved_items "
            "WHERE user_id = ? AND lower(id) LIKE ?",
            (user_id, f"{alias.removeprefix('kb_')}%"),
        ).fetchall()
        if any(row["id"] != item_id for row in prefix_rows):
            continue

        return alias

    return _fallback_alias(item_id)


def _mark_blocked_ai_rows_non_retryable(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        UPDATE saved_items
        SET ai_status = 'failed'
        WHERE status = 'needs_text'
          AND trim(user_note) = ''
          AND trim(extracted_text) = ''
          AND ai_status IN ('pending', 'retry_pending')
        """,
    )


def _fallback_alias(item_id: str) -> str:
    try:
        return alias_for_item_id(item_id)
    except ValueError:
        return item_id


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


def _datetime_to_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _text_to_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)
