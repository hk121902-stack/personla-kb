from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from kb_agent.core.aliases import alias_for_item_id
from kb_agent.core.models import Priority, SavedItem, Status
from kb_agent.core.ports import ItemRepository

_DAILY_LIMIT = 3
_WEEKLY_LIMIT = 5
_PRIORITY_ORDER = {
    Priority.HIGH: 0,
    Priority.MEDIUM: 1,
    Priority.UNSET: 2,
    Priority.LOW: 3,
}


@dataclass(frozen=True)
class Digest:
    text: str
    items: list[SavedItem]
    item_aliases: dict[str, str]
    kind: str


class DigestService:
    def __init__(
        self,
        repository: ItemRepository,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.now = now or (lambda: datetime.now(UTC))

    def daily(self, *, user_id: str) -> Digest:
        items = sorted(
            _ready_items(self.repository, user_id),
            key=_daily_sort_key,
        )[:_DAILY_LIMIT]
        items = self._mark_surfaced(items)
        lines = ["Daily tiny nudge"]
        lines.extend(_item_line(self.repository, user_id, item) for item in items)
        return Digest(
            text="\n".join(lines),
            items=items,
            item_aliases=_item_aliases(self.repository, user_id, items),
            kind="today",
        )

    def weekly(self, *, user_id: str) -> Digest:
        items = sorted(
            _ready_items(self.repository, user_id),
            key=_weekly_sort_key,
        )[:_WEEKLY_LIMIT]
        items = self._mark_surfaced(items)
        lines = ["Weekly synthesis"]
        for topic, topic_items in _group_by_topic(items).items():
            lines.append(f"{topic}:")
            lines.extend(_item_line(self.repository, user_id, item) for item in topic_items)
        return Digest(
            text="\n".join(lines),
            items=items,
            item_aliases=_item_aliases(self.repository, user_id, items),
            kind="week",
        )

    def _mark_surfaced(self, items: list[SavedItem]) -> list[SavedItem]:
        surfaced_at = self.now()
        updated_items = [
            replace(
                item,
                last_surfaced_at=surfaced_at,
                surface_count=item.surface_count + 1,
                updated_at=surfaced_at,
            )
            for item in items
        ]
        for item in updated_items:
            self.repository.save(item)
        return updated_items


def _ready_items(repository: ItemRepository, user_id: str) -> list[SavedItem]:
    return [
        item
        for item in repository.list_by_user(user_id)
        if item.status == Status.READY
    ]


def _daily_sort_key(item: SavedItem) -> tuple[int, datetime, float]:
    surfaced_at = item.last_surfaced_at or datetime.min.replace(
        tzinfo=item.created_at.tzinfo,
    )
    return (
        _PRIORITY_ORDER[item.priority],
        surfaced_at,
        -item.created_at.timestamp(),
    )


def _weekly_sort_key(item: SavedItem) -> tuple[datetime, int, int, datetime, str]:
    surfaced_at = item.last_surfaced_at or datetime.min.replace(
        tzinfo=item.created_at.tzinfo,
    )
    return (
        surfaced_at,
        item.surface_count,
        _PRIORITY_ORDER[item.priority],
        item.created_at,
        item.id,
    )


def _group_by_topic(items: list[SavedItem]) -> dict[str, list[SavedItem]]:
    groups: dict[str, list[SavedItem]] = {}
    for item in items:
        topic = item.topic or (item.tags[0] if item.tags else "general")
        groups.setdefault(topic, []).append(item)
    return groups


def _item_line(repository: ItemRepository, user_id: str, item: SavedItem) -> str:
    summary = item.summary or item.title or item.url
    return f"- {_item_alias(repository, user_id, item)}: {item.title} - {summary}"


def _item_aliases(
    repository: ItemRepository,
    user_id: str,
    items: list[SavedItem],
) -> dict[str, str]:
    return {item.id: _item_alias(repository, user_id, item) for item in items}


def _item_alias(repository: ItemRepository, user_id: str, item: SavedItem) -> str:
    alias_for_item = getattr(repository, "item_alias", None)
    if callable(alias_for_item):
        return alias_for_item(user_id, item.id)
    try:
        return alias_for_item_id(item.id)
    except ValueError:
        return item.id
