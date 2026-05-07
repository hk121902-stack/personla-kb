# Visible Notes And Bold Save Labels Design

## Context

The compact Telegram response work made saved-link replies shorter and easier to scan, but notes are still not visible enough. Notes are parsed and stored as `user_note`, and retrieval scoring already uses them, but the save/show cards prefer generated summaries and do not display a clear `Note:` field. This makes it look like notes are not working even when they are persisted.

The save card also has useful metadata labels (`ID`, `Tags`, `Priority`, and `Need more`) that are plain text. These should be bold so the message is easier to scan in Telegram.

## Goals

- Make saved notes visible in Telegram save/share-link responses.
- Make notes visible in `show` / `find` compact result cards.
- Show the full note in the details view.
- Bold the key labels in save-style cards: `ID`, `Tags`, `Priority`, and `Need more`.
- Keep responses compact and uncluttered.
- Preserve Telegram HTML safety by escaping note text, tags, IDs, priorities, and user-provided content.

## Non-Goals

- Do not change note parsing syntax in this slice.
- Do not add a separate post-save `note` command in this slice.
- Do not change AI provider behavior beyond showing the note that is already stored.
- Do not expose raw long URLs as notes or add verbose note sections to every digest.

## Current Behavior

The reliable save syntax is:

```text
https://example.com/article note: learn this for agent memory priority: low
```

This produces:

```text
note = learn this for agent memory
priority = low
```

Priority requires the `priority` keyword:

```text
https://example.com/article priority: low
https://example.com/article priority low
```

A message such as:

```text
https://example.com/article low
```

is treated as note text, not priority.

## Proposed Behavior

### Save / Share-Link Response

When a saved item has a note, compact save cards should include a short visible note line:

```text
<b>ID:</b> kb_7f3a
<b>Tags:</b> ai, claude
<b>Priority:</b> low
<b>Note:</b> learn this for agent memory

short summary...

<b>Need more?</b> Reply "details" or send details kb_7f3a.
```

The note line should be omitted when the note is blank.

If both summary and note exist, the summary remains the compact learning summary, while the note is shown as user intent/context. The note should be capped to the existing compact summary style so a long note does not make the response bulky.

### Show / Find Compact Cards

`show` / `find` result cards should use the same compact card structure. If a saved item has a note, include a compact `Note:` line in the card. This makes saved intent visible when browsing search results.

### Details View

The details view should include the full note when present:

```text
<b>Note</b>
learn this for agent memory
```

This full note should appear before the summary so the user's original intent is easy to find.

### Bold Labels

The formatter should render these labels in bold where they appear in compact save/card contexts:

- `<b>ID:</b>`
- `<b>Tags:</b>`
- `<b>Priority:</b>`
- `<b>Note:</b>`
- `<b>Need more?</b>`

The value after the label should remain normal text for readability.

## Components

### Telegram Formatter

Update `src/kb_agent/telegram/formatter.py`:

- Add a helper for bold metadata labels.
- Update tag rendering to produce `<b>Tags:</b> ...`.
- Update save confirmation, learning brief, pending/retry messages, compact item cards, and details output where labels are shown.
- Add a compact note helper that escapes and truncates note text for card output.
- Add a full note section in `format_item_details`.

### Tests

Update formatter and bot adapter tests:

- Save confirmation includes bold `ID`, `Tags`, `Priority`, `Note`, and `Need more` labels.
- Compact show/find cards include the note when present.
- Details view includes full note when present.
- Note content is HTML-escaped.
- Blank notes do not render an empty `Note:` line.

## Error Handling And Safety

- All note text must be HTML-escaped before Telegram HTML parse mode.
- Long notes should be compacted/truncated in cards.
- Details can show the full note because the user explicitly asked for more detail.
- Existing save syntax and priority parsing remain unchanged.

## Success Criteria

- Saving a link with `note:` shows the note in the immediate Telegram response.
- `show` / `find` results show a compact note line when the item has a note.
- `details` shows the full saved note.
- Metadata labels are bold and values remain readable.
- Full tests and ruff pass.
