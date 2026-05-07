import socket
from urllib.parse import parse_qs

import httpx
import pytest

from kb_agent.extraction.extractors import MAX_WEBPAGE_BODY_BYTES, WebpageExtractor


@pytest.fixture(autouse=True)
def resolve_hostnames_to_public_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(*args: object, **kwargs: object) -> list[tuple[object, ...]]:
        return [(None, None, None, None, ("93.184.216.34", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


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
async def test_webpage_extractor_uses_youtube_oembed_metadata_for_short_links() -> None:
    seen_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(
            200,
            json={
                "title": "Graphify + Claude Code: The Solution For Big Repos",
                "author_name": "Software Engineer Meets AI",
                "provider_name": "YouTube",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)
        result = await extractor.extract("https://youtu.be/rgYnZqi2GmA?si=test")

    assert result is not None
    assert seen_request is not None
    assert seen_request.headers["host"] == "www.youtube.com"
    assert seen_request.url.path == "/oembed"
    assert parse_qs(seen_request.url.query.decode())["url"] == [
        "https://youtu.be/rgYnZqi2GmA?si=test",
    ]
    assert result.title == "Graphify + Claude Code: The Solution For Big Repos"
    assert "Software Engineer Meets AI" in result.text
    assert result.metadata["provider_name"] == "YouTube"


@pytest.mark.asyncio
async def test_webpage_extractor_uses_x_oembed_metadata_for_status_links() -> None:
    seen_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(
            200,
            json={
                "author_name": "Avid",
                "provider_name": "Twitter",
                "html": (
                    '<blockquote class="twitter-tweet">'
                    '<p lang="en" dir="ltr">Eric Schmidt says agentic AI companies '
                    "are a 2026 opportunity.</p>&mdash; Avid (@Av1dlive)"
                    "</blockquote>"
                ),
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)
        result = await extractor.extract("https://x.com/av1dlive/status/2050514348511257026")

    assert result is not None
    assert seen_request is not None
    assert seen_request.headers["host"] == "publish.twitter.com"
    assert seen_request.url.path == "/oembed"
    assert parse_qs(seen_request.url.query.decode())["url"] == [
        "https://x.com/av1dlive/status/2050514348511257026",
    ]
    assert result.title == "Avid on X"
    assert "agentic AI companies are a 2026 opportunity" in result.text
    assert result.metadata["provider_name"] == "Twitter"
    assert result.metadata["author_name"] == "Avid"


@pytest.mark.asyncio
async def test_webpage_extractor_uses_instagram_opengraph_metadata_for_reel_links() -> None:
    seen_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(
            200,
            text=(
                "<html><head>"
                '<meta property="og:title" content="Build agent memory - Instagram Reel">'
                '<meta property="og:description" content="A short reel about saving learning links.">'
                '<meta property="og:image" content="https://cdn.example.com/reel.jpg">'
                '<meta property="og:video" content="https://cdn.example.com/reel.mp4">'
                "</head><body></body></html>"
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)
        result = await extractor.extract("https://www.instagram.com/reel/DXkCDvJoYa8/")

    assert result is not None
    assert seen_request is not None
    assert seen_request.headers["host"] == "www.instagram.com"
    assert result.title == "Build agent memory - Instagram Reel"
    assert "Caption: A short reel about saving learning links." in result.text
    assert "URL: https://www.instagram.com/reel/DXkCDvJoYa8/" in result.text
    assert result.metadata["provider_name"] == "Instagram"
    assert result.metadata["instagram_kind"] == "reel"
    assert result.metadata["image_url"] == "https://cdn.example.com/reel.jpg"
    assert result.metadata["video_url"] == "https://cdn.example.com/reel.mp4"


@pytest.mark.asyncio
async def test_webpage_extractor_returns_instagram_fallback_when_metadata_is_blocked() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)
        result = await extractor.extract("https://www.instagram.com/reel/DXkCDvJoYa8/")

    assert result is not None
    assert result.title == "Instagram Reel"
    assert "No public caption was available" in result.text
    assert result.metadata == {
        "provider_name": "Instagram",
        "instagram_kind": "reel",
        "extraction": "instagram_fallback",
    }


@pytest.mark.asyncio
async def test_webpage_extractor_returns_instagram_fallback_when_metadata_is_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><head><title>Instagram</title></head></html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)
        result = await extractor.extract("https://instagram.com/p/ABC123/")

    assert result is not None
    assert result.title == "Instagram Post"
    assert result.metadata["instagram_kind"] == "post"
    assert result.metadata["extraction"] == "instagram_fallback"


@pytest.mark.asyncio
async def test_webpage_extractor_returns_instagram_fallback_when_dns_resolves_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_getaddrinfo(*args: object, **kwargs: object) -> list[tuple[object, ...]]:
        return [(None, None, None, None, ("10.0.0.1", 443))]

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, text="<html><body>unsafe</body></html>")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)
        result = await extractor.extract("https://www.instagram.com/reel/DXkCDvJoYa8/")

    assert called is False
    assert result is not None
    assert result.title == "Instagram Reel"
    assert result.metadata == {
        "provider_name": "Instagram",
        "instagram_kind": "reel",
        "extraction": "instagram_fallback",
    }


@pytest.mark.asyncio
async def test_webpage_extractor_returns_instagram_fallback_when_request_fails() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network unavailable", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)
        result = await extractor.extract("https://www.instagram.com/reel/DXkCDvJoYa8/")

    assert result is not None
    assert result.title == "Instagram Reel"
    assert result.metadata["instagram_kind"] == "reel"
    assert result.metadata["extraction"] == "instagram_fallback"


@pytest.mark.asyncio
async def test_webpage_extractor_returns_instagram_fallback_for_oversized_response_body() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * (MAX_WEBPAGE_BODY_BYTES + 1))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)
        result = await extractor.extract("https://www.instagram.com/reel/DXkCDvJoYa8/")

    assert result is not None
    assert result.title == "Instagram Reel"
    assert result.metadata["instagram_kind"] == "reel"
    assert result.metadata["extraction"] == "instagram_fallback"


@pytest.mark.asyncio
async def test_webpage_extractor_returns_generic_instagram_fallback_for_profile_paths() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)
        result = await extractor.extract("https://www.instagram.com/someuser/")

    assert result is not None
    assert result.title == "Instagram"
    assert result.metadata["instagram_kind"] == "instagram"
    assert result.metadata["extraction"] == "instagram_fallback"


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
        "http://100.64.0.1/admin",
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


@pytest.mark.asyncio
async def test_webpage_extractor_rejects_hostname_resolving_to_private_ip_before_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_getaddrinfo(*args: object, **kwargs: object) -> list[tuple[object, ...]]:
        return [(None, None, None, None, ("10.0.0.1", 443))]

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, text="<html><body>unsafe</body></html>")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)

        assert await extractor.extract("https://attacker.example/admin") is None

    assert called is False


@pytest.mark.asyncio
async def test_webpage_extractor_returns_none_when_dns_resolution_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_getaddrinfo(*args: object, **kwargs: object) -> list[tuple[object, ...]]:
        raise socket.gaierror("dns unavailable")

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, text="<html><body>unsafe</body></html>")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)

        assert await extractor.extract("https://example.com/offline") is None

    assert called is False


@pytest.mark.asyncio
async def test_webpage_extractor_allows_hostname_resolving_to_public_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_getaddrinfo(*args: object, **kwargs: object) -> list[tuple[object, ...]]:
        return [(None, None, None, None, ("93.184.216.34", 443))]

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, text="<html><body>public page</body></html>")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)
        result = await extractor.extract("https://example.com/page")

    assert called is True
    assert result is not None
    assert "public page" in result.text


@pytest.mark.asyncio
async def test_webpage_extractor_fetches_resolved_ip_with_original_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_request: httpx.Request | None = None

    def fake_getaddrinfo(*args: object, **kwargs: object) -> list[tuple[object, ...]]:
        return [(None, None, None, None, ("93.184.216.34", 443))]

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(200, text="<html><body>pinned</body></html>")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)
        result = await extractor.extract("https://example.com:8443/page?q=1")

    assert result is not None
    assert seen_request is not None
    assert seen_request.url.host == "93.184.216.34"
    assert seen_request.url.port == 8443
    assert seen_request.url.path == "/page"
    assert seen_request.url.query == b"q=1"
    assert seen_request.headers["host"] == "example.com:8443"
    assert seen_request.extensions["sni_hostname"] == "example.com"


@pytest.mark.asyncio
async def test_webpage_extractor_aborts_streaming_body_over_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks_read = 0

    def fake_getaddrinfo(*args: object, **kwargs: object) -> list[tuple[object, ...]]:
        return [(None, None, None, None, ("93.184.216.34", 443))]

    class StreamingBody(httpx.AsyncByteStream):
        async def __aiter__(self) -> object:
            nonlocal chunks_read
            chunks_read += 1
            yield b"x" * MAX_WEBPAGE_BODY_BYTES
            chunks_read += 1
            yield b"y"
            chunks_read += 1
            yield b"z"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=StreamingBody())

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = WebpageExtractor(client=client)

        assert await extractor.extract("https://example.com/large") is None

    assert chunks_read == 2
