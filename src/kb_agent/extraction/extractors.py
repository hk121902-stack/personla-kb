from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass
from typing import NamedTuple
from urllib.parse import urlencode, urlparse

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

    async def _extract_youtube_metadata(self, url: str) -> ExtractedContent | None:
        if not _is_youtube_url(url):
            return None

        oembed_url = "https://www.youtube.com/oembed?" + urlencode(
            {"format": "json", "url": url},
        )
        target = _safe_fetch_target(oembed_url)
        if target is None:
            return None

        try:
            response = await self.client.get(
                target.url,
                headers=target.headers,
                extensions=target.extensions,
            )
        except httpx.HTTPError:
            return None

        if response.status_code < 200 or response.status_code >= 300:
            return None

        try:
            payload = response.json()
        except json.JSONDecodeError:
            return None

        title = _string_payload_value(payload, "title")
        if not title:
            return None

        author_name = _string_payload_value(payload, "author_name")
        provider_name = _string_payload_value(payload, "provider_name") or "YouTube"
        text_parts = [f"YouTube video: {title}"]
        if author_name:
            text_parts.append(f"Channel: {author_name}")
        text_parts.append(f"URL: {url}")

        metadata = {"provider_name": provider_name}
        if author_name:
            metadata["author_name"] = author_name

        return ExtractedContent(
            title=title,
            text="\n".join(text_parts),
            metadata=metadata,
        )

    async def _extract_x_metadata(self, url: str) -> ExtractedContent | None:
        if not _is_x_url(url):
            return None

        oembed_url = "https://publish.twitter.com/oembed?" + urlencode(
            {"omit_script": "1", "url": url},
        )
        target = _safe_fetch_target(oembed_url)
        if target is None:
            return None

        try:
            response = await self.client.get(
                target.url,
                headers=target.headers,
                extensions=target.extensions,
            )
        except httpx.HTTPError:
            return None

        if response.status_code < 200 or response.status_code >= 300:
            return None

        try:
            payload = response.json()
        except json.JSONDecodeError:
            return None

        html = _string_payload_value(payload, "html")
        text = _html_to_text(html)
        if not text:
            return None

        author_name = _string_payload_value(payload, "author_name")
        provider_name = _string_payload_value(payload, "provider_name") or "Twitter"
        title = f"{author_name} on X" if author_name else "X post"

        metadata = {"provider_name": provider_name}
        if author_name:
            metadata["author_name"] = author_name

        return ExtractedContent(
            title=title,
            text=text,
            metadata=metadata,
        )

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


def _is_youtube_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").removeprefix("www.").lower()
    return hostname == "youtube.com" or hostname.endswith(".youtube.com") or hostname == "youtu.be"


def _is_x_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").removeprefix("www.").lower()
    return hostname == "x.com" or hostname.endswith(".x.com") or hostname == "twitter.com"


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


def _string_payload_value(payload: object, key: str) -> str:
    if not isinstance(payload, dict):
        return ""
    value = payload.get(key)
    if not isinstance(value, str):
        return ""
    return value.strip()


def _html_to_text(html: str) -> str:
    if not html.strip():
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(" ", strip=True)
