# Telegram Compact Response Design

## Summary

Telegram responses should become compact, scan-friendly, and consistent across save, show/find, ask, daily digest, weekly digest, and archive-review flows. The bot should treat the default chat response as a short receipt, not a full article. Full learning detail remains available through a `details` flow.

## Goals

- Use Telegram HTML formatting for bold headings and clickable source titles.
- Keep default saved-link replies small: title, ID, tags, priority/time, 1-2 line summary, and a detail hint.
- Keep `show` and `find` list-oriented, with compact item cards instead of a long synthesized paragraph.
- Keep `ask` answer-oriented, with a short answer and compact sources.
- Keep daily and weekly digests uncluttered.
- Provide a clear expansion path through `details`.
- Ask AI providers for shorter summaries going forward, while trimming display output defensively.

## Non-Goals

- No web UI changes.
- No new database schema is required.
- No migration of existing verbose summaries is required.
- No advanced natural-language command router is required in this phase.

## UX Contract

### Saved Link Reply

Default save responses show a compact card:

```text
<b>Eric Schmidt's Agentic AI Playbook</b>
ID: kb_cac9
Tags: agentic-ai, startups, automation
Priority: low · 5 min

A short 1-2 line summary of why this is worth saving.

Need more? Reply "details" or send details kb_cac9.
```

The saved card should avoid raw long URLs when a clickable title link is available. Raw URLs can still appear in `details` or failure/help responses.

### Details Flow

The full brief moves behind `details`.

Supported inputs:

- `details kb_cac9`
- Reply to a bot message containing an item ID with `details`
- Reply with aliases `more` or `expand`
- Plain `details`, which opens the latest saved item in the current chat

All variants resolve to the same internal item-details behavior.

The detail response includes these fields when present:

- Full title
- ID
- Tags
- Priority
- Source URL
- Summary
- Key takeaways
- Why it matters
- Time
- Next action
- AI provider/model diagnostics only when the item is not ready or the user is in an AI status/debug flow

### Show And Find

`show <query>` and `find <query>` return a compact result list. They should not produce the current long "Based on saved items..." paragraph.

Example:

```text
<b>Found 3 items for "claude"</b>

<b><a href="...">Graphify + Claude Code</a></b>
ID: kb_9c6d
Tags: claude-code, repos
One short line about the item.

Need more? Reply "details" to an item, or send details kb_9c6d.
```

### Ask

`ask <question>` remains answer-oriented:

- 1-2 sentence answer
- Compact sources
- Detail hint

The `Extra context` block should not appear by default. It should appear only when the user explicitly asks for context, explanation, why, or how.

### Daily Digest

Daily digest remains a tiny nudge:

- Max 3 items
- Compact cards
- No long summaries
- Detail hint at the bottom

### Weekly Digest

Weekly digest groups by topic/theme:

- Max 5 items total
- Topic headings
- Compact cards under each topic
- Detail hint at the bottom

## Formatting Rules

- Use Telegram HTML parse mode.
- Escape all title, summary, tag, and source text before inserting into HTML.
- Use clickable title links for valid URLs.
- Do not expose long raw URLs in compact cards.
- Limit displayed summaries to 1-2 short lines.
- Limit displayed tags to at most 5.
- Use consistent labels: `ID`, `Tags`, `Priority`, `Next`.
- Avoid decorative noise and verbose status fields in normal responses.

## AI Summary Guidance

Update the learning-brief prompt so providers are asked for compact summaries:

- `summary` should be 1-2 short sentences.
- `key_takeaways` may remain structured for detail view.
- `suggested_next_action` should be short and action-oriented.

Display trimming remains required because older items and occasional model output may still be verbose.

## Architecture

Keep the implementation focused by adding or expanding a Telegram presentation layer:

- Shared helpers for HTML escaping, bold headings, clickable title links, tag formatting, truncation, and detail hints.
- Compact item-card rendering reused by save, show/find, ask sources, daily digest, weekly digest, and archive recommendations where appropriate.
- Detail rendering separated from compact rendering.
- Retrieval service can still score and return matches, but Telegram rendering should control compact presentation.
- Digest selection logic should remain in `DigestService`; digest text rendering will use shared compact card helpers.

## Details Resolution

Details command resolution should happen in Telegram adapter code:

1. If the command includes an explicit item reference, use it.
2. Else, if the message replies to a bot message containing `ID: kb_...`, use that ID.
3. Else, resolve the latest saved item for the chat.
4. If no item is available, return a short help message.

Add a repository query/helper for latest saved item by user. It should exclude archived items by default.

## Error Handling

- If HTML formatting fails because of malformed source text, escaping should prevent Telegram parse errors.
- If a detail ID cannot be resolved, return `I could not find that saved item.`
- If `details` has no reply and no latest item exists, return `No saved item yet. Send a link first.`
- If a compact card has no summary, use the title or a short fallback.
- If no search matches exist, keep the weak-match message short and avoid listing unrelated verbose content.

## Testing

Tests should cover:

- Compact saved-link formatting with bold title, ID, tags, priority/time, short summary, and detail hint.
- HTML escaping for titles, summaries, tags, and URLs.
- Details rendering includes hidden fields.
- `details kb_...` resolves explicit IDs.
- Reply-based `details`, `more`, and `expand` resolve IDs from replied bot text.
- Plain `details` resolves the latest saved item.
- `show/find` produces compact result cards.
- `ask` produces a short answer with compact sources and no default extra-context block.
- Daily digest uses compact cards with max 3 items.
- Weekly digest groups compact cards by topic.
- AI prompt asks for 1-2 sentence summaries.

## Rollout Notes

Existing saved items may keep verbose stored summaries, but compact display trimming will improve them immediately. Users should restart the bot after deployment so Telegram parse-mode and formatter changes take effect.
