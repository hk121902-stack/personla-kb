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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "http://localhost/admin",
        "http://localhost./admin",
        "http://127.0.0.1/admin",
        "http://[::1]/admin",
        "http://10.0.0.1/admin",
        "http://172.16.0.1/admin",
        "http://169.254.1.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://224.0.0.1/admin",
        "http://0.0.0.0/admin",
        "http://240.0.0.1/admin",
    ],
)
async def test_webpage_extractor_rejects_unsafe_literal_hosts_before_request(url: str) -> None:
    called = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, text="<html><body>unsafe</body></html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)

        assert await extractor.extract(url) is None

    assert called is False


@pytest.mark.asyncio
async def test_webpage_extractor_returns_none_for_oversized_response_body() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * (1024 * 1024 + 1))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)

        assert await extractor.extract("https://example.com/large") is None
