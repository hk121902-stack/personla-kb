# Personal Knowledge Base Agent Design

Date: 2026-05-03

## Summary

Build a Telegram-first personal knowledge base agent for saving interesting links and resurfacing them later. The first version focuses on two user problems:

- Saved links are forgotten and rarely revisited.
- Saved links are scattered and hard to find later.

The product is not a general bookmark manager or full learning management system in phase one. It is a lightweight chat agent that turns saved links into a searchable, resurfacing personal memory.

## Goals

- Let the user save links from X/Twitter, YouTube, LinkedIn, and similar sources through Telegram.
- Always save the original link immediately, even when extraction fails.
- Extract metadata and content when possible.
- Support optional personal notes and optional priority.
- Organize saved items with AI-generated title, tags, topic, and summary when enough signal exists.
- Answer questions from saved knowledge first, then add clearly separated general AI context when useful.
- Send daily tiny nudges and weekly themed digests.
- Recommend individual saved items for archival review when they are old and low priority or duplicate/overlapping with newer content.
- Exclude archived items from default answers and digests.
- Keep AI providers swappable so deployment and privacy choices can be decided later.

## Non-Goals

- No browser extension in phase one.
- No full web dashboard in phase one.
- No automatic archival without user confirmation.
- No topic-level or collection-level archival in phase one.
- No requirement for perfect automatic extraction from every social platform.
- No fixed commitment to a specific cloud, local database, or AI provider in the design.

## Recommended MVP Approach

Use a Telegram bot as the first and primary product surface. The user can forward links, paste links, add notes, set priority, ask questions, request digests, and archive individual items from chat.

The implementation should still keep product logic in a separate knowledge core instead of embedding all behavior directly inside Telegram handlers. This preserves a simple user experience while leaving room for a future web admin UI, alternate chat surfaces, local-first storage, or a different AI provider.

## Core Components

### Telegram Bot Adapter

Receives user messages and maps them into knowledge commands. It owns chat-specific concerns such as commands, buttons, message formatting, and Telegram user identity.

It should stay thin. It should not own extraction rules, retrieval rules, digest selection, archival recommendation logic, or AI provider calls.

### Knowledge Core

Owns product behavior:

- Save item.
- Attach note.
- Set priority.
- Enrich item.
- Search active knowledge.
- Generate saved-first answers.
- Build daily and weekly digests.
- Recommend items for archive review.
- Archive individual items.

### Extractor Port

Attempts to fetch source content and metadata. It can support providers incrementally:

- YouTube metadata and transcript when available.
- General webpage metadata.
- Social post metadata when available.
- Manual pasted text fallback when platforms block access.

Extraction failure must not prevent saving the source link.

### AI Provider Port

Provides AI operations behind a swappable interface:

- Title cleanup.
- Tag and topic suggestion.
- Short summary generation.
- Embedding generation.
- Answer synthesis.
- Digest synthesis.
- Duplicate/overlap analysis.

The first implementation may use any practical provider, but the core design should not assume a single permanent model or vendor.

### Storage And Index

Stores saved item records, metadata, extracted content, user notes, priority, archive status, event history, and search indexes. The first implementation can choose a simple persistence layer, but the data model should support future migration.

### Scheduler

Triggers:

- Daily tiny nudge.
- Weekly synthesis.
- Future spaced review reminders.

The scheduler should call the knowledge core rather than directly building digest content.

## Save And Enrichment Flow

1. User sends or forwards a link to Telegram.
2. Bot creates a saved item immediately with status `processing`.
3. Bot records the original link, source type, user id, created date, and any note or priority included in the message.
4. Extractor attempts to fetch title, metadata, and content.
5. If extraction works, AI enrichment suggests title, tags, topic, optional summary, and embeddings.
6. If extraction fails, the item remains saved and the bot asks the user to paste the relevant text, transcript, or snippet.
7. Bot sends a compact confirmation.

Default confirmation:

```text
Saved: <title>
Tags: <tag1>, <tag2>, <tag3>
Priority: unset|low|medium|high
Status: ready|needs text
```

A short summary can be included when useful, but the default response should stay lightweight.

## Commands And Interactions

Phase-one commands should be small and memorable:

```text
save <link> [note...]
note <item> <text>
priority <item> low|medium|high
ask <question>
digest today
digest week
review archive
archive <item>
show <topic/tag>
```

The bot should also accept natural language where practical. For example, a plain question should be treated as an ask request, and a plain link should be treated as a save request.

## Saved Item Data Shape

Each saved item should store:

- Stable item id.
- Telegram user id.
- Original link.
- Source type.
- Source metadata.
- Title.
- Extracted text if available.
- User note.
- Tags.
- Topic.
- Summary.
- Priority: unset, low, medium, or high.
- Status: processing, ready, needs_text, or failed_enrichment.
- Archived flag and archived date.
- Created date.
- Updated date.
- Last surfaced date.
- Digest/review appearance count.
- Embedding or index reference.

Archived items are excluded from default search, answers, and digests.

## Retrieval Behavior

When the user asks a question, the bot searches active saved items first using semantic similarity plus title, tag, topic, and note signals.

Responses should be split into two sections:

```text
From your knowledge base
<concise answer grounded in saved items>
Sources:
- <item title> - <link>

Extra context
<general AI explanation, clearly marked as outside saved knowledge>
```

If saved matches are weak, the bot should say it did not find a strong match and show the closest items instead of pretending. The user can ask to include archived items explicitly.

## Digest Behavior

### Daily Tiny Nudge

Daily digest should contain 1-3 active items and be readable in under a minute. It should favor items that are recent, high priority, or not recently surfaced.

### Weekly Synthesis

Weekly digest should contain 5-7 active items grouped by theme. It should include:

- Theme names.
- Why each cluster matters.
- Source links.
- Suggested next actions such as read, watch, try, summarize, or archive.

### Future Spaced Review

Spaced review is lower priority than daily and weekly digests. It can reuse the scheduler and surfaced-item history later.

## Archive Review Behavior

Archive recommendations are suggestions only. The bot must never archive automatically.

An item can be recommended for archive review when:

- It is at least 60 days old and priority is `low`.
- It appears duplicate or strongly overlapping with newer saved items, meaning the newer item covers the same idea with equal or better source content.

Archive review is item-level only in phase one. Topic-level and collection-level archive are out of scope.

## Error Handling And Trust

- If extraction fails, save the link and ask for pasted text.
- If a platform blocks access, say the link was saved but content extraction needs user help.
- If AI confidence is low, treat tags and summaries as suggestions.
- If search finds weak matches, show closest saved items and state that no strong match was found.
- If digest material is thin, send a smaller digest instead of filler.
- If provider calls fail, keep the item saved and retry enrichment later.

## Testing Strategy

Test the behavior through the knowledge core first, with Telegram covered by adapter-level tests.

Core tests should cover:

- Plain link save creates a saved item.
- Link plus note records the note.
- Priority can be set during or after save.
- Extraction success enriches title, tags, topic, summary, and index data.
- Extraction failure keeps the item saved and marks it as `needs_text`.
- Retrieval excludes archived items by default.
- Retrieval can include archived items when explicitly requested.
- Weak retrieval matches are reported honestly.
- Daily digest selects 1-3 active items.
- Weekly digest groups active items by theme.
- Archive review recommends old low-priority items.
- Archive review recommends duplicate or overlapping items.
- Provider failure does not lose saved links.

## Phase-One Success Criteria

The MVP is successful when the user can:

- Save links from Telegram with almost no friction.
- Add notes and priority when useful without being forced.
- Receive daily and weekly resurfacing that feels worth opening.
- Ask natural questions and find saved material they would otherwise forget.
- Archive stale individual items so future results stay clean.

## Approved Decisions

- First surface: Telegram bot.
- First approach: Telegram Memory Agent MVP.
- Main problems: forgotten saved links and hard-to-find saved links.
- Resurfacing priority: daily/weekly digest first, topic-triggered retrieval second, spaced review third, goal-based workflows later.
- Ingestion: automatic extraction when possible, manual paste fallback when blocked, optional notes always available.
- Answering: saved links first, clearly separated general AI context second.
- Digest rhythm: daily tiny nudge and weekly synthesis.
- Save confirmation: lightweight by default with title, tags, status, and optional priority.
- Archival: individual saved items only for phase one.
- Archive recommendations: old low-priority items and duplicate/overlapping items.
- Privacy/deployment: decide later, but keep providers swappable.
