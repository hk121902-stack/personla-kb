import kb_agent


def test_package_exposes_version() -> None:
    assert kb_agent.__version__ == "0.1.0"
