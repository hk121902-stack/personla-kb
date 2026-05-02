from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from kb_agent.core.models import ExtractedContent

MAX_WEBPAGE_BODY_BYTES = 1024 * 1024


class StaticExtractor:
    def __init__(self, content: ExtractedContent | None) -> None:
        self.content = content

    async def extract(self, url: str) -> ExtractedContent | None:
        return self.content


@dataclass(frozen=True)
class WebpageExtractor:
    client: httpx.AsyncClient

    async def extract(self, url: str) -> ExtractedContent | None:
        if not _is_safe_url(url):
            return None

        try:
            response = await self.client.get(url, follow_redirects=False)
        except httpx.HTTPError:
            return None

        if response.status_code < 200 or response.status_code >= 300:
            return None

        if len(response.content) > MAX_WEBPAGE_BODY_BYTES:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else ""
        for hidden in soup(["head", "script", "style", "noscript"]):
            hidden.decompose()

        text = soup.get_text(" ", strip=True)

        return ExtractedContent(
            title=title,
            text=text,
            metadata={"status_code": str(response.status_code)},
        )


def _is_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False

    host = parsed.hostname
    if host is None:
        return False

    host = host.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return False

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True

    return not (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    )
