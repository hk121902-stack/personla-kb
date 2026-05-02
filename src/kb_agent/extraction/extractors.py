from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import NamedTuple
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from kb_agent.core.models import ExtractedContent

MAX_WEBPAGE_BODY_BYTES = 1024 * 1024


class SafeFetchTarget(NamedTuple):
    url: httpx.URL
    headers: dict[str, str]
    extensions: dict[str, str]


class StaticExtractor:
    def __init__(self, content: ExtractedContent | None) -> None:
        self.content = content

    async def extract(self, url: str) -> ExtractedContent | None:
        return self.content


@dataclass(frozen=True)
class WebpageExtractor:
    client: httpx.AsyncClient

    async def extract(self, url: str) -> ExtractedContent | None:
        target = _safe_fetch_target(url)
        if target is None:
            return None

        try:
            async with self.client.stream(
                "GET",
                target.url,
                headers=target.headers,
                extensions=target.extensions,
                follow_redirects=False,
            ) as response:
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


def _safe_fetch_target(url: str) -> SafeFetchTarget | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None

    host = parsed.hostname
    if host is None:
        return None

    host = host.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return None

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return _resolved_fetch_target(url, host)

    if not _is_safe_ip(ip):
        return None
    return SafeFetchTarget(url=httpx.URL(url), headers={}, extensions={})


def _resolved_fetch_target(url: str, host: str) -> SafeFetchTarget | None:
    parsed = urlparse(url)
    port = parsed.port or parsed.scheme
    try:
        addrinfos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return None

    resolved_ips = [ipaddress.ip_address(addrinfo[4][0]) for addrinfo in addrinfos]
    if not resolved_ips or not all(_is_safe_ip(ip) for ip in resolved_ips):
        return None

    target_url = httpx.URL(url).copy_with(host=str(resolved_ips[0]))
    headers = {"Host": _host_header(host, parsed.port, parsed.scheme)}
    extensions = {"sni_hostname": host} if parsed.scheme == "https" else {}

    return SafeFetchTarget(url=target_url, headers=headers, extensions=extensions)


def _host_header(host: str, port: int | None, scheme: str) -> str:
    if port is None:
        return host
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        return host
    return f"{host}:{port}"


def _is_safe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return ip.is_global and not ip.is_multicast
