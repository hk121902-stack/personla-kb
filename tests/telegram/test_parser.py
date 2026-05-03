from kb_agent.core.models import Priority
from kb_agent.telegram.parser import (
    AIStatusCommand,
    ArchiveCommand,
    AskCommand,
    DigestCommand,
    ModelCommand,
    ParseCommand,
    RefreshCommand,
    ReviewArchiveCommand,
    SaveCommand,
    ShowCommand,
    parse_message,
)


def test_plain_link_becomes_save_command() -> None:
    command = parse_message("https://youtu.be/abc note: watch this priority: high")

    assert isinstance(command, SaveCommand)
    assert command.url == "https://youtu.be/abc"
    assert command.note == "watch this"
    assert command.priority is Priority.HIGH


def test_plain_link_accepts_priority_without_colon() -> None:
    command = parse_message("https://youtu.be/abc note: watch this priority high")

    assert isinstance(command, SaveCommand)
    assert command.url == "https://youtu.be/abc"
    assert command.note == "watch this"
    assert command.priority is Priority.HIGH


def test_save_command_link_without_note_has_empty_note() -> None:
    command = parse_message("save https://example.com/rag")

    assert isinstance(command, SaveCommand)
    assert command.url == "https://example.com/rag"
    assert command.note == ""


def test_plain_link_trims_trailing_sentence_punctuation() -> None:
    command = parse_message("save https://example.com/rag.")

    assert isinstance(command, SaveCommand)
    assert command.url == "https://example.com/rag"
    assert command.note == ""


def test_digest_today_command() -> None:
    command = parse_message("digest today")

    assert isinstance(command, DigestCommand)
    assert command.kind == "today"


def test_digest_week_command() -> None:
    command = parse_message("digest week")

    assert isinstance(command, DigestCommand)
    assert command.kind == "week"


def test_review_archive_command() -> None:
    assert isinstance(parse_message("review archive"), ReviewArchiveCommand)


def test_ai_status_command() -> None:
    assert isinstance(parse_message("ai status"), AIStatusCommand)


def test_refresh_command() -> None:
    command = parse_message("refresh kb_7f3a")

    assert isinstance(command, RefreshCommand)
    assert command.item_ref == "kb_7f3a"


def test_model_command() -> None:
    command = parse_message("model gemini:gemini-2.5-flash")

    assert isinstance(command, ModelCommand)
    assert command.provider_model == "gemini:gemini-2.5-flash"


def test_archive_command() -> None:
    command = parse_message("archive item123")

    assert isinstance(command, ArchiveCommand)
    assert command.item_id == "item123"


def test_show_command() -> None:
    command = parse_message("show vector databases")

    assert isinstance(command, ShowCommand)
    assert command.query == "vector databases"


def test_plain_question_becomes_ask_command() -> None:
    command = parse_message("what did I save about vector databases?")

    assert isinstance(command, AskCommand)
    assert command.question == "what did I save about vector databases?"


def test_include_archived_flag() -> None:
    command = parse_message("ask include archived vector databases")

    assert isinstance(command, AskCommand)
    assert command.include_archived is True


def test_unknown_empty_message_is_parse_command() -> None:
    assert isinstance(parse_message("   "), ParseCommand)
