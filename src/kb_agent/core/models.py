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
