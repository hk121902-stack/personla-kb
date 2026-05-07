import json
from datetime import UTC, datetime

import httpx
import pytest

from kb_agent.ai.briefs import AIErrorCategory, AIProviderError
from kb_agent.ai.ollama import OllamaBriefProvider
from kb_agent.core.models import SavedItem, SourceType


def _item() -> SavedItem:
    return SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/ollama",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_ollama_provider_uses_json_mode_and_non_streaming_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://localhost:11434/api/generate"
        body = json.loads(request.content.decode())
        assert body["model"] == "qwen3:8b"
        assert body["stream"] is False
        assert body["format"] == "json"
        return httpx.Response(
            200,
            json={
                "response": (
                    '{"title":"Ollama Brief","topic":"local ai","tags":["ollama"],'
                    '"summary":"Summary","key_takeaways":["Takeaway"],'
                    '"why_it_matters":"Private","estimated_time_minutes":8,'
                    '"suggested_next_action":"Run locally"}'
                )
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        brief = await OllamaBriefProvider(
            http_client=client,
            base_url="http://localhost:11434",
            model="qwen3:8b",
        ).generate_learning_brief(_item(), None)

    assert brief.provider == "ollama"
    assert brief.model == "qwen3:8b"
    assert brief.title == "Ollama Brief"


@pytest.mark.asyncio
async def test_ollama_provider_classifies_unavailable_local_server() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connect failed", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaBriefProvider(
            http_client=client,
            base_url="http://localhost:11434",
            model="qwen3:8b",
        )

        with pytest.raises(AIProviderError) as error:
            await provider.generate_learning_brief(_item(), None)

    assert error.value.category is AIErrorCategory.LOCAL_PROVIDER_UNAVAILABLE
