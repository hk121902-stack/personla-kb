from __future__ import annotations

import re

_ALIAS_RE = re.compile(r"^kb_[0-9a-f]{4,32}$")


def alias_for_item_id(item_id: str, *, length: int = 4) -> str:
    if length < 4 or length > 32:
        raise ValueError("Alias length must be between 4 and 32")
    normalized = item_id.strip().lower()
    prefix = normalized[:length]
    if len(prefix) != length or not re.fullmatch(r"[0-9a-f]+", prefix):
        raise ValueError(
            "Item id prefix must contain only lowercase hex characters "
            "and be at least the requested length"
        )
    return f"kb_{prefix}"


def is_item_alias(value: str) -> bool:
    return bool(_ALIAS_RE.match(value.strip().lower()))
