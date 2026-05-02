# Personal Knowledge Base Agent

Telegram-first personal knowledge base agent for saving links, resurfacing them, and asking saved-first questions.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```

## Runtime

Copy `.env.example` to `.env`, fill `TELEGRAM_BOT_TOKEN`, then run the bot:

```bash
python -m kb_agent.app
```

`TELEGRAM_BOT_TOKEN` is required. `KB_TELEGRAM_CHAT_ID` enables scheduled proactive digests and restricts inbound processing to that chat; it should match the chat where items are saved because the bot stores knowledge by chat id.

Digest scheduling is controlled by `KB_DAILY_DIGEST_HOUR`, `KB_WEEKLY_DIGEST_DAY`, `KB_WEEKLY_DIGEST_HOUR`, and `KB_TIMEZONE`. `KB_AI_PROVIDER` is reserved for provider selection; this MVP supports only `heuristic`, which runs without an external API key.

## Telegram Commands

- Send a plain link to save it.
- `save <link> note: <note> priority: high|medium|low`
- `ask <question>`
- `digest today`
- `digest week`
- `review archive`
- `archive <item_id>`
- `show <topic-or-tag-or-query>`

Archived items are excluded from default answers and digests.

## Extraction Fallback

Some X and LinkedIn content may be blocked by platform access rules. The bot still saves the link and asks you to paste the useful text as a note by sending `save <url> note: <text>` when extraction fails.
