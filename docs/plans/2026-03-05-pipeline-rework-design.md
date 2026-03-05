# Research Pipeline Rework — Design Document

## Problem

The current research pipeline works for single-topic research but falls apart at scale. A 46-county batch research session burned 13% of a Claude Max 20x weekly budget because:

- Sonnet agents dispatched for work Haiku could handle
- No batch mode — each topic ran the full pipeline independently with fixed overhead per agent
- Full article text (5-20K tokens) passed to classify when 500-token summaries would suffice
- Shared context duplicated in every agent prompt instead of referenced from files
- No state persistence — session compaction lost agent IDs and forced re-dispatch
- No media capture — images, PDFs, video content ignored
- Direct Claude API calls via anthropic SDK on top of Claude Max subscription

## Goals

1. Handle large batches (10-100 topics) efficiently with parallel execution and shared context
2. Support thread-pulling — semi-automatic lead discovery from completed research
3. Prioritize primary sources (government docs, court records, FOIA) over news aggregation
4. Preserve source citations end-to-end — every claim traceable
5. Capture inline media (images, PDFs, video transcripts) into the vault
6. Zero paid API calls — all AI work through Claude Code or local Ollama
7. Distribute as a Claude Code plugin — portable, vault-agnostic, layered infrastructure

## Architecture

### Three Modes, One Entry Point

| Mode | Trigger | What happens |
|------|---------|-------------|
| Single | `/research "topic"` | Full pipeline, one topic |
| Batch | `/research "natural language describing multiple topics"` | Resolver parses prompt → plan approval → parallel execution |
| Thread-pull | `/research "topic" --from vault:"path/to/note.md"` | Reads note, extracts leads, proposes threads → approval → batch |

All three modes converge after the resolver — they all produce a plan (topic list + shared context + priorities) that flows through the same executor.

Local file paths in the prompt are auto-detected. If the resolver finds a path to a folder of PDFs alongside a topic, it merges local extraction with web search — no special syntax needed.

### Pipeline Stages

```
1. RESOLVE    — Parse input, read vault context, produce plan → human approval
2. SEARCH     — Find URLs per topic (WebSearch or SearXNG)
3. FETCH      — Download + cache content (Jina Reader, Python)
4. MEDIA      — Download inline images/PDFs/docs/video to vault assets
5. SUMMARIZE  — Distill each article to ~500 tokens (Ollama or Haiku subagent)
6. CLASSIFY   — Map to vault structure, tags, links (Ollama or Haiku subagent)
7. WRITE      — Synthesize final notes (Sonnet or Opus, sequential, vault-aware)
8. DISCOVER   — Scan results for leads, propose threads → optional next batch
```

Local file ingestion (PDFs, .docx, audio) replaces stages 2-3 with an EXTRACT step and joins the pipeline at stage 4.

### Tiered Infrastructure

The plugin auto-detects available infrastructure and uses the best option:

| Layer | Base (zero setup) | Mid (+ Ollama) | Full (+ Ollama + SearXNG) |
|-------|-------------------|-----------------|---------------------------|
| Search | WebSearch (Claude Code) | WebSearch | SearXNG + WebSearch |
| Summarize | Haiku subagent | Ollama (local) | Ollama (local) |
| Classify | Haiku subagent | Ollama (local) | Ollama (local) |
| Fetch/cache | Python (Jina) | Python (Jina) | Python (Jina) |
| Media download | Python | Python | Python |
| Video transcription | Whisper (local) | Whisper (local) | Whisper (local) |
| Analysis/write | Sonnet/Opus (Claude Code) | Sonnet/Opus (Claude Code) | Sonnet/Opus (Claude Code) |

Each tier is a strict superset. The plugin detects capabilities at startup.

### Write Stage Model Selection

| Note type | Model | When |
|-----------|-------|------|
| Standard (primary, secondary, scan) | Sonnet | Default for all research notes |
| Synthesis (cross-batch summary, MOC, strategic assessment) | Opus | Auto-selected when classify assigns `type: synthesis` |
| User override | Either | User can escalate any note to Opus in plan approval |

## Plugin Structure

```
research-workflow/
├── plugin.json                    # Plugin manifest
├── README.md                      # Setup guide + tier explanations
├── requirements.txt               # Python deps (minimal for base tier)
│
├── skills/
│   ├── research/SKILL.md          # Main entry point — all three modes
│   └── research-setup/SKILL.md    # First-run setup wizard
│
├── agents/
│   ├── topic-resolver.md          # NL prompt → structured plan
│   ├── search-agent.md            # Haiku — web search per topic
│   ├── classify-agent.md          # Haiku — vault mapping + tags
│   └── thread-discoverer.md       # Haiku — extract leads from results
│
├── scripts/
│   ├── fetch_and_clean.py         # Jina fetch + cache (parallel, async)
│   ├── fetch_media.py             # Download images/PDFs/video
│   ├── extract_local.py           # .pdf/.docx/.doc/.mp3 text extraction
│   ├── summarize.py               # Ollama or file-based summarize
│   ├── vault_index.py             # SQLite FTS5 vault index
│   ├── vault_lint.py              # Frontmatter validation (post-write)
│   ├── find_broken_links.py       # Dangling wikilink detection (post-write)
│   ├── state.py                   # Checkpoint read/write
│   ├── detect_tier.py             # Check for Ollama, SearXNG, hardware
│   ├── config.py                  # Auto-generated by setup wizard
│   └── utils.py                   # Shared helpers
│
├── scripts/prompts/
│   ├── vault_rules.txt            # Generated during setup from vault conventions
│   ├── summarize_fetch.txt        # Summarization prompt template
│   └── output_formats/            # produce_output templates (blog, briefing, etc.)
│
├── docker/
│   ├── docker-compose.yml         # Optional SearXNG
│   └── searxng/settings.yml       # SearXNG engine config
│
├── template-vault/                # Starter vault for new users
│   ├── Inbox/
│   ├── Projects/
│   │   └── Example Topic/
│   │       └── _MOC.md
│   ├── Resources/
│   ├── Meta/
│   │   └── Tags.md
│   ├── assets/
│   └── .research-workflow/
│       └── config.json
│
└── tests/
```

### What's Removed

- `claude_pipe.py` — no more direct API calls. AI work routes through Claude Code agents or Ollama.
- `ingest.py` / `ingest_batch.py` — absorbed into fetch stage. Raw ingestion = running stages 3-4 only.
- `synthesize_folder.py` — absorbed into write stage as `type: synthesis` notes.
- `find_related.py` — replaced by vault index FTS5 queries.
- `daily_digest.py` — dropped. Out of scope for a research plugin.
- `discover_vault.py` — replaced by `research-setup` skill (interactive wizard).

### What's Kept and Integrated

- `produce_output.py` — note → blog post, briefing, video script, etc. Post-research step.
- `vault_lint.py` — runs automatically after write stage as a quality gate.
- `find_broken_links.py` — runs after write stage to catch dangling wikilinks.
- `transcript_processor.py` — reworked to route through Ollama/Claude Code instead of claude_pipe.

## Stage Details

### Stage 1: RESOLVE

The topic resolver agent (Sonnet) parses natural language input and produces a structured plan.

**Inputs it handles:**
- Pure topic string → single web research
- Natural language describing multiple topics → batch with tiers/priorities
- Reference to vault note → thread-pull (extract leads, propose for approval)
- File path in prompt → local extraction mode (skip search + fetch)
- Mix of the above → merged pipeline

**Output: `research_plan.json`**
```json
{
  "project": "SC County ALPR Research",
  "shared_context_files": ["Projects/Surveillance/SC ALPR Overview.md"],
  "topics": [
    {"topic": "Greenville County ALPR", "tier": 1, "priority": "deep"},
    {"topic": "Abbeville County ALPR", "tier": 3, "priority": "scan"}
  ],
  "local_sources": [],
  "execution_order": "tier_1_first",
  "estimated_usage": {
    "search_agents": 46,
    "summarize_calls": 250,
    "classify_agents": 1,
    "write_messages": "46 Sonnet + 1 Opus",
    "total_claude_messages": "~95"
  }
}
```

**Always presented for human approval before execution.** User can edit topics, change tiers, remove items, escalate write models.

### Stage 2: SEARCH

Per-topic web search, dispatched in parallel.

**Base tier:** Haiku subagents use WebSearch tool. Prompt prioritizes primary sources (`.gov`, `.edu`, court records, official reports).

**Full tier:** Python queries SearXNG. Source quality scoring:
- Primary (government, court, FOIA, official reports): score 3
- Secondary (investigative journalism, academic): score 2
- Tertiary (aggregation, blog posts, listicles): score 1

Top 5-7 URLs per topic, primary sources first.

**Batch optimization:** Topics sharing a domain reuse statewide/shared sources already found.

Output: `state/search_results.json`

### Stage 3: FETCH

Python script. Parallel async with rate limiting (3 concurrent, 1s delay between bursts).

- Cache: SHA-256(url) key, 7-day TTL, integrity checks
- Fallback: Jina Reader → Wayback Machine
- SSRF protection: private IP blocking, fail-closed on DNS errors
- Content cap: 50K chars per URL

Output: `state/fetch_results.json`

### Stage 3-alt: EXTRACT (local files)

When the resolver detects file paths, replaces stages 2-3.

| Format | Backend |
|--------|---------|
| .pdf | pymupdf |
| .docx | python-docx |
| .doc | python-docx → LibreOffice → win32com (fallback chain) |
| .mp3/.mp4/.webm | yt-dlp (audio extract) → Whisper (transcribe) |

Original files copied to vault `assets/`. Output in same format as fetch_results.

### Stage 4: MEDIA

Python script scans fetched content for inline media.

**Allowed types:**
- Images: `.png`, `.jpg`, `.jpeg`, `.gif`, `.svg`, `.webp`
- Documents: `.pdf`
- Video/audio: YouTube, Vimeo URLs, `.mp4`, `.webm`, `.mp3`

**Video handling:**
- `yt-dlp` extracts audio stream only (no full video download)
- Whisper transcribes audio → text
- Thumbnail grabbed and stored in assets
- Transcript feeds into summarize stage
- Original URL preserved as source

**Constraints:**
- Size cap: 10MB per file (images/docs), 100MB per audio/video. Configurable.
- Files larger than cap are logged but not downloaded
- Source tracking: `.meta` sidecar JSON per downloaded file (source URL, timestamp, run ID, size, content type)
- Downloads stored in `{vault}/assets/{topic-slug}/`

**yt-dlp and Whisper:** Detected/installed during setup, same pattern as Ollama. Auto on Linux/Mac, guided on Windows.

Output: `state/media_manifest.json`

### Stage 5: SUMMARIZE

Distills each article from 5-20K tokens to ~500 tokens.

**With Ollama:** `summarize.py` sends articles to local model. Parallel.
**Without Ollama:** Haiku subagent via Task tool.

**Output per article:**
```json
{
  "url": "https://...",
  "title": "...",
  "summary": "~500 token distillation",
  "source_type": "government|journalism|academic|advocacy|other",
  "key_entities": ["SLED", "Flock Safety", "H.3456"],
  "key_claims": ["422M plate reads in 2024"],
  "media_refs": ["assets/greenville-alpr/alpr-report.pdf"]
}
```

Full article text preserved in fetch cache — write stage can request it for direct quotes.

Output: `state/summaries.json`

### Stage 6: CLASSIFY

Maps summaries to vault structure using the SQLite FTS5 index.

**With Ollama:** `classify.py` sends summaries + relevant index results to local model.
**Without Ollama:** Haiku subagent.

**Batch optimization:** All summaries from a batch classified in one pass for consistent folder placement and tagging.

**Output per note:**
```json
{
  "title": "Greenville County ALPR Surveillance",
  "folder": "Projects/Surveillance/South Carolina/",
  "action": "create",
  "type": "research",
  "write_model": "sonnet",
  "tags": ["research", "surveillance", "greenville-sc"],
  "links": ["[[SC ALPR Overview]]", "[[Flock Safety]]"],
  "stub_links": ["[[SLED Plate Reader Program]]"],
  "sources": ["url1", "url2"],
  "media": ["assets/greenville-alpr/alpr-report.pdf"],
  "priority": "primary"
}
```

Notes classified as `type: synthesis` automatically get `write_model: opus`.

Output: `state/classification.json`

### Stage 7: WRITE

Sonnet (or Opus for synthesis) writes final notes through Claude Code. Always Claude Code, never Ollama.

**Sequential within tiers.** Tier 1 notes write first so lower tiers can cross-reference them. Each note's Sonnet prompt receives only:
- Summaries for this note's sources
- Classification for this note
- Shared context files (read from disk, not duplicated in prompt)
- Previously written notes from this batch (for cross-referencing)
- Vault rules

**Before writing each note:** Check target file mtime against classification timestamp. If newer (Obsidian or another process modified it), re-read and merge instead of overwriting.

**Post-write quality checks:**
- `vault_lint.py` validates frontmatter conventions
- `find_broken_links.py` catches dangling wikilinks
- Violations reported in final summary

Output: `state/written_notes.json` (appended per note for crash recovery)

### Stage 8: DISCOVER

Haiku agent (or Ollama) scans batch results for research leads.

**Scoring criteria:**
- Frequency — entity mentioned across multiple sources
- Novelty — not already in vault (checked via index)
- Connectedness — relates to multiple existing vault notes
- Specificity — named bill, org, or person > vague concept

**Presented to user:**
```
Threads discovered from SC County ALPR research:
  1. Flock Safety federal data sharing (score: 9)
  2. SLED plate reader program (score: 8)
  3. SC Bill H.3456 (score: 7)
  4. Motorola Solutions ALPR products (score: 4)

Research any of these? [1,2,3] / all / none
```

Approved threads feed back into Stage 1 as a new batch with completed research as shared context.

Output: `state/threads.json`

## Vault Index

SQLite FTS5 database at `{vault}/.research-workflow/vault_index.db`.

```sql
notes:
  path    TEXT PRIMARY KEY
  title   TEXT
  tags    TEXT
  excerpt TEXT  (first 500 chars)
  mtime   REAL

notes_fts (FTS5 virtual table over title, tags, excerpt)
```

- Built during setup, updated incrementally before each run (mtime check)
- ~2KB per note, 1000-note vault = ~2MB
- Replaces glob-all-markdown pattern, find_related.py keyword extraction
- Used by classify, thread-discover, write (cross-reference lookup)

## Vault-Agnostic Configuration

Config lives in the vault at `{vault}/.research-workflow/config.json`:

```json
{
  "vault_root": "/path/to/vault",
  "inbox": "Inbox",
  "assets": "assets",
  "moc_pattern": "^_|MOC|Index|Hub",
  "tag_format": "list",
  "date_format": "%Y-%m-%d",
  "frontmatter_fields": ["title", "tags", "source", "created"],
  "ollama_enabled": true,
  "ollama_model": "qwen2.5:14b",
  "ollama_benchmark_ms": 3200,
  "searxng_url": null,
  "whisper_available": true,
  "ytdlp_available": true,
  "tier": "mid"
}
```

`vault_rules.txt` also generated during setup based on detected vault conventions.

Setup wizard (`/research-setup`):
1. Locate vault (user provides or scan common locations)
2. Scan vault conventions (folders, tags, frontmatter, MOC patterns)
3. Detect/install Ollama (hardware-aware recommendation, auto-install on Linux/Mac, guided on Windows)
4. Detect/install yt-dlp, Whisper (same pattern)
5. Detect SearXNG
6. Generate config + vault_rules
7. Build vault index
8. Offer template vault for new Obsidian users

### Ollama Hardware Recommendations

| Hardware | Recommendation | Model |
|----------|---------------|-------|
| <8GB RAM, no GPU | Don't use Ollama — base tier | N/A |
| 8-16GB RAM, no GPU | Small model, expect slow | qwen2.5:7b or llama3.1:8b |
| 16GB+ RAM or 6-8GB VRAM | Good fit | qwen2.5:14b or llama3.1:8b |
| 12GB+ VRAM | Strong fit | qwen2.5:32b or llama3.1:70b (q4) |

Setup runs a quick benchmark (summarize a short paragraph). If >30s, warns user and suggests base tier.

## State Management

State directory: `{vault}/.research-workflow/state/`

**`current_run.json` tracks position:**
```json
{
  "run_id": "2026-03-05-sc-alpr",
  "started_at": "2026-03-05T14:30:00",
  "stage": "write",
  "stage_progress": {"total_notes": 46, "completed": 23, "current": "Lexington County ALPR"},
  "tier_detected": "mid",
  "plan_approved": true
}
```

Each stage writes output atomically (temp file → rename). Stage 7 appends per-note for granular recovery.

**Recovery on re-entry:**
```
Incomplete run detected: "SC County ALPR Research"
Stage: write (23/46 notes completed)
Resume / Restart / Abandon?
```

`current_run.json` also acts as a concurrency lock — one run at a time per machine. Stale runs (>24h) flagged for cleanup.

Completed runs archived to `state/history/{run-id}/`.

## Error Handling

**Keep going, report at end.** Partial failures (failed fetches, Ollama timeouts, missing media) don't stop the pipeline. Failures are collected and reported in the final summary:

```
Run complete: SC County ALPR Research
  43/46 notes written
  12 sources failed to fetch (see state/failures.json)
  3 notes have <2 sources (flagged for review)
  2 media files exceeded size cap (logged, not downloaded)
```

## Media Safety

**Allowed types:** Images (.png, .jpg, .jpeg, .gif, .svg, .webp), documents (.pdf), video/audio (YouTube, Vimeo, .mp4, .webm, .mp3 — extracted to audio, transcribed via Whisper).

**Blocked:** All other types (.exe, .zip, .docx from unknown URLs).

**Size caps:** 10MB images/docs, 100MB audio/video. Configurable.

**Source tracking:** Every downloaded file gets a `.meta` sidecar JSON with source URL, timestamp, run ID, size, content type.

**No execution:** Files stored and linked, never opened or processed beyond transcription.

## Migration

- Rename `Areas/` → `Projects/` in vault, update all wikilinks and references
- Run `/research-setup` to generate new config (replaces old config.py + .env)
- Old `.cache/fetch/` carries forward (same format)
- Delete old `.tmp/` state files (incompatible)
- One-time step, not blocking

## Cost Estimation

Shown in plan approval before execution:

```
Estimated usage:
  Search:    46 Haiku subagents
  Summarize: ~250 Ollama calls (local, free)
  Classify:  1 Haiku subagent
  Write:     46 Sonnet messages + 1 Opus synthesis
  Total:     ~95 Claude Code messages
```
