from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from kb_agent.ai.briefs import AIProviderError, sync_brief_to_item
from kb_agent.core.models import AIStatus, ExtractedContent, LearningBrief, SavedItem, Status


class BriefProvider(Protocol):
    async def generate_learning_brief(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> LearningBrief: ...


@dataclass(frozen=True)
class ProviderChainEntry:
    provider: str
    model: str

    @classmethod
    def parse(cls, value: str) -> ProviderChainEntry:
        provider, separator, model = value.strip().partition(":")
        if not separator:
            if provider == "heuristic":
                return cls(provider="heuristic", model="heuristic")
            raise ValueError(f"Provider chain entry {value!r} must use provider:model")

        provider = provider.strip()
        model = model.strip()
        if not provider or not model:
            raise ValueError(f"Provider chain entry {value!r} must use provider:model")

        return cls(provider=provider, model=model)

    def key(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass(frozen=True)
class AIStatusSnapshot:
    chain: list[str]
    last_error: str


class AIProviderRouter:
    def __init__(
        self,
        chain: Sequence[ProviderChainEntry],
        *,
        providers: dict[str, BriefProvider],
    ) -> None:
        if not chain:
            raise ValueError("Provider chain must not be empty")

        self._configured_chain = tuple(chain)
        self._current_chain = list(chain)
        self._providers = dict(providers)
        self._last_error = ""

    async def enrich(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> SavedItem:
        attempt_at = item.updated_at
        item = replace(
            item,
            ai_attempt_count=item.ai_attempt_count + 1,
            ai_last_attempt_at=attempt_at,
        )
        last_error = ""
        first_real_provider_error = ""
        real_provider_failed = False

        for entry in self._current_chain:
            provider = self._providers.get(entry.key())
            if provider is None:
                last_error = f"{entry.key()} provider is not configured"
                if entry.provider != "heuristic":
                    real_provider_failed = True
                    first_real_provider_error = first_real_provider_error or last_error
                continue

            try:
                brief = await provider.generate_learning_brief(item, extracted)
            except AIProviderError as error:
                last_error = str(error)
                if entry.provider != "heuristic":
                    real_provider_failed = True
                    first_real_provider_error = first_real_provider_error or last_error
                continue
            except Exception as error:
                last_error = str(error) or error.__class__.__name__
                if entry.provider != "heuristic":
                    real_provider_failed = True
                    first_real_provider_error = first_real_provider_error or last_error
                continue

            diagnostic_error = first_real_provider_error or last_error
            self._last_error = diagnostic_error
            if entry.provider == "heuristic" and real_provider_failed:
                item_with_error = replace(item, ai_last_error=diagnostic_error)
                return sync_brief_to_item(
                    item_with_error,
                    brief,
                    ready=False,
                    now=attempt_at,
                    extracted=extracted,
                )

            return sync_brief_to_item(
                item,
                brief,
                ready=True,
                now=attempt_at,
                extracted=extracted,
            )

        diagnostic_error = first_real_provider_error or last_error
        self._last_error = diagnostic_error
        return replace(
            item,
            ai_status=AIStatus.RETRY_PENDING,
            ai_last_error=diagnostic_error,
            status=Status.FAILED_ENRICHMENT,
            updated_at=attempt_at,
        )

    async def synthesize_answer(self, question: str, matches: list[SavedItem]) -> str:
        provider = self._providers.get("heuristic:heuristic")
        synthesize = getattr(provider, "synthesize_answer", None)
        if callable(synthesize):
            return await synthesize(question, matches)

        return "No AI provider is available to synthesize an answer."

    async def synthesize_extra_context(self, question: str) -> str:
        provider = self._providers.get("heuristic:heuristic")
        synthesize = getattr(provider, "synthesize_extra_context", None)
        if callable(synthesize):
            return await synthesize(question)

        question_text = question.strip() or "the question"
        return f"No extra AI context is available for {question_text!r}."

    def select_model(self, provider_model: str) -> None:
        selected = ProviderChainEntry.parse(provider_model)
        configured_by_key = {entry.key(): entry for entry in self._configured_chain}
        selected_entry = configured_by_key.get(selected.key())
        if selected_entry is None:
            raise ValueError(f"{provider_model} is not in configured provider chain")

        self._current_chain = [
            selected_entry,
            *(entry for entry in self._configured_chain if entry.key() != selected.key()),
        ]

    def status(self) -> AIStatusSnapshot:
        return AIStatusSnapshot(
            chain=[entry.key() for entry in self._current_chain],
            last_error=self._last_error,
        )
