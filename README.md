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

Copy `.env.example` to `.env`, fill `TELEGRAM_BOT_TOKEN`, then run the bot after implementation:

```bash
python -m kb_agent.app
```
