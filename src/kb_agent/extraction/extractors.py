from __future__ import annotations

import ipaddress
import socket
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
            async with self.client.stream("GET", url, follow_redirects=False) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    return None

                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_WEBPAGE_BODY_BYTES:
                        return None
        except httpx.HTTPError:
            return None

        soup = BeautifulSoup(bytes(body), "html.parser")
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
        return _hostname_resolves_safely(host, parsed.port or parsed.scheme)

    return _is_safe_ip(ip)


def _hostname_resolves_safely(host: str, port: int | str) -> bool:
    try:
        addrinfos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False

    return all(_is_safe_ip(ipaddress.ip_address(addrinfo[4][0])) for addrinfo in addrinfos)


def _is_safe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    )
