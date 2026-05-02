from __future__ import annotations

from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from kb_agent.core.models import ExtractedContent


@dataclass(frozen=True)
class WebpageExtractor:
    client: httpx.AsyncClient

    async def extract(self, url: str) -> ExtractedContent | None:
        response = await self.client.get(url)
        if response.status_code < 200 or response.status_code >= 300:
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
