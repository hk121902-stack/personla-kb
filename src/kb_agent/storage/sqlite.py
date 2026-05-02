from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any

from kb_agent.core.models import Priority, SavedItem, SourceType, Status


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

    def _initialize_schema(self) -> None:
        schema = resources.files("kb_agent.storage").joinpath("schema.sql").read_text()
        with closing(self._connect()) as connection:
            with connection:
                connection.executescript(schema)

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
            embedding=json.loads(row["embedding_json"]),
        )


def _datetime_to_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _text_to_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)
