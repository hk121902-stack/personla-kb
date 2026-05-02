from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from kb_agent.core.models import ExtractedContent, Priority, SavedItem, Status
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
        item = self._pending_manual_fallback_item(
            user_id=user_id,
            url=url,
            note=note,
            priority=priority,
            now=now,
        )
        if item is None:
            item = SavedItem.new(
                user_id=user_id,
                url=url,
                source_type=detect_source_type(url),
                now=now,
                note=note,
                priority=priority,
            )
        self.repository.save(item)
        try:
            extracted = await self.extractor.extract(url)
        except Exception:
            extracted = _manual_extracted_content(item)
            if extracted is not None:
                return await self._enrich_and_save(item, extracted)
            failed = replace(
                item,
                status=Status.NEEDS_TEXT,
                updated_at=self.clock.now(),
            )
            self.repository.save(failed)
            return failed

        if extracted is None:
            extracted = _manual_extracted_content(item)

        return await self._enrich_and_save(item, extracted)

    async def _enrich_and_save(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> SavedItem:
        try:
            enriched = await self.ai_provider.enrich(item, extracted)
        except Exception:
            extracted_title = item.url
            extracted_text = ""
            source_metadata = {}
            if extracted is not None:
                extracted_title = extracted.title
                extracted_text = extracted.text
                source_metadata = dict(extracted.metadata)

            failed = replace(
                item,
                title=extracted_title,
                extracted_text=extracted_text,
                source_metadata=source_metadata,
                status=Status.FAILED_ENRICHMENT,
                updated_at=self.clock.now(),
            )
            self.repository.save(failed)
            return failed

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

    def _pending_manual_fallback_item(
        self,
        *,
        user_id: str,
        url: str,
        note: str,
        priority: Priority,
        now: datetime,
    ) -> SavedItem | None:
        if not note.strip():
            return None

        for item in self.repository.list_by_user(user_id):
            if item.url == url and item.status == Status.NEEDS_TEXT:
                selected_priority = item.priority
                if priority is not Priority.UNSET:
                    selected_priority = priority
                return replace(
                    item,
                    user_note=note,
                    priority=selected_priority,
                    status=Status.PROCESSING,
                    updated_at=now,
                )

        return None


def _manual_extracted_content(item: SavedItem) -> ExtractedContent | None:
    text = item.user_note.strip()
    if not text:
        return None

    return ExtractedContent(
        title=item.url,
        text=text,
        metadata={"extraction": "manual_note"},
    )
