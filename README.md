# Personal Knowledge Base Agent

Telegram-first personal knowledge base agent for saving links, surfacing them later, and answering questions from your own saved knowledge first.

## Features

- Telegram bot interface (`save`, `ask`, `digest`, `review archive`).
- Save links immediately, with optional notes and priority.
- Fallback path when extraction fails (link is still saved, and you can add manual context).
- Daily + weekly digest generation with scheduled delivery.
- Duplicate/low-value item recommendations for archival review.
- Search and answer flow that excludes archived items by default.
- Lightweight SQLite-backed storage and a modular core suitable for future providers.
- Stable, editable aliases for saved items and AI enrichment metadata persistence.
- Optional AI enrichment layer with configurable provider chaining (`gemini`, `ollama`, `heuristic`).

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
cp .env.example .env
pip install -e ".[dev]"
python -m kb_agent.app
```

Populate `.env` with:

- `TELEGRAM_BOT_TOKEN` (required)
- `KB_TELEGRAM_CHAT_ID` (required; filters inbound messages and links digests to the target chat)

Optional runtime configuration:

- `KB_DAILY_DIGEST_HOUR`
- `KB_WEEKLY_DIGEST_DAY`
- `KB_WEEKLY_DIGEST_HOUR`
- `KB_TIMEZONE`
- `KB_AI_PROVIDER_CHAIN` (defaults to Gemini, Ollama, then heuristic fallback)
- `KB_GEMINI_API_KEY`
- `KB_GEMINI_MODEL`
- `KB_OLLAMA_BASE_URL`
- `KB_OLLAMA_MODEL`
- `KB_AI_SYNC_WAIT_SECONDS`
- `KB_AI_RETRY_INTERVAL_MINUTES`

## AI Understanding Layer

Phase 2 can enrich saved items with structured AI learning briefs. Configure the provider chain in `.env`:

```dotenv
KB_AI_PROVIDER_CHAIN=gemini:gemini-2.5-flash-lite,gemini:gemini-2.5-flash,ollama:qwen3:8b,heuristic
KB_GEMINI_API_KEY=
KB_OLLAMA_BASE_URL=http://localhost:11434
KB_OLLAMA_MODEL=qwen3:8b
```

Gemini is the default cloud path for high-quality brief generation. Ollama keeps enrichment local/private when you have a local model running. The heuristic provider is the final safe fallback so saved items can still be summarized when AI providers are unavailable.

Useful Telegram commands:

- `ai status`
- `model gemini:gemini-2.5-flash`
- `model ollama:qwen3:8b`
- `refresh kb_7f3a`

Run tests:

```bash
pytest
ruff check .
```

## Telegram Commands

- Send a plain link: saves immediately.
- `save <link> note: <note> priority: high|medium|low`
- `ask <question>`
- `digest today`
- `digest week`
- `review archive`
- `archive <item_id>`
- `show <topic-or-tag-or-query>`

Archived items are excluded from default answers and digests.

## Extraction Fallback

If source extraction is blocked, the bot keeps the URL and prompts you to add your own summary text:
`save <url> note: <text>`.

## Release Notes

See `CHANGELOG.md` for version history. Current release: `v0.0.2`.

- oEmbed fallback for YouTube and X links now preserves useful summaries when primary extraction is blocked.
- Stable item aliases and improved AI enrichment command flows improve reliability for Telegram workflows.

## Development Notes

- `docs/superpowers/specs/2026-05-03-personal-knowledge-base-agent-design.md` captures the MVP design rationale.
- Tests are in `tests/`, and core behavior is validated independently from Telegram adapter glue.
