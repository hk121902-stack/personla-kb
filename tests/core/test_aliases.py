import pytest

from kb_agent.core.aliases import alias_for_item_id, is_item_alias


def test_alias_for_item_id_uses_short_stable_prefix() -> None:
    assert alias_for_item_id("7f3a9b8c1234") == "kb_7f3a"


def test_alias_for_item_id_accepts_longer_prefix() -> None:
    assert alias_for_item_id("7f3a9b8c1234", length=8) == "kb_7f3a9b8c"


def test_alias_for_item_id_generates_aliases_accepted_by_alias_validator() -> None:
    assert is_item_alias(alias_for_item_id("7F3A9B8C1234", length=8)) is True


def test_alias_for_item_id_rejects_length_below_alias_range() -> None:
    with pytest.raises(ValueError, match="Alias length must be between 4 and 32"):
        alias_for_item_id("7f3a9b8c1234", length=3)


def test_alias_for_item_id_rejects_length_above_alias_range() -> None:
    with pytest.raises(ValueError, match="Alias length must be between 4 and 32"):
        alias_for_item_id("7f3a9b8c1234", length=33)


def test_alias_for_item_id_rejects_non_hex_item_id() -> None:
    with pytest.raises(
        ValueError,
        match="Item id prefix must contain only lowercase hex characters",
    ):
        alias_for_item_id("item-123")


def test_is_item_alias_accepts_kb_prefix() -> None:
    assert is_item_alias("kb_7f3a") is True
    assert is_item_alias("7f3a") is False
