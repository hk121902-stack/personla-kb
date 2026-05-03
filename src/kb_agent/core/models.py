from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import uuid4


class FrozenList[T](list[T]):
    def _blocked(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("FrozenList cannot be mutated")

    append = _blocked
    clear = _blocked
    extend = _blocked
    insert = _blocked
    pop = _blocked
    remove = _blocked
    reverse = _blocked
    sort = _blocked
    __delitem__ = _blocked
    __iadd__ = _blocked
    __imul__ = _blocked
    __setitem__ = _blocked


class FrozenDict[K, V](dict[K, V]):
    def _blocked(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("FrozenDict cannot be mutated")

    clear = _blocked
    pop = _blocked
    popitem = _blocked
    setdefault = _blocked
    update = _blocked
    __delitem__ = _blocked
    __ior__ = _blocked
    __setitem__ = _blocked


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


class AIStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RETRY_PENDING = "retry_pending"
    FAILED = "failed"


@dataclass(frozen=True)
class ExtractedContent:
    title: str
    text: str
    metadata: dict[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", FrozenDict(self.metadata))


@dataclass(frozen=True)
class Enrichment:
    title: str
    tags: list[str]
    topic: str
    summary: str
    embedding: list[float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tags", FrozenList(self.tags))
        object.__setattr__(self, "embedding", FrozenList(self.embedding))


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
    learning_brief: LearningBrief | None
    ai_status: AIStatus
    ai_attempt_count: int
    ai_last_attempt_at: datetime | None
    ai_last_error: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tags", FrozenList(self.tags))
        object.__setattr__(self, "source_metadata", FrozenDict(self.source_metadata))
        object.__setattr__(self, "embedding", FrozenList(self.embedding))

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
            learning_brief=None,
            ai_status=AIStatus.PENDING,
            ai_attempt_count=0,
            ai_last_attempt_at=None,
            ai_last_error="",
        )

    def archive(self, now: datetime) -> SavedItem:
        return replace(self, archived=True, archived_at=now, updated_at=now)
