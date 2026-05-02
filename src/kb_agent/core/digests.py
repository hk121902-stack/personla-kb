from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from kb_agent.core.models import Priority, SavedItem, Status
from kb_agent.core.ports import ItemRepository

_DAILY_LIMIT = 3
_WEEKLY_LIMIT = 7
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


class DigestService:
    def __init__(self, repository: ItemRepository) -> None:
        self.repository = repository

    def daily(self, *, user_id: str) -> Digest:
        items = sorted(
            _ready_items(self.repository, user_id),
            key=_daily_sort_key,
        )[:_DAILY_LIMIT]
        lines = ["Daily tiny nudge"]
        lines.extend(_item_line(item) for item in items)
        return Digest(text="\n".join(lines), items=items)

    def weekly(self, *, user_id: str) -> Digest:
        items = _ready_items(self.repository, user_id)[:_WEEKLY_LIMIT]
        lines = ["Weekly synthesis"]
        for topic, topic_items in _group_by_topic(items).items():
            lines.append(f"{topic}:")
            lines.extend(_item_line(item) for item in topic_items)
        return Digest(text="\n".join(lines), items=items)


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


def _group_by_topic(items: list[SavedItem]) -> dict[str, list[SavedItem]]:
    groups: dict[str, list[SavedItem]] = {}
    for item in items:
        topic = item.topic or (item.tags[0] if item.tags else "general")
        groups.setdefault(topic, []).append(item)
    return groups


def _item_line(item: SavedItem) -> str:
    summary = item.summary or item.title or item.url
    return f"- {item.title}: {summary}"
