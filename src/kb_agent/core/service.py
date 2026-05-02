from __future__ import annotations

from dataclasses import replace
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
        item = self._get_user_item(user_id=user_id, item_id=item_id)
        archived = item.archive(self.clock.now())
        self.repository.save(archived)
        return archived

    def add_note(self, *, user_id: str, item_id: str, note: str) -> SavedItem:
        item = self._get_user_item(user_id=user_id, item_id=item_id)
        updated = replace(item, user_note=note, updated_at=self.clock.now())
        self.repository.save(updated)
        return updated

    def set_priority(
        self,
        *,
        user_id: str,
        item_id: str,
        priority: Priority,
    ) -> SavedItem:
        item = self._get_user_item(user_id=user_id, item_id=item_id)
        updated = replace(item, priority=priority, updated_at=self.clock.now())
        self.repository.save(updated)
        return updated

    def _get_user_item(self, *, user_id: str, item_id: str) -> SavedItem:
        item = self.repository.get(item_id)
        if item is None or item.user_id != user_id:
            raise ValueError("Saved item not found")
        return item
