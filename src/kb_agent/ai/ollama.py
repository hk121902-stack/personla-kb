from __future__ import annotations

import json
from typing import Any

import httpx

from kb_agent.ai.briefs import (
    AIErrorCategory,
    AIProviderError,
    build_enrichment_prompt,
    build_request_context,
    validate_learning_brief,
)
from kb_agent.core.models import ExtractedContent, LearningBrief, SavedItem


class OllamaBriefProvider:
    def __init__(self, *, http_client: httpx.AsyncClient, base_url: str, model: str) -> None:
        self._http_client = http_client
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def generate_learning_brief(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> LearningBrief:
        prompt = build_enrichment_prompt(build_request_context(item=item, extracted=extracted))
        try:
            response = await self._http_client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                },
                timeout=60,
            )
        except (httpx.ConnectError, httpx.ConnectTimeout) as error:
            raise AIProviderError(
                AIErrorCategory.LOCAL_PROVIDER_UNAVAILABLE,
                f"Ollama local provider is unavailable at {self.base_url}",
            ) from error
        except httpx.TimeoutException as error:
            raise AIProviderError(AIErrorCategory.TIMEOUT, "Ollama request timed out") from error
        except httpx.HTTPError as error:
            raise AIProviderError(
                AIErrorCategory.UNKNOWN_PROVIDER_ERROR,
                f"Ollama request failed: {error}",
            ) from error

        if response.status_code == 404:
            raise AIProviderError(AIErrorCategory.INVALID_MODEL, "Ollama model was not found")
        if response.status_code >= 400:
            raise AIProviderError(
                AIErrorCategory.UNKNOWN_PROVIDER_ERROR,
                f"Ollama request failed with HTTP {response.status_code}",
            )

        text = _extract_response_text(response)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise AIProviderError(
                AIErrorCategory.INVALID_RESPONSE,
                "Ollama returned invalid JSON",
            ) from error

        return validate_learning_brief(data, provider="ollama", model=self.model)


def _extract_response_text(response: httpx.Response) -> str:
    try:
        payload: Any = response.json()
        text = payload["response"]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise AIProviderError(
            AIErrorCategory.INVALID_RESPONSE,
            "Ollama returned an unexpected response shape",
        ) from error

    if not isinstance(text, str) or not text.strip():
        raise AIProviderError(
            AIErrorCategory.INVALID_RESPONSE,
            "Ollama returned an empty response",
        )

    return text
