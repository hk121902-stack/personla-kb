from kb_agent.core.models import SourceType
from kb_agent.extraction.url_parser import detect_source_type, find_first_url


def test_find_first_url_from_message() -> None:
    assert find_first_url("save https://x.com/user/status/1 note this") == (
        "https://x.com/user/status/1"
    )


def test_detects_primary_source_types() -> None:
    assert detect_source_type("https://x.com/user/status/1") is SourceType.X
    assert detect_source_type("https://twitter.com/user/status/1") is SourceType.X
    assert detect_source_type("https://youtube.com/watch?v=abc") is SourceType.YOUTUBE
    assert detect_source_type("https://youtu.be/abc") is SourceType.YOUTUBE
    assert detect_source_type("https://linkedin.com/posts/demo") is SourceType.LINKEDIN
    assert detect_source_type("https://example.com/article") is SourceType.WEB


def test_detects_source_types_from_common_subdomains() -> None:
    assert detect_source_type("https://m.youtube.com/watch?v=abc") is SourceType.YOUTUBE
    assert detect_source_type("https://www.linkedin.com/posts/demo") is SourceType.LINKEDIN


def test_detect_source_type_avoids_spoofed_domains() -> None:
    assert detect_source_type("https://youtube.com.example.com/watch?v=abc") is SourceType.WEB
