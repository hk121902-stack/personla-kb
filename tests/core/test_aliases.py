from kb_agent.core.aliases import alias_for_item_id, is_item_alias


def test_alias_for_item_id_uses_short_stable_prefix() -> None:
    assert alias_for_item_id("7f3a9b8c1234") == "kb_7f3a"


def test_alias_for_item_id_accepts_longer_prefix() -> None:
    assert alias_for_item_id("7f3a9b8c1234", length=8) == "kb_7f3a9b8c"


def test_is_item_alias_accepts_kb_prefix() -> None:
    assert is_item_alias("kb_7f3a") is True
    assert is_item_alias("7f3a") is False
