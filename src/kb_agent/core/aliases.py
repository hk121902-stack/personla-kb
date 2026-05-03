from __future__ import annotations

import re

_ALIAS_RE = re.compile(r"^kb_[0-9a-f]{4,32}$")


def alias_for_item_id(item_id: str, *, length: int = 4) -> str:
    normalized = item_id.strip().lower()
    return f"kb_{normalized[:length]}"


def is_item_alias(value: str) -> bool:
    return bool(_ALIAS_RE.match(value.strip().lower()))
