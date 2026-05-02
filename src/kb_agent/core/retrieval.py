from __future__ import annotations

import re
from dataclasses import dataclass

from kb_agent.core.models import SavedItem, Status
from kb_agent.core.ports import AIProvider, ItemRepository

_WORD_RE = re.compile(r"[a-z0-9]+")
_WEAK_MATCH_THRESHOLD = 0.15
_MAX_MATCHES = 5
_STOP_WORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "did",
    "for",
    "from",
    "has",
    "i",
    "in",
    "include",
    "into",
    "is",
    "it",
    "my",
    "of",
    "on",
    "or",
    "save",
    "saved",
    "that",
    "the",
    "this",
    "to",
    "what",
    "with",
}
_EXPLANATION_WORDS = {"explain", "explanation", "why", "how", "context"}


@dataclass(frozen=True)
class RetrievalResponse:
    text: str
    matches: list[SavedItem]


class RetrievalService:
    def __init__(self, repository: ItemRepository, ai_provider: AIProvider) -> None:
        self.repository = repository
        self.ai_provider = ai_provider

    async def answer(
        self,
        *,
        user_id: str,
        question: str,
        include_archived: bool = False,
    ) -> RetrievalResponse:
        candidates = [
            item
            for item in self.repository.list_by_user(
                user_id,
                include_archived=include_archived,
            )
            if item.status == Status.READY
        ]
        scored = sorted(
            (
                (_score(question, item), item)
                for item in candidates
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        matches = [
            item
            for score, item in scored[:_MAX_MATCHES]
            if score >= _WEAK_MATCH_THRESHOLD
        ]

        if matches:
            answer = await self.ai_provider.synthesize_answer(question, matches)
        else:
            answer = (
                "I did not find a strong match in your saved knowledge base "
                f"for {question.strip()!r}."
            )

        extra_context = ""
        if matches or _asks_for_explanation(question):
            extra_context = await self.ai_provider.synthesize_extra_context(question)

        return RetrievalResponse(
            text=_format_response(answer, matches, extra_context),
            matches=matches,
        )


def _score(question: str, item: SavedItem) -> float:
    question_tokens = set(_tokens(question))
    if not question_tokens:
        return 0.0

    item_tokens = set(
        _tokens(
            " ".join(
                [
                    item.title,
                    " ".join(item.tags),
                    item.topic,
                    item.summary,
                    item.user_note,
                    item.extracted_text,
                ]
            )
        )
    )
    if not item_tokens:
        return 0.0

    return len(question_tokens & item_tokens) / len(question_tokens)


def _tokens(text: str) -> list[str]:
    return [
        match.group(0)
        for match in _WORD_RE.finditer(text.lower())
        if match.group(0) not in _STOP_WORDS and len(match.group(0)) > 2
    ]


def _asks_for_explanation(question: str) -> bool:
    return bool(set(_tokens(question)) & _EXPLANATION_WORDS)


def _format_response(
    answer: str,
    matches: list[SavedItem],
    extra_context: str,
) -> str:
    sources = "\n".join(
        f"- {item.title or item.url}: {item.url}"
        for item in matches
    )
    if not sources:
        sources = "- No strong saved source match."

    if not extra_context:
        extra_context = "No extra context added."

    return (
        "From your knowledge base\n"
        f"{answer}\n\n"
        "Sources\n"
        f"{sources}\n\n"
        "Extra context\n"
        f"{extra_context}"
    )
