# 3-Tier Research Pipeline Design

**Date:** 2026-02-25
**Status:** Approved
**Author:** Design session with Claude

---

## Overview

Redesign the research pipeline to reduce token costs and improve reliability by splitting the existing `research-haiku` skill into three tiers with clear responsibilities:

1. **Haiku search agent** — queries the web and selects the best URLs
2. **Python fetch/clean/cache layer** — fetches, cleans, and caches content via Jina Reader
3. **Haiku classify agent** — classifies content and maps it to vault structure
4. **Sonnet write agent** — writes final notes (unchanged)

Additionally, update existing post-research scripts to use Sonnet instead of Opus.

---

## Motivation

- **Token cost reduction**: Haiku is ~12x cheaper than Sonnet and ~80x cheaper than Opus for I/O-heavy tasks. Fetching and classifying content is well within Haiku's capabilities.
- **Caching savings**: Python caches fetched content (7-day TTL) so re-researching the same URLs does not make repeat API calls to Jina Reader.
- **Reliability**: Python handles all network I/O deterministically, avoiding LLM tool-call flakiness and retry overhead.
- **Separation of concerns**: Each tier has a single clear job, making the pipeline easier to debug and improve.

---

## Architecture

```
INPUT: topic string(s) OR known URL(s)
         │
         ▼
┌─────────────────────┐
│  research skill     │  (orchestrator — modified)
│  (Sonnet)           │  Routes: known_urls → skip search
└──────┬──────────────┘
       │
       ├─── known_urls path ─────────────────────────────────┐
       │                                                       │
       ▼                                                       │
┌─────────────────────┐                                        │
│  research-search    │  TIER 1                                │
│  (Haiku agent)      │  - Web search via WebSearch/WebFetch  │
│                     │  - Evaluates relevance, selects URLs  │
│                     │  - Output: search_context JSON        │
└──────┬──────────────┘                                        │
       │                                                       │
       └──────────────── merge ◄─────────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │  fetch_and_clean.py     │  TIER 2
              │  (Python subprocess)    │  - Jina Reader fetch + clean
              │                         │  - MD5 cache (7-day TTL)
              │                         │  - Wayback Machine fallback
              │                         │  - URL deduplication
              │                         │  - Output: fetch_results JSON
              └──────────┬──────────────┘
                         │
                         ▼
              ┌─────────────────────────┐
              │  research-classify      │  TIER 3
              │  (Haiku agent)          │  - Reads cleaned markdown content
              │                         │  - Maps to vault structure
              │                         │  - Tags, links, placement
              │                         │  - Output: classification JSON
              └──────────┬──────────────┘
                         │
                         ▼
              ┌─────────────────────────┐
              │  Sonnet write           │  UNCHANGED
              │  (main research skill)  │  - Writes final vault notes
              └─────────────────────────┘
```

---

## JSON Schemas

### Tier 1 Output: `search_context.json`

Produced by `research-search` skill, consumed by `fetch_and_clean.py` and passed through to `research-classify`.

```json
{
  "topic": "string — original research topic",
  "query_used": "string — actual search query sent to web",
  "selected_urls": [
    {
      "url": "string",
      "title": "string",
      "snippet": "string — brief description of relevance",
      "relevance_score": "number 1-10",
      "reason": "string — why this URL was chosen"
    }
  ],
  "rejected_urls": [
    {
      "url": "string",
      "reason": "string — why this URL was skipped"
    }
  ],
  "search_notes": "string — any observations about the search landscape"
}
```

### Tier 2 Output: `fetch_results.json`

Produced by `fetch_and_clean.py`, consumed by `research-classify`.

```json
{
  "topic": "string — passed through from search_context",
  "search_context": { "...": "full search_context object passed through" },
  "fetched": [
    {
      "url": "string",
      "title": "string",
      "content": "string — cleaned markdown content",
      "fetch_method": "jina | wayback | cached",
      "cache_hit": "boolean",
      "fetched_at": "ISO timestamp",
      "word_count": "number"
    }
  ],
  "failed": [
    {
      "url": "string",
      "error": "string",
      "attempts": ["jina", "wayback"]
    }
  ],
  "stats": {
    "total_urls": "number",
    "fetched": "number",
    "failed": "number",
    "cache_hits": "number",
    "total_words": "number"
  }
}
```

### Tier 3 Output: `classification.json`

Produced by `research-classify` skill, consumed by the `research` orchestrator to guide Sonnet note writing.

```json
{
  "topic": "string",
  "search_context": { "...": "passed through" },
  "notes_to_create": [
    {
      "title": "string — proposed note title",
      "filename": "string — suggested filename (no path)",
      "folder": "string — vault subfolder e.g. Research/",
      "content_summary": "string — what this note should contain",
      "source_urls": ["url1", "url2"],
      "suggested_tags": ["tag1", "tag2"],
      "suggested_links": ["[[Existing Note Title]]"],
      "stub_links": ["[[Topic Worth Researching Later]]"],
      "priority": "primary | supporting | stub-only"
    }
  ],
  "vault_context": {
    "existing_notes_found": ["list of relevant existing notes discovered"],
    "suggested_moc_update": "string — which MOC to update if any"
  }
}
```

---

## Component Specifications

### New File: `fetch_and_clean.py`

**Location:** `C:\Users\tim\OneDrive\Documents\Projects\research-workflow\fetch_and_clean.py`

**Responsibilities:**
- Accept a `search_context.json` file path as input (or stdin JSON)
- Fetch each URL via Jina Reader API (`https://r.jina.ai/{url}`)
- Fall back to Wayback Machine (`https://archive.org/wayback/available?url={url}`) if Jina fails
- Cache responses by MD5 hash of URL, stored in `.cache/fetch/` directory
- 7-day TTL: re-fetch if cache entry is older than 7 days
- Deduplicate URLs before fetching (case-insensitive, strip trailing slashes)
- Truncate content at 50,000 characters per URL
- Output `fetch_results.json` to stdout or specified output path

**CLI interface:**
```
fetch_and_clean.py --input search_context.json [--output fetch_results.json] [--cache-dir .cache/fetch] [--ttl-days 7] [--dry-run]
```

**Cache structure:**
```
.cache/
  fetch/
    {md5_of_url}.json    ← { url, content, fetched_at, title }
```

**Error handling:**
- If both Jina and Wayback fail, add to `failed` list and continue
- Never raise an exception that halts the pipeline; always produce valid JSON output
- Log fetch status to stderr

**Environment variable:** `JINA_API_KEY` (optional — Jina Reader works without key at rate-limited tier)

**Tests:** Add to `tests/test_fetch_and_clean.py`
- Test cache hit (mock filesystem)
- Test cache miss triggers fetch
- Test TTL expiry triggers re-fetch
- Test Jina failure falls back to Wayback
- Test both fail → appears in `failed` list
- Test URL deduplication
- Test content truncation at 50K chars

---

### Modified Skill: `research` (orchestrator)

**Location:** `C:\Users\tim\.claude\skills\research\SKILL.md`

**Changes needed:**
1. Add routing logic: if input contains known URLs, skip `research-search` tier
2. After `research-search` (or for known URLs), invoke `fetch_and_clean.py` as subprocess
3. Pass `fetch_results.json` to `research-classify` skill
4. Pass `classification.json` to Sonnet note-writing step (unchanged)

**Known URLs path:**
- Build a minimal `search_context.json` with the provided URLs (no search query, empty `selected_urls` relevance metadata)
- Continue directly to `fetch_and_clean.py`

---

### New Skill: `research-search`

**Location:** `C:\Users\tim\.claude\skills\research-search\SKILL.md`

**Replaces:** The search/URL selection portion of `research-haiku`

**Responsibilities:**
- Accept a topic string
- Perform web search using `WebSearch` tool
- Evaluate up to 10 URLs for relevance using `WebFetch` for snippets
- Select 3-7 best URLs
- Reject clearly irrelevant URLs with reasoning
- Output `search_context.json` to stdout

**Model:** Haiku (specified in skill invocation)

---

### New Skill: `research-classify`

**Location:** `C:\Users\tim\.claude\skills\research-classify\SKILL.md`

**Replaces:** The classification/vault-mapping portion of `research-haiku`

**Responsibilities:**
- Accept `fetch_results.json` as input (contains cleaned content + search context)
- Read vault structure via `discover_vault.py` output or direct vault scanning
- For each fetched URL's content, determine:
  - What note(s) to create
  - Which vault folder they belong in
  - What tags and wikilinks are appropriate
  - Whether existing notes should be updated vs. new notes created
- Output `classification.json` to stdout

**Model:** Haiku (specified in skill invocation)

---

### Deprecated: `research-haiku`

**Location:** `C:\Users\tim\.claude\skills\research-haiku\SKILL.md`

**Action:** Keep file but add deprecation notice at top pointing to `research-search` and `research-classify`. Do not delete — preserves git history and allows rollback.

---

## Post-Research Toolkit Modifications

These changes are independent of the 3-tier pipeline redesign but were requested in the same session.

### `synthesize_folder.py`

**Change:** Replace `claude-opus-*` model with `claude-sonnet-*` (latest Sonnet model)
**Reason:** Sonnet is sufficient for synthesis tasks and significantly cheaper

### `produce_output.py`

**Change 1:** Replace `claude-opus-*` model with `claude-sonnet-*` (latest Sonnet model)
**Reason:** Same as above

**Change 2:** Only prepend date to filename for `daily-digest` format
- **Before:** `{date}-{slug}-{format}.md` for all formats
- **After:** `{date}-{slug}-daily-digest.md` for daily digest; `{slug}-{format}.md` for all other formats
**Reason:** Date-stamped filenames are appropriate for diary-like digests but not for evergreen content formats (articles, scripts, briefings, etc.)

---

## Vault CLAUDE.md Addition

Add a new section to `C:\Users\tim\OneDrive\Documents\Tim's Vault\CLAUDE.md` documenting the research workflow scripts:

```markdown
## Research Workflow Scripts

Scripts live in `C:\Users\tim\OneDrive\Documents\Projects\research-workflow\`.
Python: `C:\Users\tim\AppData\Local\Programs\Python\Python312\python.exe`

### Research Pipeline (use via research skill — these run automatically)
- `fetch_and_clean.py` — Fetches URLs via Jina Reader, caches results, cleans to markdown
- See skills: `research-search`, `research-classify`

### Post-Research Toolkit (invoke manually)
- `synthesize_folder.py --folder PATH --output FILENAME` — Synthesize a folder of notes into a MOC/overview
- `produce_output.py --file NOTE --format FORMAT` — Transform a note into web article, video script, briefing, etc.
- `daily_digest.py` — Generate a daily digest of vault activity
- `find_related.py --note NOTE` — Find semantically related notes
- `find_broken_links.py` — Audit vault for broken wikilinks
- `vault_lint.py` — Check notes for formatting/tagging issues
- `discover_vault.py` — Generate vault structure map (used internally)
```

---

## Out of Scope

The following are **not** changed by this design:
- Sonnet note-writing step (unchanged)
- `ingest.py` / `ingest_batch.py` (URL ingestion pipeline — separate system)
- `transcript_processor.py` (audio/video transcript handling)
- `daily_digest.py` (daily digest generation)
- `find_broken_links.py`, `find_related.py`, `vault_lint.py`, `discover_vault.py`
- Test suite structure (new tests added for `fetch_and_clean.py` only)

---

## Implementation Order

1. Modify `synthesize_folder.py` and `produce_output.py` (model + filename changes) — quick wins, no dependencies
2. Create `fetch_and_clean.py` with tests
3. Create `research-search` skill
4. Create `research-classify` skill
5. Modify `research` orchestrator skill
6. Add deprecation notice to `research-haiku`
7. Update vault `CLAUDE.md`
