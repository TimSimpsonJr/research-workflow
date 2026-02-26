# Plan: Local File Ingestion Pipeline (`/ingest-local`)

## Overview

Add an end-to-end pipeline for ingesting local files of any format into the Obsidian vault. Mirrors the architecture of the existing `/research` pipeline: Python for I/O, Haiku subagents for extraction and classification, Sonnet orchestrator for synthesis and note writing. **No direct Claude API calls** — all intelligence is subagents managed by the skill, just like `/research`.

---

## Architecture

The key insight: `/research` and `/ingest-local` **converge after the "get markdown" step**. They differ only in the source layer:

```
/research:      topic → Haiku search → fetch_and_clean.py → content_results.json
/ingest-local:  paths → parse_local.py                    → content_results.json
                         ↓ (same shape)                       ↓ (same shape)
                ─────────────────────────────────────────────────────────────
                Tier 1: Haiku subagent — extract structured content
                Tier 2: Haiku subagent — classify into vault structure
                Tier 3: Sonnet orchestrator — write notes + synthesize_folder.py for MOC
```

### What runs where

| Component | Executor | Why |
|-----------|----------|-----|
| File discovery + parsing | Python (`parse_local.py` via Bash) | Needs libraries (pymupdf, mammoth, whisper), no Claude |
| Structured extraction | Haiku subagent (Task tool) | Intelligence, cheap |
| Vault classification | Haiku subagent (Task tool) | Same pattern as `/research`, needs Glob for vault file list |
| Note writing | Sonnet orchestrator (the skill itself) | Needs Write tool, synthesis reasoning |
| MOC generation | Python (`synthesize_folder.py` via Bash) | Already exists, reuse it |

### No direct API calls

`claude_pipe.py` is **not used** by this pipeline. All Claude interactions are subagents spawned via the Task tool, exactly like `/research`. This means:
- Single auth path (Claude Code manages credentials)
- Subagents have tool access (Glob, Read, Write)
- No API key management in Python for this pipeline
- Cost tracking handled by Claude Code

---

## Unified Intermediate Format

`parse_local.py` outputs JSON with the **same shape** as `fetch_and_clean.py`. Downstream tiers don't know or care whether content came from a URL or a local file.

```json
{
  "topic": "batch-2026-02-26-research-papers",
  "source_type": "local",
  "fetched": [
    {
      "url": "file:///home/user/Documents/paper.pdf",
      "source_path": "/home/user/Documents/paper.pdf",
      "title": "Extracted or inferred title",
      "content": "# Title\n\nMarkdown content here...",
      "fetch_method": "pymupdf4llm",
      "cache_hit": false,
      "fetched_at": "2026-02-26T12:00:00Z",
      "word_count": 4500,
      "format": "pdf",
      "chunks": null
    }
  ],
  "failed": [
    {
      "url": "file:///home/user/Documents/corrupt.pdf",
      "source_path": "/home/user/Documents/corrupt.pdf",
      "error": "PyMuPDF: cannot open damaged file",
      "attempts": ["pymupdf4llm"]
    }
  ],
  "stats": {
    "total_files": 25,
    "parsed": 23,
    "failed": 2,
    "cache_hits": 10,
    "total_words": 112000,
    "estimated_tokens": 149000
  }
}
```

Key compatibility points:
- `fetched[]` array with `{url, title, content, word_count}` — same keys as `fetch_and_clean.py`
- `url` field uses `file://` scheme for local files — classify skill sees a URL either way
- `failed[]` array with `{url, error}` — same shape
- Added fields (`source_path`, `format`, `chunks`) are additive, won't break existing consumers

For **large files that need chunking**, the `chunks` field replaces `content`:

```json
{
  "url": "file:///home/user/Books/long-book.epub",
  "title": "A Very Long Book",
  "content": "[chunked — see chunks array]",
  "chunks": [
    { "index": 0, "total": 5, "heading": "Chapter 1", "content": "...", "word_count": 8000 },
    { "index": 1, "total": 5, "heading": "Chapter 2", "content": "...", "word_count": 9200 }
  ],
  "word_count": 45000,
  "format": "epub"
}
```

---

## New Files

### 1. `scripts/parse_local.py` — File discovery + parsing (Tier 0)

**Purpose**: Discover files, convert to markdown, cache results, output `content_results.json`. Pure Python, no Claude API calls.

**CLI interface** (mirrors `fetch_and_clean.py`):
```bash
python parse_local.py --input /path/to/file_or_dir --output .tmp/content_results.json
python parse_local.py --input /path/to/dir --recursive --output .tmp/content_results.json
python parse_local.py --input /path/to/dir --exclude "*.log,*.tmp" --dry-run
```

**Discovery logic**:
- Single file → parse it
- Directory → collect all supported files (non-recursive by default)
- `--recursive` → recurse into subdirectories
- `--exclude` → glob patterns to skip
- Report unsupported file types encountered

**Supported formats and libraries**:

| Format | Library | Notes |
|--------|---------|-------|
| PDF | `pymupdf4llm` (PyMuPDF) | Direct markdown output with headings, bold, lists |
| DOCX | `mammoth` | HTML-to-markdown conversion |
| EPUB | `ebooklib` + `html2text` | Chapter-by-chapter extraction |
| RTF | `striprtf` | RTF-to-text |
| CSV | stdlib `csv` | Markdown table, summary for large files |
| JSON | stdlib `json` | Pretty-print with structure description |
| XML | stdlib `xml.etree` | Text content, structure as headings |
| YAML | `PyYAML` (already a dep) | Pretty-print |
| MD/TXT | passthrough | Normalize frontmatter if present |
| VTT/SRT | reuse `strip_vtt()` from `transcript_processor.py` | Import, don't duplicate |
| Kindle | custom parser | "My Clippings.txt" and Kindle HTML exports |
| Readwise | custom parser | Readwise CSV/JSON export format |
| Audio/Video | `whisper` CLI (local) | Shell out, produce transcript, then passthrough |

**Chunking** (for files producing >100K chars of markdown):
- PDF: chunk by page ranges (e.g., pages 1-20, 21-40)
- EPUB: chunk by chapter
- All others: chunk by heading sections (`## ` boundaries)
- Each chunk carries `{index, total, heading}` metadata

**Caching** (same pattern as `fetch_and_clean.py`):
- Cache dir: `.cache/parse/`
- Cache key: SHA-256 of file content
- Cache entry: JSON with `content_hash` integrity check (same as `fetch_and_clean.py`)
- Invalidation: content hash mismatch (file was modified)
- TTL: no expiry (local files don't change like web pages), but `--no-cache` flag to force re-parse

**Key functions**:
```python
PARSERS: dict[str, Callable] = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".epub": parse_epub,
    # ...registered for extension
}

def discover_files(path: Path, recursive: bool, exclude: list[str]) -> list[Path]
def detect_format(path: Path) -> str  # by extension, magic bytes fallback
def parse_file(path: Path, cache_dir: Path) -> dict  # returns fetched[] entry
def chunk_content(content: str, max_chars: int, format: str) -> list[dict] | None
def process_files(paths: list[Path], cache_dir: Path) -> tuple[list[dict], list[dict]]  # (parsed, failed) — same signature as fetch_and_clean.process_urls
```

Note: `process_files` mirrors `process_urls` from `fetch_and_clean.py` — same return signature, same error handling pattern.

### 2. `scripts/prompts/extract_local.txt` — Extraction prompt (Tier 1)

Prompt for Haiku subagent. Given markdown content from a parsed local file, output structured JSON:

```
Given the following document content, extract and output a JSON object with:
- title: document title (from headings, filename, or inferred)
- author: author/attribution if identifiable, null otherwise
- claims: array of substantive factual assertions (max 10)
- quotes: array of notable verbatim quotes with context (max 5)
- topics: array of 3-5 topic keywords
- entities: { people: [], organizations: [], places: [] }
- summary: 3-5 sentence summary
- suggested_tags: array of 2-4 vault tags
- content_type: one of [reference, argument, narrative, data, correspondence, notes]

Output only the JSON object. No backticks, no narration.
```

### 3. `skills/ingest-local/SKILL.md` — Claude Code skill (Sonnet orchestrator)

**Purpose**: The `/ingest-local` command. Orchestrates the full pipeline.

**Structure** (mirrors `skills/research/SKILL.md`):

```
Step 1: Parse Input
  - Argument is a file path, directory, or glob
  - Validate path exists

Step 2: Run parse_local.py (Tier 0)
  - Write input config to .tmp/ingest_input.json
  - Run: python parse_local.py --input <path> --output .tmp/content_results.json
  - Read content_results.json
  - If all failed, report and stop

Step 3: Cost Estimate + Confirm
  - Calculate estimated tokens from content_results.stats
  - Estimate Haiku cost (extraction + classification) + Sonnet cost (synthesis)
  - Display: "N files, ~X tokens, estimated cost $Y.YY. Proceed?"
  - Wait for user confirmation

Step 4: Extract via Haiku (Tier 1)
  - For each item in fetched[] (batch 5-10 per subagent for efficiency):
    - Spawn Haiku subagent with extract_local.txt prompt + content
    - Collect structured extraction JSON
  - For chunked files: extract each chunk, then merge extractions
  - Write .tmp/extract_results.json

Step 5: Classify via Haiku (Tier 2)
  - Read the generalized classify skill
  - Spawn Haiku subagent with classify skill + extract_results.json
  - Same pattern as /research Step 4
  - Returns: notes_to_create[], vault_context

Step 6: Write Notes (Tier 3)
  - For each entry in notes_to_create[]:
    - Read relevant existing vault files
    - Synthesize note content (the Sonnet orchestrator does this itself)
    - Add frontmatter with source_path reference (not copy, not move)
    - Write to vault at classified path
    - Update MOCs as indicated

Step 7: Synthesize MOC (if multiple files share a theme)
  - Run: python synthesize_folder.py --folder <output_folder> --output <moc_name>.md
  - Reuses existing synthesis, don't rebuild

Step 8: Print Summary
  - Created: [paths]
  - Updated: [paths]
  - MOCs: [paths]
  - Cost: $X.XX actual
  - Warnings: [any failures]
```

### 4. `skills/ingest-classify/SKILL.md` — Generalized vault classifier

**Purpose**: Extended version of `research-classify` that handles any content type, not just web research articles.

**Changes from `research-classify`**:
- Content types expanded: `reference`, `argument`, `narrative`, `data`, `correspondence`, `notes`, `campaign`, `legislation`, `general_research` (original types preserved for backward compatibility)
- Classification uses both the extraction JSON (from Tier 1) AND the vault file list (via Glob) to determine placement
- Same output format as `research-classify` — `notes_to_create[]` + `vault_context`

**Note**: `research-classify` remains unchanged. `/research` continues using it. `/ingest-local` uses `ingest-classify`. If the generalized version proves reliable, `/research` can switch to it later.

### 5. `tests/test_parse_local.py` — Tests for file parser

**Coverage**:
- Format detection (extension-based, with edge cases)
- Per-format parsing (small fixture files in `tests/fixtures/`)
- Chunking logic: boundary detection, metadata, reassembly
- Output JSON shape matches `fetch_and_clean.py` format
- Cache: hit, miss, invalidation on content change
- Discovery: single file, directory, recursive, exclude patterns
- Graceful handling: corrupt files, empty files, unsupported formats
- `process_files` returns same shape as `process_urls`

---

## Modified Files

### 6. `requirements.txt` — New dependencies

```
pymupdf4llm>=0.0.10       # PDF to markdown
mammoth>=1.8.0             # DOCX to markdown
ebooklib>=0.18             # EPUB parsing
html2text>=2024.2.26       # HTML to markdown (for EPUB)
striprtf>=0.0.26           # RTF to text
```

`openai-whisper` is **not** added to requirements. It's a runtime-optional dependency: `parse_local.py` checks if the `whisper` CLI is on PATH. If not, audio/video files are skipped with a clear warning. This avoids dragging PyTorch into the dependency tree for users who don't need transcription.

### 7. `scripts/config.py` template (via `discover_vault.py`)

Add:
```python
PARSE_CACHE_DIR = PROJECT_ROOT / ".cache" / "parse"
SUPPORTED_FORMATS = {".pdf", ".docx", ".epub", ".rtf", ".csv", ".json", ".xml", ".yaml", ".yml", ".md", ".txt", ".vtt", ".srt"}
MAX_CHUNK_CHARS = 100_000
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")
```

### 8. `transcript_processor.py` — Mark as legacy

Add a docstring note:
```python
# Legacy: For new ingestion workflows, use /ingest-local which handles
# audio files via parse_local.py (whisper → markdown → extract → classify → write).
# This script still works for standalone transcript processing.
```

No functional changes. It continues to work for direct CLI usage.

---

## Implementation Order

1. **`parse_local.py` + `test_parse_local.py`** — Foundation. Start with PDF + DOCX + MD/TXT passthrough. Add remaining formats incrementally.
2. **`prompts/extract_local.txt`** — Extraction prompt template.
3. **`skills/ingest-classify/SKILL.md`** — Generalized classifier (extend `research-classify` pattern).
4. **`skills/ingest-local/SKILL.md`** — The orchestrator skill wiring Tiers 0-3.
5. **Config + dependency updates** — `requirements.txt`, `config.py` template, `transcript_processor.py` legacy note.
6. **Integration testing** — End-to-end with sample files of each format.

---

## Design Decisions

**Why no `ingest_local.py` orchestrator script?**
The skill IS the orchestrator, just like `/research`. Adding a Python orchestrator between the skill and the subagents would be a layer that doesn't exist in `/research` and doesn't add value. Python handles I/O (`parse_local.py`), the skill handles intelligence (subagents + synthesis).

**Why a separate `ingest-classify` instead of modifying `research-classify`?**
Risk management. `/research` is working. Changing its classifier could break it. Better to create a generalized variant, prove it works, then optionally migrate `/research` to it later.

**Why `file://` URLs in the unified format?**
The classify skill checks URLs for provenance. Using `file://` scheme means the skill sees a valid URL without special-casing. The `source_path` field carries the real path for frontmatter.

**Why batch extraction subagents (5-10 files per call)?**
One subagent per file = hundreds of sequential Task spawns = slow. One subagent for all files = context overflow. Batching 5-10 small files per Haiku subagent balances throughput with context limits. Large/chunked files get their own subagent.

**Why reuse `synthesize_folder.py` for MOC generation?**
It already does exactly this: collect .md files in a folder, send to Claude, write MOC. Rebuilding it inside the skill would duplicate tested logic. The skill writes individual notes, then calls `synthesize_folder.py` on the output folder.

**Why whisper is not in requirements.txt?**
Adding `openai-whisper` pulls in PyTorch (~2GB). Most users won't need audio transcription. Checking for the `whisper` CLI at runtime and giving a clear skip message is the right trade-off.
