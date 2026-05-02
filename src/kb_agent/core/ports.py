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
