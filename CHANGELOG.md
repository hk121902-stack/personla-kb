# Changelog

## v0.0.1 - 2026-05-03

### Added

- Telegram bot command surface and message parsing/formatting.
- Scheduler support for daily and weekly digests.
- Runtime settings hooks for scheduling and chat filtering.
- Heuristic-first extraction and archive state workflow.

### Changed

- Digest generation and retrieval flows now exclude archived items by default.
- Chat scope now respects the configured `KB_TELEGRAM_CHAT_ID` for Telegram ingestion and proactive messaging.

### Fixed

- Handling of extraction failures on blocked platforms by preserving link saves.
- URL parsing and webpage extraction hardening.
- Message parsing edge cases (notes and priority parsing).
- Scheduler lifecycle/startup edge cases during startup/shutdown.
- Archive review and fallback behavior for missing data paths.

### Docs

- Added release documentation in this changelog and improved README usage guidance.
