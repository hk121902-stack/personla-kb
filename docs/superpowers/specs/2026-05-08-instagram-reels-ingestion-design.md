# Instagram Reels Ingestion Design

## Goal

Support saving Instagram Reels as a first-class knowledge source while keeping the user experience simple, compact, and reliable. A Reel should save even when Instagram does not expose useful public metadata.

## Scope

This phase covers Instagram public metadata extraction with fallback behavior.

In scope:

- Accept Instagram Reel URLs from Telegram save messages.
- Detect Instagram links as a dedicated source instead of generic web.
- Try to extract public page metadata such as title, description, and OpenGraph media fields.
- Use user notes as the most reliable signal when metadata is weak or unavailable.
- Keep Telegram responses compact with bold labels for important fields.
- Add fallback tags such as `instagram` and `reel` when better tags are unavailable.

Out of scope:

- Instagram login, authenticated scraping, or session cookies.
- Downloading Reel video or audio.
- Transcribing Reel audio.
- Meta app setup, Graph API access, or oEmbed access tokens.

## Current Behavior

The parser already accepts an Instagram Reel URL as a normal save command. Source detection currently classifies it as `web`, and the extractor has no Instagram-specific path. This means the item can be saved, but the resulting brief may be weak when Instagram hides useful content from public HTML.

## Proposed Behavior

Instagram URLs should become first-class save targets:

- `instagram.com/reel/...` should be classified as Instagram Reel content.
- `instagram.com/p/...` can share the same Instagram source handling for posts.
- Spoofed domains such as `instagram.com.example.com` must remain generic web.
- Extraction should first try Instagram-aware public metadata.
- If useful metadata is not available, the app should still save the item with a minimal title and note-aware summary.

The save response should stay small:

```text
Learning brief: Instagram Reel
**ID:** kb_xxxx
**Tags:** instagram, reel
**Priority:** low
**Summary:** Saved Instagram Reel. No public caption was available.
**Note:** Optional user note when provided.
**Need more?** Reply `details` or add a note.
```

## Architecture

Use the existing ingestion pipeline and add a small Instagram branch:

1. Telegram parser extracts the URL and optional note or priority using existing save command behavior.
2. Source detection classifies Instagram hosts as a dedicated Instagram source.
3. The webpage extractor attempts Instagram-specific metadata extraction before generic HTML body extraction.
4. The AI brief generation receives either extracted metadata plus note, or a fallback content object built from URL and note.
5. Telegram formatters display compact fields with bold labels.

This keeps the feature close to the existing YouTube/X extraction pattern without adding a new service or background workflow.

## Metadata Extraction

The Instagram extraction step should:

- Match real Instagram hosts, including `instagram.com` and `www.instagram.com`.
- Identify Reels from paths beginning with `/reel/`.
- Read public metadata from HTML when available:
  - `<title>`
  - `meta[property="og:title"]`
  - `meta[property="og:description"]`
  - `meta[property="og:image"]`
  - `meta[property="og:video"]`
- Prefer OpenGraph title and description over generic page text.
- Store useful metadata fields for future display or debugging.

If metadata is missing, private, blocked, or too generic, the extractor should return a minimal content object rather than failing the save.

## Fallback UX

The fallback should be clear without being noisy:

- The item saves successfully.
- The summary says the Reel was saved and public caption text was unavailable.
- If the user supplied a note, the note appears in the save response and item details.
- Fallback tags include `instagram` and `reel`.
- The response reminds the user that richer details can come from adding a note or asking for details.

## Error Handling

Network failures, non-2xx responses, blocked pages, malformed metadata, and empty HTML should not block saving. These cases should produce a compact fallback brief and preserve the original URL.

Private/local/unsafe fetch targets must continue to be blocked by the existing safe fetch checks.

## Testing

Add focused tests for:

- Instagram Reel URLs are detected as Instagram.
- Instagram post URLs are detected as Instagram.
- Spoofed Instagram domains are not classified as Instagram.
- Public OpenGraph metadata is converted into extracted content.
- Missing or blocked metadata produces a saveable fallback.
- Notes continue to appear in save responses and details output.
- Compact response labels remain bold for ID, tags, priority, and need-more guidance.

## Acceptance Criteria

- Saving a public Instagram Reel URL creates a knowledge item.
- The source type is Instagram, not generic web.
- Public title or caption metadata is used when available.
- Save still succeeds when metadata is unavailable.
- Notes improve the brief and are visible in Telegram responses.
- The feature does not require Instagram auth, Meta app setup, downloads, or transcription.
