# Manual QA

## Local Bot Smoke Test

1. Create a Telegram bot token with BotFather.
2. Copy `.env.example` to `.env`.
3. Set `TELEGRAM_BOT_TOKEN`.
4. Set `KB_TELEGRAM_CHAT_ID` to the chat where links will be saved.
5. Run `python -m kb_agent.app`.
6. Send `https://example.com`.
7. Confirm the bot replies with `Saved:`.
8. Send `ask example domain`.
9. Confirm the bot replies with `From your knowledge base`, includes the Example Domain source/content, and does not say `No strong saved source match`.
10. Send `digest today`.
11. Confirm the bot returns 1-3 active items.
12. Send `review archive`.
13. Confirm the bot returns recommendations or says none are ready.

## Scheduled Digest Check

1. Set `KB_TELEGRAM_CHAT_ID` to the chat where test items are saved.
2. Confirm `KB_TIMEZONE`, `KB_DAILY_DIGEST_HOUR`, `KB_WEEKLY_DIGEST_DAY`, and `KB_WEEKLY_DIGEST_HOUR` match the expected delivery window.
3. Confirm scheduled digests only include active items from that chat-scoped knowledge base.

## Trust Checks

- Extraction failure keeps the link saved.
- Archived items do not appear in default answers.
- Weak search matches are labelled clearly.
- Archive recommendations do not archive automatically.
