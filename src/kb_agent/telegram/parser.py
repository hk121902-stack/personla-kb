from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from kb_agent.core.models import Priority

_URL_RE = re.compile(r"https?://\S+")
_TRAILING_URL_PUNCTUATION = ".,;:!?"
_SAVE_VERB_RE = re.compile(r"^\s*save\b", re.IGNORECASE)
_PRIORITY_PATTERN = r"\bpriority:?\s*(high|medium|low)\b"
_PRIORITY_RE = re.compile(_PRIORITY_PATTERN, re.IGNORECASE)
_NOTE_RE = re.compile(
    rf"\bnote:\s*(?P<note>.*?)(?=\s+{_PRIORITY_PATTERN}|$)",
    re.IGNORECASE,
)
_INCLUDE_ARCHIVED_RE = re.compile(r"\binclude\s+archived\b", re.IGNORECASE)


@dataclass(frozen=True)
class SaveCommand:
    url: str
    note: str
    priority: Priority


@dataclass(frozen=True)
class AskCommand:
    question: str
    include_archived: bool = False


@dataclass(frozen=True)
class DigestCommand:
    kind: Literal["today", "week"]


@dataclass(frozen=True)
class AIStatusCommand:
    pass


@dataclass(frozen=True)
class RefreshCommand:
    item_ref: str


@dataclass(frozen=True)
class ModelCommand:
    provider_model: str


@dataclass(frozen=True)
class ArchiveCommand:
    item_id: str


@dataclass(frozen=True)
class ReviewArchiveCommand:
    pass


@dataclass(frozen=True)
class ShowCommand:
    query: str


@dataclass(frozen=True)
class ParseCommand:
    message: str = ""


def parse_message(
    message: str,
) -> (
    SaveCommand
    | AskCommand
    | DigestCommand
    | AIStatusCommand
    | RefreshCommand
    | ModelCommand
    | ArchiveCommand
    | ReviewArchiveCommand
    | ShowCommand
    | ParseCommand
):
    text = message.strip()
    if not text:
        return ParseCommand(message=message)

    url_match = _URL_RE.search(text)
    if url_match:
        raw_url = url_match.group(0)
        url = _clean_url(raw_url)
        return SaveCommand(
            url=url,
            note=_parse_note(text, raw_url),
            priority=_parse_priority(text),
        )

    lowered = text.casefold()
    if lowered == "digest today" or lowered.startswith("digest today "):
        return DigestCommand(kind="today")
    if lowered == "digest week" or lowered.startswith("digest week "):
        return DigestCommand(kind="week")
    if lowered == "ai status" or lowered.startswith("ai status "):
        return AIStatusCommand()
    if lowered == "refresh" or lowered.startswith("refresh "):
        return RefreshCommand(item_ref=_after_command(text))
    if lowered == "model" or lowered.startswith("model "):
        return ModelCommand(provider_model=_after_command(text))
    if lowered == "review archive" or lowered.startswith("review archive "):
        return ReviewArchiveCommand()
    if lowered == "archive" or lowered.startswith("archive "):
        return ArchiveCommand(item_id=_after_command(text))
    if lowered == "show" or lowered.startswith("show "):
        return ShowCommand(query=_after_command(text))

    return _parse_ask(text)


def _parse_priority(text: str) -> Priority:
    match = _PRIORITY_RE.search(text)
    if match is None:
        return Priority.UNSET
    return Priority(match.group(1).casefold())


def _after_command(text: str) -> str:
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        return ""
    return parts[1].strip()


def _clean_url(url: str) -> str:
    return url.rstrip(_TRAILING_URL_PUNCTUATION)


def _parse_note(text: str, url: str) -> str:
    note_match = _NOTE_RE.search(text)
    if note_match is not None:
        return note_match.group("note").strip()

    without_url = text.replace(url, "", 1)
    without_priority = _PRIORITY_RE.sub("", without_url)
    without_save_verb = _SAVE_VERB_RE.sub("", without_priority, count=1)
    return without_save_verb.strip()


def _parse_ask(text: str) -> AskCommand:
    question = text
    if question.casefold() == "ask":
        question = ""
    elif question.casefold().startswith("ask "):
        question = question[4:].strip()

    include_archived = bool(_INCLUDE_ARCHIVED_RE.search(question))
    if include_archived:
        question = _INCLUDE_ARCHIVED_RE.sub("", question).strip()
        question = re.sub(r"\s+", " ", question)

    return AskCommand(question=question, include_archived=include_archived)
