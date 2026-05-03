from __future__ import annotations

import json
from typing import Any

import httpx

from kb_agent.ai.briefs import (
    AIErrorCategory,
    AIProviderError,
    build_enrichment_prompt,
    build_learning_brief_schema,
    build_request_context,
    validate_learning_brief,
)
from kb_agent.core.models import ExtractedContent, LearningBrief, SavedItem


class GeminiBriefProvider:
    def __init__(self, *, http_client: httpx.AsyncClient, api_key: str, model: str) -> None:
        self._http_client = http_client
        self._api_key = api_key
        self.model = model

    async def generate_learning_brief(
        self,
        item: SavedItem,
        extracted: ExtractedContent | None,
    ) -> LearningBrief:
        if not self._api_key.strip():
            raise AIProviderError(
                AIErrorCategory.MISSING_API_KEY,
                "Gemini API key is missing",
            )

        prompt = build_enrichment_prompt(build_request_context(item=item, extracted=extracted))
        try:
            response = await self._http_client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                headers={"x-goog-api-key": self._api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "responseJsonSchema": build_learning_brief_schema(),
                    },
                },
                timeout=30,
            )
        except httpx.TimeoutException as error:
            raise AIProviderError(AIErrorCategory.TIMEOUT, "Gemini request timed out") from error
        except httpx.HTTPError as error:
            raise AIProviderError(
                AIErrorCategory.UNKNOWN_PROVIDER_ERROR,
                f"Gemini request failed: {error}",
            ) from error

        if response.status_code == 429:
            raise AIProviderError(AIErrorCategory.RATE_LIMIT, "Gemini rate limit exceeded")
        if response.status_code == 404:
            raise AIProviderError(AIErrorCategory.INVALID_MODEL, "Gemini model was not found")
        if response.status_code >= 400:
            raise AIProviderError(
                AIErrorCategory.UNKNOWN_PROVIDER_ERROR,
                f"Gemini request failed with HTTP {response.status_code}",
            )

        text = _extract_candidate_text(response)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise AIProviderError(
                AIErrorCategory.INVALID_RESPONSE,
                "Gemini returned invalid JSON",
            ) from error

        return validate_learning_brief(data, provider="gemini", model=self.model)


def _extract_candidate_text(response: httpx.Response) -> str:
    try:
        payload: Any = response.json()
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise AIProviderError(
            AIErrorCategory.INVALID_RESPONSE,
            "Gemini returned an unexpected response shape",
        ) from error

    if not isinstance(text, str) or not text.strip():
        raise AIProviderError(
            AIErrorCategory.INVALID_RESPONSE,
            "Gemini returned an empty response",
        )

    return text
