from datetime import UTC, datetime

import pytest

from kb_agent.ai.briefs import AIErrorCategory, AIProviderError
from kb_agent.ai.router import AIProviderRouter, BriefProvider, ProviderChainEntry
from kb_agent.core.models import AIStatus, LearningBrief, SavedItem, SourceType, Status


class FakeProvider(BriefProvider):
    def __init__(self, name: str, model: str, result: LearningBrief | Exception) -> None:
        self.name = name
        self.model = model
        self.result = result
        self.calls = 0

    async def generate_learning_brief(self, item, extracted):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _item() -> SavedItem:
    return SavedItem.new(
        user_id="telegram:123",
        url="https://example.com/router",
        source_type=SourceType.WEB,
        now=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
    )


def _brief(provider: str, model: str) -> LearningBrief:
    return LearningBrief(
        brief_version=1,
        provider=provider,
        model=model,
        generated_at=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
        title="Router Brief",
        topic="ai",
        tags=["router"],
        summary="Router summary.",
        key_takeaways=["First success wins."],
        why_it_matters="Predictable cost.",
        estimated_time_minutes=10,
        suggested_next_action="Inspect ai status.",
    )


@pytest.mark.asyncio
async def test_router_stops_after_first_success() -> None:
    first = FakeProvider("gemini", "fast", _brief("gemini", "fast"))
    second = FakeProvider("ollama", "qwen3:8b", _brief("ollama", "qwen3:8b"))
    router = AIProviderRouter(
        [ProviderChainEntry("gemini", "fast"), ProviderChainEntry("ollama", "qwen3:8b")],
        providers={"gemini:fast": first, "ollama:qwen3:8b": second},
    )

    enriched = await router.enrich(_item(), None)

    assert enriched.ai_status is AIStatus.READY
    assert enriched.learning_brief is not None
    assert enriched.learning_brief.provider == "gemini"
    assert first.calls == 1
    assert second.calls == 0


@pytest.mark.asyncio
async def test_router_falls_back_on_rate_limit() -> None:
    first = FakeProvider(
        "gemini",
        "lite",
        AIProviderError(AIErrorCategory.RATE_LIMIT, "rate limited"),
    )
    second = FakeProvider("gemini", "flash", _brief("gemini", "flash"))
    router = AIProviderRouter(
        [ProviderChainEntry("gemini", "lite"), ProviderChainEntry("gemini", "flash")],
        providers={"gemini:lite": first, "gemini:flash": second},
    )

    enriched = await router.enrich(_item(), None)

    assert enriched.learning_brief is not None
    assert enriched.learning_brief.model == "flash"
    assert router.status().last_error == "rate limited"


@pytest.mark.asyncio
async def test_router_heuristic_after_real_failure_is_retry_pending() -> None:
    first = FakeProvider(
        "ollama",
        "qwen3:8b",
        AIProviderError(AIErrorCategory.LOCAL_PROVIDER_UNAVAILABLE, "ollama unavailable"),
    )
    heuristic = FakeProvider("heuristic", "heuristic", _brief("heuristic", "heuristic"))
    router = AIProviderRouter(
        [ProviderChainEntry("ollama", "qwen3:8b"), ProviderChainEntry("heuristic", "heuristic")],
        providers={"ollama:qwen3:8b": first, "heuristic:heuristic": heuristic},
    )

    enriched = await router.enrich(_item(), None)

    assert enriched.learning_brief is not None
    assert enriched.learning_brief.provider == "heuristic"
    assert enriched.ai_status is AIStatus.RETRY_PENDING
    assert enriched.status is Status.READY
    assert "ollama unavailable" in enriched.ai_last_error


def test_router_updates_runtime_model_only_inside_configured_chain() -> None:
    router = AIProviderRouter(
        [ProviderChainEntry.parse("gemini:lite"), ProviderChainEntry.parse("gemini:flash")],
        providers={
            "gemini:lite": FakeProvider("gemini", "lite", _brief("gemini", "lite")),
            "gemini:flash": FakeProvider("gemini", "flash", _brief("gemini", "flash")),
        },
    )

    router.select_model("gemini:flash")

    assert router.status().chain == ["gemini:flash", "gemini:lite"]
    with pytest.raises(ValueError, match="not in configured provider chain"):
        router.select_model("gemini:expensive")
