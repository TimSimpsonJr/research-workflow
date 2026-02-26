# Plan: Local File Ingestion Pipeline (`/ingest-local`)

## Overview

Add an end-to-end pipeline for ingesting local files of any format into the Obsidian vault. Mirrors the architecture of the existing `/research` pipeline but replaces URL fetching with local file parsing. Invoked as a Claude Code skill.

---

## Architecture

```
/ingest-local ~/Documents/research-dump/

Tier 0: Parse (Python, no API)
  → Convert any file format to markdown text
  → Chunk large files to stay within token limits
  → Cache parsed results by file hash

Tier 1: Extract (Haiku)
  → Structured extraction per file: claims, key points, quotes, entities, metadata
  → Batched — multiple small files per API call where possible

Tier 2: Classify (Haiku)
  → Reuse existing research-classify skill pattern
  → Determine folder, tags, wikilinks, MOC updates

Tier 3: Synthesize (Sonnet)
  → Cross-reference extracted content across files
  → Write final vault notes with wikilinks, tags, frontmatter
  → Generate MOC if multiple files share a theme
```

---

## New Files

### 1. `scripts/parse_file.py` — Format-agnostic file parser (Tier 0)

**Purpose**: Convert any supported file to markdown text. No API calls. Pure Python.

**Supported formats and libraries**:

| Format | Library | Notes |
|--------|---------|-------|
| PDF | `pymupdf4llm` (PyMuPDF) | Best markdown output for PDFs. Falls back to `pdfplumber` for scanned/image PDFs |
| DOCX | `mammoth` | Clean HTML-to-markdown conversion |
| EPUB | `ebooklib` + `html2text` | Chapter-by-chapter extraction |
| RTF | `striprtf` | Lightweight RTF-to-text |
| CSV | stdlib `csv` | Convert to markdown table, with summary row for large files |
| JSON | stdlib `json` | Pretty-print with structure description |
| XML | stdlib `xml.etree` | Extract text content, preserve structure as headings |
| YAML | `PyYAML` (already a dep) | Pretty-print |
| Markdown/TXT | passthrough | Normalize frontmatter if present |
| VTT/SRT | existing `strip_vtt()` | Reuse from `transcript_processor.py` |
| Kindle highlights | custom parser | Parse "My Clippings.txt" or Kindle HTML exports |
| Readwise exports | custom parser | Parse Readwise CSV/JSON export format |
| Audio/Video | `whisper` (OpenAI) via CLI | Shell out to `whisper` binary, produce transcript, then parse |

**Chunking strategy**:
- Files producing > 100K chars of markdown get split into chunks
- Chunk at natural boundaries: page breaks (PDF), chapters (EPUB), sections (headings in any format)
- Each chunk is processed independently through Tier 1, then reassembled for Tier 2+
- Chunk metadata (position, total chunks) preserved for reassembly

**Caching**:
- Cache parsed markdown by SHA-256(file content) in `.cache/parse/`
- Same cache structure as `fetch_and_clean.py` (JSON with content_hash integrity check)
- Cache invalidated if source file is modified (mtime check + hash verify)

**Key functions**:
- `detect_format(path: Path) -> str` — identify file type by extension + magic bytes
- `parse_file(path: Path) -> ParseResult` — main entry point, returns dataclass with `{content, title, metadata, format, chunks[]}`
- `parse_pdf(path)`, `parse_docx(path)`, `parse_epub(path)`, etc. — format-specific parsers
- `chunk_content(content: str, max_chars: int) -> list[Chunk]` — split at natural boundaries
- Per-format parsers registered in a `PARSERS` dict for easy extension

### 2. `scripts/ingest_local.py` — Batch orchestrator (CLI entry point)

**Purpose**: Collect files, estimate costs, run the 4-tier pipeline, track progress.

**Input modes** (determined by argument type):
- Single file: `python ingest_local.py /path/to/file.pdf`
- Directory: `python ingest_local.py /path/to/folder/`
- Directory + recursive: `python ingest_local.py /path/to/folder/ --recursive`
- Glob pattern: `python ingest_local.py "/path/to/*.pdf"`

**Processing flow**:
1. **Discover** — collect all files, filter by supported formats, report unsupported
2. **Parse** — run Tier 0 on each file (parallelizable, no API calls)
3. **Estimate** — calculate token counts, estimate API costs for Tier 1-3, display summary
4. **Confirm** — prompt user to proceed (skippable with `--confirm`)
5. **Extract** — run Tier 1 (Haiku) on each parsed file/chunk
6. **Classify** — run Tier 2 (Haiku) on all extracted content
7. **Synthesize** — run Tier 3 (Sonnet) to write final vault notes
8. **Report** — summary of created/updated notes, costs incurred

**Progress & resumability**:
- State file: `.tmp/ingest_state.json` tracking status per file
- States: `pending → parsed → extracted → classified → written`
- On re-run with `--resume`, skip files already in later states
- Progress bar via `rich.progress`

**CLI flags**:
- `--recursive` — recurse into subdirectories
- `--confirm` — skip cost confirmation prompt
- `--resume` — resume interrupted batch from state file
- `--dry-run` — parse only, show what would be processed
- `--depth ingest|extract|synthesize` — stop at a specific tier (future flexibility even though default is full)
- `--exclude "*.log,*.tmp"` — glob patterns to skip

### 3. `scripts/prompts/extract_local.txt` — Extraction prompt (Tier 1)

**Purpose**: Prompt template for Haiku to extract structured content from a parsed local file.

**Outputs per file**:
- Title (extracted or inferred)
- Author / source attribution
- Key claims / assertions
- Notable quotes
- Topics / themes (3-5 keywords)
- Entities (people, organizations, places)
- Summary (3-5 sentences)
- Suggested tags (2-4)
- Source file metadata (format, page count, word count)

Similar to `extract_transcript.txt` but generalized for any content type.

### 4. `scripts/prompts/synthesize_local_batch.txt` — Cross-file synthesis prompt (Tier 3)

**Purpose**: Prompt template for Sonnet to synthesize across multiple extracted files.

**Outputs**:
- Thematic groupings of files
- Cross-references and connections between files
- Per-group MOC structure
- Per-file vault note content with wikilinks to related notes

### 5. `skills/ingest-local/SKILL.md` — Claude Code skill definition

**Purpose**: The `/ingest-local` command that orchestrates the pipeline from within Claude Code.

**Pattern**: Mirrors `skills/research/SKILL.md` structure:
- Model check (expects Sonnet)
- Parse input (file path, directory, or glob)
- Spawn Haiku agents for extraction and classification
- Run Python scripts for parsing
- Sonnet writes final notes
- Print summary

**Invocation examples**:
```
/ingest-local ~/Documents/research-papers/
/ingest-local ~/Downloads/important-report.pdf
/ingest-local ~/Kindle/My Clippings.txt
/ingest-local ~/interviews/recording.mp3
```

### 6. `tests/test_parse_file.py` — Tests for file parser

**Coverage**:
- Format detection for each supported type
- Parsing correctness for each format (with small fixture files)
- Chunking logic (boundary detection, reassembly)
- Cache hit/miss/invalidation
- Graceful handling of corrupt or empty files
- Unsupported format error messages

### 7. `tests/test_ingest_local.py` — Tests for batch orchestrator

**Coverage**:
- File discovery (single file, directory, recursive, glob)
- Cost estimation calculation
- State file creation and resume logic
- Progress tracking
- Exclude pattern filtering

---

## Modified Files

### 8. `requirements.txt` — New dependencies

Add:
```
pymupdf4llm>=0.0.10       # PDF to markdown (PyMuPDF-based)
mammoth>=1.8.0             # DOCX to markdown
ebooklib>=0.18             # EPUB parsing
html2text>=2024.2.26       # HTML to markdown (for EPUB chapters)
striprtf>=0.0.26           # RTF to text
openai-whisper>=20231117   # Audio/video transcription (optional)
```

Note: `whisper` is optional — if not installed, audio/video files are skipped with a warning. The parser will check for availability at runtime.

### 9. `scripts/utils.py` — Shared utilities

Add:
- `estimate_batch_cost(file_count, avg_tokens, model_tiers)` — cost estimation helper
- `format_file_size(bytes)` — human-readable file sizes for progress display

### 10. `scripts/config.py` template (via `discover_vault.py`)

Add new config constants:
- `PARSE_CACHE_DIR` — `.cache/parse/` (parallel to `.cache/fetch/`)
- `SUPPORTED_FORMATS` — list of extensions this pipeline handles
- `MAX_CHUNK_CHARS` — default 100,000
- `WHISPER_MODEL` — default "base" (configurable for quality vs speed)

---

## Implementation Order

1. **`parse_file.py`** + **`test_parse_file.py`** — the parser is the foundation. Start with PDF + DOCX + plain text, then add remaining formats.
2. **`prompts/extract_local.txt`** + **`prompts/synthesize_local_batch.txt`** — prompt templates.
3. **`ingest_local.py`** + **`test_ingest_local.py`** — orchestrator wiring the tiers together.
4. **`skills/ingest-local/SKILL.md`** — Claude Code skill definition.
5. **`requirements.txt`** + **`utils.py`** + **`config.py`** updates — dependency and config changes.
6. Integration testing — end-to-end with sample files.

---

## Design Decisions & Trade-offs

**Why `pymupdf4llm` over `pdfplumber`?**
`pymupdf4llm` outputs markdown directly (headings, bold, lists) rather than raw text extraction. Better for vault notes. Falls back to `pdfplumber` for edge cases.

**Why shell out to `whisper` instead of using the Python API?**
Keeps whisper as an optional dependency. Users who don't need audio transcription don't need to install a 1.5GB model. The CLI binary is the standard interface.

**Why reuse the existing `research-classify` skill?**
The classification logic (folder routing, tag suggestion, wikilink detection, MOC updates) is format-agnostic. The input is already markdown by the time it reaches Tier 2. No reason to duplicate.

**Why not a watched folder / daemon?**
Adds process management complexity (systemd, launchd, Windows services). A Claude Code skill invocation is explicit, auditable, and consistent with the existing workflow. Can always add a watcher later as a separate concern.

**Chunking at natural boundaries vs fixed size?**
Fixed-size chunks split mid-sentence and lose context. Natural boundaries (pages, chapters, headings) preserve semantic coherence, which matters for extraction quality. The trade-off is slightly uneven chunk sizes, but that's acceptable.
