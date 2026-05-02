from __future__ import annotations

import re
from urllib.parse import urlparse

from kb_agent.core.models import SourceType

_URL_RE = re.compile(r"https?://[^\s<>()]+")


def find_first_url(message: str) -> str | None:
    match = _URL_RE.search(message)
    if match is None:
        return None
    return match.group(0).rstrip(".,;:!?")


def detect_source_type(url: str) -> SourceType:
    hostname = (urlparse(url).hostname or "").removeprefix("www.").lower()

    if _host_matches(hostname, "x.com") or _host_matches(hostname, "twitter.com"):
        return SourceType.X
    if _host_matches(hostname, "youtube.com") or _host_matches(hostname, "youtu.be"):
        return SourceType.YOUTUBE
    if _host_matches(hostname, "linkedin.com"):
        return SourceType.LINKEDIN
    return SourceType.WEB


def _host_matches(hostname: str, domain: str) -> bool:
    return hostname == domain or hostname.endswith(f".{domain}")
