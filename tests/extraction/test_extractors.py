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

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)
        result = await extractor.extract("https://example.com/rag")

    assert result is not None
    assert result.title == "RAG Notes"
    assert "Hello retrieval" in result.text


@pytest.mark.asyncio
async def test_webpage_extractor_returns_none_when_blocked() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)

        assert await extractor.extract("https://example.com/private") is None


@pytest.mark.asyncio
async def test_webpage_extractor_returns_none_when_request_fails() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network unavailable", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)

        assert await extractor.extract("https://example.com/offline") is None
