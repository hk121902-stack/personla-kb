from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from kb_agent.core.models import Priority, SavedItem, Status
from kb_agent.core.ports import ItemRepository

_OLD_LOW_PRIORITY_DAYS = 60
_DUPLICATE_OVERLAP_THRESHOLD = 0.80
_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class ArchiveRecommendation:
    item: SavedItem
    reason: str


class ArchiveReviewService:
    def __init__(self, repository: ItemRepository) -> None:
        self.repository = repository

    def recommend(
        self,
        *,
        user_id: str,
        now: datetime,
    ) -> list[ArchiveRecommendation]:
        items = [
            item
            for item in self.repository.list_by_user(user_id)
            if item.status == Status.READY
        ]
        recommendations: list[ArchiveRecommendation] = []
        recommended_ids: set[str] = set()

        for item in items:
            if _is_old_low_priority(item, now):
                recommendations.append(
                    ArchiveRecommendation(item=item, reason="old_low_priority"),
                )
                recommended_ids.add(item.id)

        for older in items:
            if older.id in recommended_ids:
                continue
            if any(_is_older_duplicate(older, newer) for newer in items):
                recommendations.append(
                    ArchiveRecommendation(item=older, reason="duplicate_overlap"),
                )
                recommended_ids.add(older.id)

        return recommendations


def _is_old_low_priority(item: SavedItem, now: datetime) -> bool:
    return (
        item.priority == Priority.LOW
        and (now - item.created_at).days >= _OLD_LOW_PRIORITY_DAYS
    )


def _is_older_duplicate(older: SavedItem, newer: SavedItem) -> bool:
    if older.id == newer.id or older.created_at >= newer.created_at:
        return False

    older_tokens = _tokens(_duplicate_text(older))
    newer_tokens = _tokens(_duplicate_text(newer))
    if not older_tokens or not newer_tokens:
        return False

    overlap = len(older_tokens & newer_tokens) / len(older_tokens)
    return overlap >= _DUPLICATE_OVERLAP_THRESHOLD


def _duplicate_text(item: SavedItem) -> str:
    return " ".join(
        [
            item.title,
            item.extracted_text,
            item.summary,
            item.topic,
            " ".join(item.tags),
        ],
    )


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))
