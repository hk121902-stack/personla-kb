# Changelog

## Unreleased

### Added

- _(No entries yet.)_

## v0.0.2 - 2026-05-04

### Added

- Phase 2 AI understanding layer with provider routing and fallback (`gemini`, `ollama`, `heuristic`).
- Stable item aliases for saved items.
- New Telegram AI commands: `ai status`, `model`, `refresh`.
- AI learning brief follow-up flow with provider runtime tuning and configurable model chain.
- Added extraction metadata fallback via oEmbed for X and YouTube links.
- Expanded persistence for alias and AI enrichment metadata.

### Changed

- Split item capture from AI enrichment for better reliability.
- Tightened AI runtime config parsing, validation, and chain handling.
- Improved telegram enrichment command states and follow-up behavior.

### Fixed

- Preserved items when AI providers fail during enrichment.
- Preserved retry diagnostics and surfaced persisted AI status errors.
- Improved handling of blocked/blank refreshes and needs-text follow-up edge cases.
- Preserved note save semantics across failed save follow-ups.
- Hardening around router attempts, digest retries, and alias mutation persistence.

### Docs

- Updated changelog and README for the `v0.0.2` release.

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
