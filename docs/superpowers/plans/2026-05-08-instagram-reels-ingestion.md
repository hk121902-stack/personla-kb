# Instagram Reels Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Save Instagram Reels as first-class knowledge items with public metadata extraction and a reliable compact fallback.

**Architecture:** Extend the existing link ingestion pipeline rather than adding a new subsystem. Add an Instagram source type, teach the URL detector and web extractor about Instagram/Reel URLs, and add source fallback tags in the AI sync layer so compact Telegram cards stay useful even when Instagram exposes little public metadata.

**Tech Stack:** Python 3.12, pytest, ruff, httpx MockTransport, BeautifulSoup, existing `kb_agent` service/extraction/AI/Telegram modules.

---

## Scope Check

The spec is one bounded feature: Instagram/Reels ingestion. It touches source classification, public metadata extraction, fallback enrichment tags, and tests. It does not include authentication, downloading, transcription, or Meta Graph/oEmbed integration.

## File Structure

- `src/kb_agent/core/models.py`
  - Add `SourceType.INSTAGRAM`.
- `src/kb_agent/extraction/url_parser.py`
  - Detect real Instagram hosts as Instagram and preserve spoof-domain protection.
- `src/kb_agent/extraction/extractors.py`
  - Add Instagram-aware metadata extraction before generic HTML extraction.
  - Return minimal fallback content for Instagram URLs when metadata is blocked or empty.
- `src/kb_agent/ai/briefs.py`
  - Add a small source-tag fallback helper used by routed AI providers.
- `src/kb_agent/ai/providers.py`
  - Reuse the source-tag fallback helper for heuristic enrichment and heuristic learning briefs.
- `tests/extraction/test_url_parser.py`
  - Cover Instagram source detection and spoofing.
- `tests/extraction/test_extractors.py`
  - Cover OpenGraph extraction and fallback behavior.
- `tests/ai/test_briefs.py`
  - Cover routed provider tag fallback for Instagram Reels.
- `tests/ai/test_heuristic_provider.py`
  - Cover heuristic provider tag fallback for Instagram Reels.

Do not modify `.env`; it is an untracked local runtime file.

---

### Task 1: Source Type And URL Detection

**Files:**
- Modify: `src/kb_agent/core/models.py`
- Modify: `src/kb_agent/extraction/url_parser.py`
- Test: `tests/extraction/test_url_parser.py`

- [ ] **Step 1: Write failing source detection tests**

In `tests/extraction/test_url_parser.py`, extend `test_detects_primary_source_types` with Instagram Reel and post assertions:

```python
def test_detects_primary_source_types() -> None:
    assert detect_source_type("https://x.com/user/status/1") is SourceType.X
    assert detect_source_type("https://twitter.com/user/status/1") is SourceType.X
    assert detect_source_type("https://youtube.com/watch?v=abc") is SourceType.YOUTUBE
    assert detect_source_type("https://youtu.be/abc") is SourceType.YOUTUBE
    assert detect_source_type("https://linkedin.com/posts/demo") is SourceType.LINKEDIN
    assert (
        detect_source_type("https://www.instagram.com/reel/DXkCDvJoYa8/")
        is SourceType.INSTAGRAM
    )
    assert detect_source_type("https://instagram.com/p/ABC123/") is SourceType.INSTAGRAM
    assert detect_source_type("https://example.com/article") is SourceType.WEB
```

Extend `test_detects_source_types_from_common_subdomains`:

```python
def test_detects_source_types_from_common_subdomains() -> None:
    assert detect_source_type("https://m.youtube.com/watch?v=abc") is SourceType.YOUTUBE
    assert detect_source_type("https://www.linkedin.com/posts/demo") is SourceType.LINKEDIN
    assert detect_source_type("https://www.instagram.com/reel/DXkCDvJoYa8/") is SourceType.INSTAGRAM
```

Extend `test_detect_source_type_avoids_spoofed_domains`:

```python
def test_detect_source_type_avoids_spoofed_domains() -> None:
    assert detect_source_type("https://youtube.com.example.com/watch?v=abc") is SourceType.WEB
    assert detect_source_type("https://instagram.com.example.com/reel/abc") is SourceType.WEB
```

- [ ] **Step 2: Run URL parser tests to verify failure**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/extraction/test_url_parser.py -q
```

Expected: FAIL with `AttributeError: INSTAGRAM` because the enum value does not exist yet.

- [ ] **Step 3: Add Instagram source detection**

In `src/kb_agent/core/models.py`, update `SourceType`:

```python
class SourceType(StrEnum):
    X = "x"
    YOUTUBE = "youtube"
    LINKEDIN = "linkedin"
    INSTAGRAM = "instagram"
    WEB = "web"
```

In `src/kb_agent/extraction/url_parser.py`, add Instagram detection before the generic web fallback:

```python
def detect_source_type(url: str) -> SourceType:
    hostname = (urlparse(url).hostname or "").removeprefix("www.").lower()

    if _host_matches(hostname, "x.com") or _host_matches(hostname, "twitter.com"):
        return SourceType.X
    if _host_matches(hostname, "youtube.com") or _host_matches(hostname, "youtu.be"):
        return SourceType.YOUTUBE
    if _host_matches(hostname, "linkedin.com"):
        return SourceType.LINKEDIN
    if _host_matches(hostname, "instagram.com"):
        return SourceType.INSTAGRAM
    return SourceType.WEB
```

- [ ] **Step 4: Run URL parser tests to verify pass**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/extraction/test_url_parser.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit source detection**

Run:

```bash
git add src/kb_agent/core/models.py src/kb_agent/extraction/url_parser.py tests/extraction/test_url_parser.py
git commit -m "feat: detect instagram source links"
```

---

### Task 2: Instagram Metadata Extraction And Fallback

**Files:**
- Modify: `src/kb_agent/extraction/extractors.py`
- Test: `tests/extraction/test_extractors.py`

- [ ] **Step 1: Write failing Instagram extractor tests**

In `tests/extraction/test_extractors.py`, add these tests after the X oEmbed test:

```python
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
```

Add the blocked-page fallback test:

```python
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
```

Add the empty-public-page fallback test:

```python
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
```

- [ ] **Step 2: Run Instagram extractor tests to verify failure**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/extraction/test_extractors.py::test_webpage_extractor_uses_instagram_opengraph_metadata_for_reel_links tests/extraction/test_extractors.py::test_webpage_extractor_returns_instagram_fallback_when_metadata_is_blocked tests/extraction/test_extractors.py::test_webpage_extractor_returns_instagram_fallback_when_metadata_is_empty -q
```

Expected: FAIL because the extractor still falls through to generic web extraction or returns `None` for blocked Instagram pages.

- [ ] **Step 3: Add Instagram extraction before generic web extraction**

In `src/kb_agent/extraction/extractors.py`, call the Instagram extractor after YouTube extraction and before the generic fetch:

```python
    async def extract(self, url: str) -> ExtractedContent | None:
        x_metadata = await self._extract_x_metadata(url)
        if x_metadata is not None:
            return x_metadata

        youtube_metadata = await self._extract_youtube_metadata(url)
        if youtube_metadata is not None:
            return youtube_metadata

        instagram_metadata = await self._extract_instagram_metadata(url)
        if instagram_metadata is not None:
            return instagram_metadata

        target = _safe_fetch_target(url)
```

Add this method inside `WebpageExtractor`, after `_extract_x_metadata`:

```python
    async def _extract_instagram_metadata(self, url: str) -> ExtractedContent | None:
        if not _is_instagram_url(url):
            return None

        kind = _instagram_kind(url)
        fallback = _instagram_fallback_content(url, kind)
        target = _safe_fetch_target(url)
        if target is None:
            return fallback

        try:
            async with self.client.stream(
                "GET",
                target.url,
                headers=target.headers,
                extensions=target.extensions,
                follow_redirects=False,
            ) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    return fallback

                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_WEBPAGE_BODY_BYTES:
                        return fallback
        except httpx.HTTPError:
            return fallback

        soup = BeautifulSoup(bytes(body), "html.parser")
        title = _clean_instagram_title(
            _first_meta_content(soup, "og:title", "twitter:title")
            or (soup.title.get_text(strip=True) if soup.title else ""),
        )
        description = _clean_instagram_description(
            _first_meta_content(soup, "og:description", "description", "twitter:description"),
        )

        if not title and not description:
            return fallback

        display_kind = _instagram_display_kind(kind)
        resolved_title = title or display_kind
        text_parts = [f"{display_kind}: {resolved_title}"]
        if description:
            text_parts.append(f"Caption: {description}")
        text_parts.append(f"URL: {url}")

        metadata = {
            "provider_name": "Instagram",
            "instagram_kind": kind,
            "status_code": str(response.status_code),
        }
        image_url = _first_meta_content(soup, "og:image", "twitter:image")
        video_url = _first_meta_content(soup, "og:video", "og:video:url", "twitter:player")
        if image_url:
            metadata["image_url"] = image_url
        if video_url:
            metadata["video_url"] = video_url

        return ExtractedContent(
            title=resolved_title,
            text="\n".join(text_parts),
            metadata=metadata,
        )
```

- [ ] **Step 4: Add Instagram helper functions**

In `src/kb_agent/extraction/extractors.py`, add these helpers near `_is_x_url`:

```python
def _is_instagram_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").removeprefix("www.").lower()
    return hostname == "instagram.com" or hostname.endswith(".instagram.com")


def _instagram_kind(url: str) -> str:
    path = urlparse(url).path.lower()
    if path.startswith("/reel/"):
        return "reel"
    if path.startswith("/p/"):
        return "post"
    return "instagram"


def _instagram_display_kind(kind: str) -> str:
    if kind == "reel":
        return "Instagram Reel"
    if kind == "post":
        return "Instagram Post"
    return "Instagram"


def _instagram_fallback_content(url: str, kind: str) -> ExtractedContent:
    title = _instagram_display_kind(kind)
    return ExtractedContent(
        title=title,
        text=f"{title} saved from URL. No public caption was available. URL: {url}",
        metadata={
            "provider_name": "Instagram",
            "instagram_kind": kind,
            "extraction": "instagram_fallback",
        },
    )


def _first_meta_content(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name})
        if tag is None:
            tag = soup.find("meta", attrs={"name": name})
        if tag is None:
            continue
        content = tag.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def _clean_instagram_title(value: str) -> str:
    cleaned = " ".join(value.split())
    if " • Instagram" in cleaned:
        cleaned = cleaned.split(" • Instagram", 1)[0].strip()
    if cleaned.lower() in {"", "instagram", "instagram reel", "instagram post"}:
        return ""
    return cleaned


def _clean_instagram_description(value: str) -> str:
    cleaned = " ".join(value.split())
    if cleaned.lower() in {"", "instagram", "photos and videos"}:
        return ""
    return cleaned
```

- [ ] **Step 5: Run extractor tests to verify pass**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/extraction/test_extractors.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Instagram extraction**

Run:

```bash
git add src/kb_agent/extraction/extractors.py tests/extraction/test_extractors.py
git commit -m "feat: extract instagram reel metadata"
```

---

### Task 3: Instagram Fallback Tags In AI Output

**Files:**
- Modify: `src/kb_agent/ai/briefs.py`
- Modify: `src/kb_agent/ai/providers.py`
- Test: `tests/ai/test_briefs.py`
- Test: `tests/ai/test_heuristic_provider.py`

- [ ] **Step 1: Write failing routed AI tag fallback test**

In `tests/ai/test_briefs.py`, add this test after `test_sync_brief_to_item_sets_search_fields_and_ai_status`:

```python
def test_sync_brief_to_item_adds_instagram_reel_fallback_tags() -> None:
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://www.instagram.com/reel/DXkCDvJoYa8/",
        source_type=SourceType.INSTAGRAM,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )
    brief = LearningBrief(
        brief_version=1,
        provider="gemini",
        model="gemini-2.5-flash-lite",
        generated_at=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
        title="Instagram Reel",
        topic="ai",
        tags=["ai"],
        summary="Saved Instagram Reel.",
        key_takeaways=["Review the Reel."],
        why_it_matters="It was saved for later learning.",
        estimated_time_minutes=5,
        suggested_next_action="Review the source.",
    )

    synced = sync_brief_to_item(
        item,
        brief,
        ready=True,
        now=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
    )

    assert synced.learning_brief is not None
    assert synced.learning_brief.tags == ["ai", "instagram", "reel"]
    assert synced.tags == ["ai", "instagram", "reel"]
```

- [ ] **Step 2: Write failing heuristic provider tag fallback test**

In `tests/ai/test_heuristic_provider.py`, add this test after `test_heuristic_provider_enriches_from_extracted_content`:

```python
@pytest.mark.asyncio
async def test_heuristic_provider_adds_instagram_reel_fallback_tags() -> None:
    item = SavedItem.new(
        user_id="telegram:123",
        url="https://www.instagram.com/reel/DXkCDvJoYa8/",
        source_type=SourceType.INSTAGRAM,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )
    extracted = ExtractedContent(
        title="Instagram Reel",
        text="Saved Instagram Reel. No public caption was available.",
        metadata={"provider_name": "Instagram", "instagram_kind": "reel"},
    )

    enriched = await HeuristicAIProvider().enrich(item, extracted)
    brief = await HeuristicAIProvider().generate_learning_brief(item, extracted)

    assert "instagram" in enriched.tags
    assert "reel" in enriched.tags
    assert "instagram" in brief.tags
    assert "reel" in brief.tags
```

- [ ] **Step 3: Run AI fallback tests to verify failure**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/ai/test_briefs.py::test_sync_brief_to_item_adds_instagram_reel_fallback_tags tests/ai/test_heuristic_provider.py::test_heuristic_provider_adds_instagram_reel_fallback_tags -q
```

Expected: FAIL because fallback tags are not applied centrally yet.

- [ ] **Step 4: Add a shared source fallback tag helper**

In `src/kb_agent/ai/briefs.py`, update imports:

```python
from collections.abc import Iterable, Mapping
from urllib.parse import urlparse
```

Add `SourceType` to the core model imports:

```python
    SourceType,
```

Add this helper after `build_enrichment_prompt`:

```python
def apply_source_fallback_tags(item: SavedItem, tags: Iterable[str]) -> list[str]:
    selected = list(dict.fromkeys(tag.strip().lower() for tag in tags if tag.strip()))
    if item.source_type is SourceType.INSTAGRAM:
        defaults = ["instagram"]
        if urlparse(item.url).path.lower().startswith("/reel/"):
            defaults.append("reel")
        for tag in defaults:
            if tag not in selected:
                selected.append(tag)
    return selected
```

In `sync_brief_to_item`, apply fallback tags before copying brief fields to the item:

```python
def sync_brief_to_item(
    item: SavedItem,
    brief: LearningBrief,
    *,
    ready: bool,
    now: datetime,
    extracted: ExtractedContent | None = None,
) -> SavedItem:
    brief = replace(brief, tags=apply_source_fallback_tags(item, brief.tags))
    extracted_text = item.extracted_text
    source_metadata = dict(item.source_metadata)
```

- [ ] **Step 5: Use fallback tags in the heuristic provider**

In `src/kb_agent/ai/providers.py`, update the import:

```python
from kb_agent.ai.briefs import apply_source_fallback_tags
```

In `HeuristicAIProvider.enrich`, wrap generated tags:

```python
        tags = apply_source_fallback_tags(item, _generate_tags(title, text, item.user_note))
```

In `HeuristicAIProvider.generate_learning_brief`, wrap generated tags:

```python
        tags = apply_source_fallback_tags(item, _generate_tags(title, text, item.user_note))
```

- [ ] **Step 6: Run AI fallback tests to verify pass**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/ai/test_briefs.py tests/ai/test_heuristic_provider.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit AI fallback tags**

Run:

```bash
git add src/kb_agent/ai/briefs.py src/kb_agent/ai/providers.py tests/ai/test_briefs.py tests/ai/test_heuristic_provider.py
git commit -m "feat: add instagram fallback tags"
```

---

### Task 4: Final Verification And Manual Smoke Test

**Files:**
- No new files.
- Verify: full test suite and linting.

- [ ] **Step 1: Run focused feature tests**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest tests/extraction/test_url_parser.py tests/extraction/test_extractors.py tests/ai/test_briefs.py tests/ai/test_heuristic_provider.py tests/telegram/test_formatter.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full pytest suite**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -m pytest -q
```

Expected: PASS.

- [ ] **Step 3: Run ruff**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/ruff check .
```

Expected: PASS with `All checks passed!`.

- [ ] **Step 4: Smoke test an Instagram Reel save through the service**

Run:

```bash
/private/tmp/personal-kb-agent-venv/bin/python -c "import asyncio, sys; sys.path.insert(0, 'src'); exec(\"\"\"from kb_agent.ai.providers import HeuristicAIProvider\nfrom kb_agent.core.models import ExtractedContent, SourceType\nfrom kb_agent.core.service import KnowledgeService, SystemClock\nfrom kb_agent.extraction.extractors import StaticExtractor\nfrom kb_agent.storage.sqlite import SQLiteItemRepository\n\nasync def main():\n    repo = SQLiteItemRepository('/tmp/personal-kb-instagram-smoke.sqlite3')\n    extracted = ExtractedContent(\n        title='Instagram Reel',\n        text='Instagram Reel saved from URL. No public caption was available. URL: https://www.instagram.com/reel/DXkCDvJoYa8/',\n        metadata={'provider_name': 'Instagram', 'instagram_kind': 'reel', 'extraction': 'instagram_fallback'},\n    )\n    service = KnowledgeService(\n        repository=repo,\n        extractor=StaticExtractor(extracted),\n        ai_provider=HeuristicAIProvider(),\n        clock=SystemClock(),\n    )\n    item = await service.save_link(\n        user_id='telegram:smoke',\n        url='https://www.instagram.com/reel/DXkCDvJoYa8/',\n    )\n    print(item.source_type.value, item.status.value, item.title, ','.join(item.tags))\n    assert item.source_type is SourceType.INSTAGRAM\n    assert item.status.value == 'ready'\n    assert 'instagram' in item.tags\n    assert 'reel' in item.tags\n\nasyncio.run(main())\n\"\"\")"
```

Expected output includes:

```text
instagram ready Instagram Reel
```

- [ ] **Step 5: Confirm worktree only contains intentional changes**

Run:

```bash
git status --short
```

Expected: only implementation files touched by these tasks plus the pre-existing untracked `.env`.

- [ ] **Step 6: Do not create a final verification commit**

The implementation commits were created at the end of Tasks 1, 2, and 3. Leave the branch without an extra commit when Step 5 shows no uncommitted implementation changes.

Expected: no command is needed.
