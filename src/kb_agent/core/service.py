from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from kb_agent.core.models import AIStatus, ExtractedContent, Priority, SavedItem, Status
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
            item = self.create_link(
                user_id=user_id,
                url=url,
                note=note,
                priority=priority,
            )
        else:
            self.repository.save(item)

        extracted = await self._extract_for_item(item)
        if extracted is None:
            needs_text = replace(
                item,
                title=item.url,
                status=Status.NEEDS_TEXT,
                ai_status=AIStatus.FAILED,
                updated_at=self.clock.now(),
            )
            self.repository.save(needs_text)
            return needs_text

        return await self._enrich_and_save(item, extracted)

    def create_link(
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
        return item

    def resolve_item_ref(self, *, user_id: str, item_ref: str) -> str:
        item_id = self.repository.resolve_item_ref(user_id, item_ref)
        if item_id is None:
            raise ValueError("Saved item not found")
        return item_id

    async def enrich_saved_item(self, *, user_id: str, item_id: str) -> SavedItem:
        item = self._get_user_item(user_id=user_id, item_id=item_id)
        extracted = await self._extract_for_item(item)
        return await self._enrich_and_save(item, extracted)

    async def refresh_item(self, *, user_id: str, item_ref: str) -> SavedItem:
        item_id = self.resolve_item_ref(user_id=user_id, item_ref=item_ref)
        return await self.enrich_saved_item(user_id=user_id, item_id=item_id)

    async def retry_pending_ai(self, *, limit: int, max_attempts: int) -> list[SavedItem]:
        results: list[SavedItem] = []
        for item in self.repository.list_ai_retry_candidates(
            limit=limit,
            max_attempts=max_attempts,
        ):
            retry_at = self.clock.now()
            updated = replace(
                item,
                ai_last_attempt_at=retry_at,
                updated_at=retry_at,
            )
            self.repository.save(updated)
            enriched = await self.enrich_saved_item(user_id=item.user_id, item_id=item.id)
            persisted = self.repository.get(item.id) or enriched
            if persisted.ai_attempt_count <= item.ai_attempt_count:
                persisted = replace(
                    persisted,
                    ai_attempt_count=item.ai_attempt_count + 1,
                    ai_last_attempt_at=persisted.ai_last_attempt_at or retry_at,
                )
                self.repository.save(persisted)
            results.append(
                persisted,
            )
        return results

    async def _extract_for_item(self, item: SavedItem) -> ExtractedContent | None:
        try:
            extracted = await self.extractor.extract(item.url)
        except Exception:
            extracted = None

        if extracted is not None and not extracted.text.strip():
            extracted = None
        if extracted is None and item.extracted_text.strip():
            extracted = ExtractedContent(
                title=item.title,
                text=item.extracted_text,
                metadata=dict(item.source_metadata),
            )
        if extracted is None:
            extracted = _manual_extracted_content(item)
        return extracted

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
        item_id = self.resolve_item_ref(user_id=user_id, item_ref=item_id)
        item = self._get_user_item(user_id=user_id, item_id=item_id)
        archived = item.archive(self.clock.now())
        self.repository.save(archived)
        return archived

    def add_note(self, *, user_id: str, item_id: str, note: str) -> SavedItem:
        item_id = self.resolve_item_ref(user_id=user_id, item_ref=item_id)
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
        item_id = self.resolve_item_ref(user_id=user_id, item_ref=item_id)
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
                    ai_status=AIStatus.PENDING,
                    ai_attempt_count=0,
                    ai_last_attempt_at=None,
                    ai_last_error="",
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
