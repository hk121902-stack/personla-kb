from kb_agent.core.models import Priority
from kb_agent.telegram.parser import AskCommand, ParseCommand, SaveCommand, parse_message


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
