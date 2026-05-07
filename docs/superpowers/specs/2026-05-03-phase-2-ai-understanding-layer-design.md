# Phase 2 AI Understanding Layer Design

Date: 2026-05-03

## Summary

Phase 2 adds a real AI understanding layer to the personal knowledge base agent. The goal is to turn each saved link into a useful learning brief while keeping the Phase 1 trust behavior: save links immediately, never lose user context, and make failures visible without blocking capture.

The phase adds a provider router with Gemini as the default cloud path, Ollama as a local/private path, and the existing heuristic provider as the final safe fallback. It also adds structured learning brief storage, short item aliases for Telegram commands, manual brief refresh, provider diagnostics, and conservative retry behavior.

## Goals

- Generate structured learning briefs for saved items.
- Support Gemini, Ollama, and heuristic providers through one provider router.
- Make Gemini model selection configurable so cheaper or less rate-limited models can be selected.
- Support a configured fallback chain and stop after the first valid structured brief.
- Keep provider fallback cost-safe by never jumping outside the configured chain.
- Preserve the original URL, user note, priority, extracted content, and saved item even when AI fails.
- Show short item aliases in Telegram so commands such as `refresh kb_7f3a` and `archive kb_7f3a` are easy to use.
- Add `ai status`, `model <provider:model>`, and `refresh <item_id>` commands.
- Retry pending AI enrichment in the background without retrying archived items by default.
- Improve search inputs using AI-generated title, topic, tags, summary, takeaways, and user notes.

## Non-Goals

- No embeddings or vector search in Phase 2.
- No web dashboard.
- No automatic archival decisions.
- No provider quality comparison across multiple successful outputs.
- No persistent runtime model preference beyond `.env` in Phase 2.
- No expensive model fallback unless the model is explicitly configured.
- No use of unrelated saved history as enrichment context.

## Architecture

The existing knowledge core should continue to own product behavior, while provider-specific model calls live behind the AI provider boundary.

The AI layer should contain:

- `LearningBrief` domain object.
- Provider implementations for Gemini, Ollama, and heuristic enrichment.
- Provider router that receives an enrichment request and tries configured providers in order.
- Context builder that decides how much extracted content to send.
- Validation layer that rejects malformed provider output.
- Retry service or scheduler job that re-attempts pending AI enrichment.

The knowledge core should ask for a `LearningBrief`. It should not know how Gemini or Ollama APIs work.

Default provider chain example:

```text
gemini:gemini-2.5-flash-lite
gemini:gemini-2.5-flash
ollama:qwen3:8b
heuristic
```

The router stops after the first valid structured brief. It does not generate multiple briefs to compare quality. If the first valid result comes from the heuristic provider after a real provider failed, the item can still store the heuristic brief, but its AI status should remain retryable so Gemini or Ollama can improve it later.

## Learning Brief Schema

Each successful AI enrichment produces this structured shape:

```json
{
  "brief_version": 1,
  "provider": "gemini",
  "model": "gemini-2.5-flash-lite",
  "generated_at": "2026-05-03T10:00:00Z",
  "title": "Cleaned title",
  "topic": "Topic name",
  "tags": ["tag-one", "tag-two"],
  "summary": "Concise summary of the saved item.",
  "key_takeaways": ["First useful takeaway.", "Second useful takeaway."],
  "why_it_matters": "Why this is worth revisiting.",
  "estimated_time_minutes": 20,
  "suggested_next_action": "Try one concrete follow-up action."
}
```

There is no `difficulty` or `depth` field. Estimated time is enough review-planning signal for Phase 2.

## Storage

Saved item records keep their current searchable fields:

- title
- topic
- tags
- summary
- priority
- status
- archive state
- source metadata

Phase 2 adds structured AI enrichment data, preferably JSON-backed, while syncing key brief fields onto the saved item for existing retrieval and digest flows.

Each item should also track AI-specific state separately from extraction state:

```text
ai_status: pending | ready | retry_pending | failed
ai_attempt_count
ai_last_attempt_at
ai_last_error
```

This allows extraction to succeed even when AI enrichment is pending or failed.

`ready` means a non-heuristic provider produced the current brief, or the configured chain intentionally contains only heuristic enrichment. If heuristic is used only because Gemini or Ollama failed, the brief should be stored as basic enrichment and `ai_status` should stay `retry_pending`.

## Item Aliases

Telegram responses should include a short stable item alias anywhere the user may need to act on an item.

Example:

```text
Saved: Async Python Notes
ID: kb_7f3a
```

Aliases should appear in:

- save confirmations
- follow-up learning briefs
- `show <query>` results
- `digest today`
- `digest week`
- `review archive`
- `ask` sources when useful

Commands should accept aliases:

```text
refresh kb_7f3a
archive kb_7f3a
```

The internal stable item ID can remain unchanged. The alias should resolve back to that ID. If an alias collision occurs, the system should fall back to a longer alias.

## Save And Enrichment Flow

The bot keeps the Phase 1 save-first behavior.

1. Telegram receives a link with optional note and optional priority.
2. The item is saved immediately.
3. The bot obtains the short item alias.
4. Extraction runs as it does today.
5. AI brief generation starts through the provider router.
6. The bot waits briefly, controlled by `KB_AI_SYNC_WAIT_SECONDS`.
7. If the brief is ready in time, the save reply includes the learning brief.
8. If not ready, the bot replies with the item alias and says the learning brief is being prepared.
9. When enrichment finishes, the bot sends a follow-up learning brief with the same alias.
10. If all real AI providers fail, the item remains saved with basic enrichment and an AI retry state.

Delayed response example:

```text
Saved: <title or URL>
ID: kb_7f3a
Preparing learning brief...
```

Failure example:

```text
Saved with basic enrichment.
ID: kb_7f3a
AI brief is pending retry.
```

## Provider Configuration

Environment configuration should support:

```env
KB_AI_PROVIDER_CHAIN=gemini:gemini-2.5-flash-lite,gemini:gemini-2.5-flash,ollama:qwen3:8b,heuristic
KB_GEMINI_API_KEY=
KB_GEMINI_MODEL=gemini-2.5-flash-lite
KB_OLLAMA_BASE_URL=http://localhost:11434
KB_OLLAMA_MODEL=qwen3:8b
KB_AI_SYNC_WAIT_SECONDS=6
KB_AI_RETRY_INTERVAL_MINUTES=30
```

The configured provider chain is the cost boundary. Automatic fallback must only try entries explicitly present in `KB_AI_PROVIDER_CHAIN`.

The current `.env` remains the source of truth after restart. Runtime Telegram model changes are process-local in Phase 2.

## Telegram Commands

Phase 2 adds:

```text
ai status
refresh <item_id>
model <provider:model>
```

`ai status` shows:

- active provider chain
- currently selected Gemini model
- Ollama base URL and model
- pending AI retry count
- last provider error

Example:

```text
AI status
Chain: gemini:gemini-2.5-flash-lite -> gemini:gemini-2.5-flash -> ollama:qwen3:8b -> heuristic
Pending retries: 3
Last error: Ollama unavailable at http://localhost:11434
```

`refresh <item_id>` regenerates the learning brief using the current provider chain.

`model <provider:model>` changes the runtime model or first provider selection for the current bot process. It must only be accepted from the configured Telegram chat. Manual model selection is treated as explicit user intent, but automatic fallback still stays inside the configured chain.

Examples:

```text
model gemini:gemini-2.5-flash
model gemini:gemini-2.5-flash-lite
model ollama:qwen3:8b
```

## Context Policy

Each enrichment request should include:

- URL
- source type
- extracted title
- user note
- priority
- available metadata
- extracted text within a configured content cap

The default context should be trimmed to keep cloud calls cheap and privacy-friendlier. The context builder can include more extracted text when the item is short or high priority.

Phase 2 should not send archived items, unrelated saved history, or embeddings context into enrichment.

User notes are high-signal context. If the note and extracted content conflict, the generated brief should preserve the user's intent instead of erasing it.

## Prompting And Validation

Providers should be asked for structured JSON matching the learning brief schema. Free-form prose should not be accepted as a successful AI brief.

If a provider returns invalid JSON or fails schema validation, the router should classify that as an invalid AI response and try the next configured provider.

The Telegram rendering should remain compact:

```text
Learning brief: <title>
ID: kb_7f3a

Summary:
...

Key takeaways:
- ...
- ...

Why it matters:
...

Time: 20 min
Next: Try building a small example.
```

## Retry Behavior

Retries should be conservative:

- Retry only items with `pending` or `retry_pending`.
- Cap attempts per item.
- Skip archived items by default.
- Preserve the last provider error for diagnostics.
- Allow `refresh <item_id>` to manually retry even after failure.

If Ollama is unavailable, the bot should show a visible but calm notice and continue with fallback behavior. If every real provider fails, heuristic enrichment can keep the item useful while AI state remains retryable.

## Error Handling And Trust

Provider errors should be classified into simple categories:

- missing API key
- rate limit
- timeout
- invalid model
- invalid AI response
- local provider unavailable
- unknown provider error

User-facing messages should be short and actionable:

```text
Saved. AI brief is pending retry because Gemini hit a rate limit.
```

```text
Saved with basic enrichment because Ollama is unavailable.
```

```text
Could not refresh kb_7f3a because the selected model is invalid.
```

The system must never lose the original URL, note, priority, or extracted content because AI failed.

## Testing Strategy

Core tests should cover:

- Gemini provider returns a valid learning brief from structured JSON.
- Invalid provider JSON is rejected.
- Router stops after the first valid provider result.
- Router falls back from rate limit to the next configured provider.
- Router falls back from Ollama unavailable to heuristic or basic enrichment.
- No provider fallback jumps outside the configured chain.
- Smart context policy trims normal items and allows more context for high-priority or short items.
- Learning brief JSON is stored and key fields sync onto the saved item.
- `refresh <item_id>` regenerates the brief using the current provider chain.
- AI retry job picks pending items, caps attempts, and skips archived items.
- Short item alias resolves to the stable item ID.

Telegram adapter tests should cover:

- Save response includes item alias.
- Delayed enrichment sends a follow-up brief.
- Failed enrichment says pending retry.
- `ai status` renders provider chain, pending count, and last error.
- `model <provider:model>` updates runtime selection only from the allowed chat.
- `refresh kb_xxxx` works with an alias.

Manual QA should cover:

- Gemini happy path with `gemini-2.5-flash-lite`.
- Gemini model switch to `gemini-2.5-flash`.
- Missing Gemini key falls back safely.
- Ollama running with a local model.
- Ollama not running gives a visible but non-blocking message.
- Saved item can still be asked/searched even if AI brief is pending.

## Success Criteria

Phase 2 is successful when:

- Saving a link usually produces a useful learning brief.
- Model/provider failures do not block saving.
- The user can understand provider health through `ai status`.
- The user can change Gemini or Ollama model behavior without code changes.
- The user can regenerate a brief with `refresh <item_id>`.
- Short item aliases make archive and refresh commands practical.
- Retrieval and digests become more useful because AI-generated fields improve item organization.
