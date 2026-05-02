import httpx
import pytest

from kb_agent.extraction.extractors import WebpageExtractor


@pytest.mark.asyncio
async def test_webpage_extractor_reads_title_and_text() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="<html><head><title>RAG Notes</title></head>"
            "<body><main>Hello retrieval</main></body></html>",
        )

    extractor = WebpageExtractor(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    result = await extractor.extract("https://example.com/rag")

    assert result is not None
    assert result.title == "RAG Notes"
    assert "Hello retrieval" in result.text


@pytest.mark.asyncio
async def test_webpage_extractor_returns_none_when_blocked() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    extractor = WebpageExtractor(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    assert await extractor.extract("https://example.com/private") is None
