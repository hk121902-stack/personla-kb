from __future__ import annotations

from datetime import datetime
from typing import Protocol

from kb_agent.core.models import ExtractedContent, SavedItem


class Clock(Protocol):
    def now(self) -> datetime: ...


class ItemRepository(Protocol):
    def save(self, item: SavedItem) -> SavedItem: ...
    def get(self, item_id: str) -> SavedItem | None: ...
    def list_by_user(
        self,
        user_id: str,
        *,
        include_archived: bool = False,
    ) -> list[SavedItem]: ...
    def resolve_item_ref(self, user_id: str, item_ref: str) -> str | None: ...
    def list_ai_retry_candidates(
        self,
        *,
        limit: int,
        max_attempts: int,
    ) -> list[SavedItem]: ...
    def count_ai_retry_pending(self) -> int: ...
    def last_ai_error(self) -> str: ...


class Extractor(Protocol):
    async def extract(self, url: str) -> ExtractedContent | None: ...


class AIProvider(Protocol):
    async def enrich(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> SavedItem: ...
    async def synthesize_answer(self, question: str, matches: list[SavedItem]) -> str: ...
    async def synthesize_extra_context(self, question: str) -> str: ...
