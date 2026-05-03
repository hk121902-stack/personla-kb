from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime

from kb_agent.core.models import ExtractedContent, LearningBrief, SavedItem, Status

_EMBEDDING_SIZE = 32
_MAX_TAGS = 8
_WORD_RE = re.compile(r"[a-z0-9]+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
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
    "for",
    "from",
    "has",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "uses",
    "with",
}


class HeuristicAIProvider:
    async def enrich(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> SavedItem:
        if extracted is None:
            return replace(item, status=Status.NEEDS_TEXT, title=item.url)

        title = extracted.title.strip() or item.url
        text = extracted.text.strip()
        tags = _generate_tags(title, text, item.user_note)
        topic = " ".join(tags[:2]) if tags else item.source_type.value
        summary = _summarize(text) or title
        embedding = _embed(title, text, item.user_note)

        return replace(
            item,
            title=title,
            extracted_text=text,
            tags=tags,
            topic=topic,
            summary=summary,
            embedding=embedding,
            status=Status.READY,
            source_metadata=dict(extracted.metadata),
        )

    async def generate_learning_brief(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> LearningBrief:
        title = item.url
        text = item.user_note
        if extracted is not None:
            title = extracted.title.strip() or item.url
            text = extracted.text.strip() or item.user_note
        tags = _generate_tags(title, text, item.user_note)
        summary = _summarize(text) or title
        return LearningBrief(
            brief_version=1,
            provider="heuristic",
            model="heuristic",
            generated_at=datetime.now(UTC),
            title=title,
            topic=" ".join(tags[:2]) if tags else item.source_type.value,
            tags=tags,
            summary=summary,
            key_takeaways=[summary],
            why_it_matters=item.user_note or "This item was saved for later review.",
            estimated_time_minutes=max(1, min(30, len(text.split()) // 180 + 1)),
            suggested_next_action="Review the source and add a note with the useful details.",
        )

    async def synthesize_answer(self, question: str, matches: list[SavedItem]) -> str:
        question_text = question.strip() or "the question"
        if not matches:
            return f"No saved items match {question_text!r}."

        snippets = []
        for item in matches[:5]:
            title = item.title or item.url
            detail = item.summary or item.extracted_text[:180] or item.user_note or item.url
            snippets.append(f"{title}: {detail}")

        return f"Based on saved items for {question_text!r}: " + " ".join(snippets)

    async def synthesize_extra_context(self, question: str) -> str:
        question_text = question.strip() or "the question"
        return (
            "No external context is available from the local heuristic provider "
            f"for {question_text!r}."
        )


def _generate_tags(*parts: str) -> list[str]:
    counts = Counter(_tokens(" ".join(parts)))
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [word for word, _count in ranked[:_MAX_TAGS]]


def _tokens(text: str) -> list[str]:
    return [
        match.group(0)
        for match in _WORD_RE.finditer(text.lower())
        if match.group(0) not in _STOP_WORDS and len(match.group(0)) > 2
    ]


def _summarize(text: str) -> str:
    if not text:
        return ""

    sentences = _SENTENCE_RE.split(text, maxsplit=1)
    if len(sentences) > 1:
        return sentences[0].strip()

    return text[:180].strip()


def _embed(*parts: str) -> list[float]:
    vector = [0.0] * _EMBEDDING_SIZE
    tokens = _tokens(" ".join(parts))
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode()).digest()
        index = int.from_bytes(digest[:2], "big") % _EMBEDDING_SIZE
        vector[index] += 1.0

    total = float(len(tokens))
    return [value / total for value in vector]
