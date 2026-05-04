from dataclasses import replace
from datetime import UTC, datetime

import pytest

from kb_agent.ai.providers import HeuristicAIProvider
from kb_agent.core.models import SavedItem, SourceType, Status
from kb_agent.core.retrieval import RetrievalService
from kb_agent.storage.sqlite import SQLiteItemRepository


def ready_item(url: str, title: str, text: str, *, archived: bool = False) -> SavedItem:
    item = SavedItem.new(
        user_id="telegram:123",
        url=url,
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )
    return replace(
        item,
        title=title,
        extracted_text=text,
        tags=["retrieval", "rag"],
        topic="retrieval rag",
        summary=text,
        status=Status.READY,
        archived=archived,
    )


def ready_item_with_id(
    item_id: str,
    url: str,
    title: str,
    text: str,
) -> SavedItem:
    return replace(ready_item(url, title, text), id=item_id)


@pytest.mark.asyncio
async def test_retrieval_excludes_archived_by_default(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    active = ready_item(
        "https://example.com/active",
        "RAG Search",
        "semantic retrieval notes",
    )
    archived = ready_item(
        "https://example.com/archived",
        "Old RAG",
        "semantic retrieval archive",
        archived=True,
    )
    repo.save(active)
    repo.save(archived)

    response = await RetrievalService(repo, HeuristicAIProvider()).answer(
        user_id="telegram:123",
        question="What did I save about retrieval?",
    )

    assert "From your knowledge base" in response.text
    assert "RAG Search" in response.text
    assert "Old RAG" not in response.text


@pytest.mark.asyncio
async def test_retrieval_sources_include_item_aliases(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    repo.save(
        ready_item_with_id(
            "7f3a9b8c1234",
            "https://example.com/active",
            "RAG Search",
            "semantic retrieval notes",
        ),
    )

    response = await RetrievalService(repo, HeuristicAIProvider()).answer(
        user_id="telegram:123",
        question="What did I save about retrieval?",
    )

    assert "- kb_7f3a: RAG Search - https://example.com/active" in response.text


@pytest.mark.asyncio
async def test_retrieval_response_carries_structured_answer_fields(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    repo.save(
        ready_item_with_id(
            "7f3a9b8c1234",
            "https://example.com/active",
            "RAG Search",
            "semantic retrieval notes",
        ),
    )

    response = await RetrievalService(repo, HeuristicAIProvider()).answer(
        user_id="telegram:123",
        question="What did I save about retrieval?",
    )

    assert response.question == "What did I save about retrieval?"
    assert response.answer
    assert response.extra_context == ""
    assert response.item_aliases[response.matches[0].id] == "kb_7f3a"
    assert response.matches[0].title == "RAG Search"


@pytest.mark.asyncio
async def test_retrieval_only_adds_extra_context_for_explanation_questions(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    repo.save(ready_item("https://example.com/active", "RAG Search", "semantic retrieval notes"))

    plain = await RetrievalService(repo, HeuristicAIProvider()).answer(
        user_id="telegram:123",
        question="retrieval",
    )
    explanatory = await RetrievalService(repo, HeuristicAIProvider()).answer(
        user_id="telegram:123",
        question="why retrieval matters",
    )

    assert plain.extra_context == ""
    assert explanatory.extra_context


@pytest.mark.asyncio
async def test_retrieval_can_include_archived(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    archived = ready_item(
        "https://example.com/archived",
        "Old RAG",
        "semantic retrieval archive",
        archived=True,
    )
    repo.save(archived)

    response = await RetrievalService(repo, HeuristicAIProvider()).answer(
        user_id="telegram:123",
        question="include archived retrieval",
        include_archived=True,
    )

    assert "Old RAG" in response.text


@pytest.mark.asyncio
async def test_retrieval_reports_weak_matches(tmp_path) -> None:
    repo = SQLiteItemRepository(tmp_path / "kb.sqlite3")
    repo.save(ready_item("https://example.com/cooking", "Cooking", "sourdough starter"))

    response = await RetrievalService(repo, HeuristicAIProvider()).answer(
        user_id="telegram:123",
        question="kubernetes autoscaling",
    )

    assert "I did not find a strong match" in response.text
