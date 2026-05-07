import json
from datetime import UTC, datetime

import httpx
import pytest

from kb_agent.ai.briefs import AIErrorCategory, AIProviderError
from kb_agent.ai.gemini import GeminiBriefProvider
from kb_agent.core.models import ExtractedContent, SavedItem, SourceType


def _item() -> SavedItem:
    return SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/gemini",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        note="use for learning",
    )


@pytest.mark.asyncio
async def test_gemini_provider_parses_structured_text_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "gemini-2.5-flash-lite:generateContent" in str(request.url)
        assert request.headers["x-goog-api-key"] == "key"
        body = json.loads(request.content.decode())
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert "responseJsonSchema" in body["generationConfig"]
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"title":"Gemini Brief","topic":"ai","tags":["gemini"],'
                                        '"summary":"Summary","key_takeaways":["Takeaway"],'
                                        '"why_it_matters":"Useful","estimated_time_minutes":10,'
                                        '"suggested_next_action":"Try it"}'
                                    )
                                }
                            ]
                        }
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        brief = await GeminiBriefProvider(
            http_client=client,
            api_key="key",
            model="gemini-2.5-flash-lite",
        ).generate_learning_brief(_item(), ExtractedContent(title="T", text="Body", metadata={}))

    assert brief.provider == "gemini"
    assert brief.model == "gemini-2.5-flash-lite"
    assert brief.title == "Gemini Brief"


@pytest.mark.asyncio
async def test_gemini_provider_classifies_rate_limit() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(429, json={"error": {"message": "quota"}}),
        ),
    ) as client:
        provider = GeminiBriefProvider(
            http_client=client,
            api_key="key",
            model="gemini-2.5-flash-lite",
        )

        with pytest.raises(AIProviderError) as error:
            await provider.generate_learning_brief(_item(), None)

    assert error.value.category is AIErrorCategory.RATE_LIMIT


@pytest.mark.asyncio
async def test_gemini_provider_requires_api_key() -> None:
    async with httpx.AsyncClient() as client:
        provider = GeminiBriefProvider(
            http_client=client,
            api_key="",
            model="gemini-2.5-flash-lite",
        )

        with pytest.raises(AIProviderError) as error:
            await provider.generate_learning_brief(_item(), None)

    assert error.value.category is AIErrorCategory.MISSING_API_KEY
