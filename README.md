# Research Workflow Automation

A Python toolkit and Claude Code skills for automating an Obsidian research vault. Handles web research, local file ingestion, media management, note synthesis, and formatted output — all through the Claude API.

## Why This Exists

Research in Obsidian means a lot of manual work: finding sources, reading articles, deciding where notes go, maintaining consistent formatting, keeping wikilinks and MOCs up to date. This toolkit automates the tedious parts so you can focus on thinking.

**The `/research` command** takes a topic or note path, searches the web, fetches and caches the best sources, classifies them against your vault structure, and writes fully-formed notes with frontmatter, tags, wikilinks, and source citations.

**The local ingestion tools** handle files you already have — PDFs, Word docs, images, audio, video, YouTube links. They extract content, download media into your vault's attachments folder, and track citation metadata.

**The standalone scripts** cover the rest: synthesizing folders into MOCs, transforming research into articles or briefings, processing transcripts, finding related notes, and auditing vault health.

Everything runs locally through the Claude API. Your vault stays on your machine, and fetched content is cached so you're not re-downloading pages you've already processed.

## Research Pipeline

The main feature is a 3-tier pipeline invoked via Claude Code's `/research` command:

1. **Search (Haiku):** A Haiku agent searches the web and selects the 3–7 most relevant URLs.
2. **Fetch (Python):** `fetch_and_clean.py` fetches each URL via [Jina Reader](https://jina.ai/reader/), converts to markdown, and caches locally (7-day TTL). Falls back to the Wayback Machine if the primary fetch fails.
3. **Classify (Haiku):** A Haiku agent scans your vault, classifies each article, and determines where notes go — create vs. update, folder placement, tags, wikilinks, stub links.
4. **Write (Sonnet):** The orchestrator synthesizes content into final vault notes, checks for redundancy, and updates MOCs.

```
/research "topic to research"
/research path/to/existing-note.md
```

### Skills

The pipeline uses three Claude Code skills (in `skills/`):

| Skill | Model | Role |
|-------|-------|------|
| `research` | Sonnet | Orchestrator — parses input, coordinates tiers, writes notes |
| `research-search` | Haiku | Web search and URL selection |
| `research-classify` | Haiku | Vault structure mapping and classification |

The orchestrator spawns the Haiku skills as subagents. You only invoke `/research` directly.

## Local Ingestion & Media

### URL Ingestion

| Script | Purpose | Usage |
|--------|---------|-------|
| `ingest.py` | Fetch a URL into vault inbox (raw archival, no Claude processing) | `python scripts/ingest.py "https://example.com/article"` |
| `ingest_batch.py` | Batch URL ingestion from file | `python scripts/ingest_batch.py urls.txt` |

### Local File Ingestion

`ingest_local.py` extracts text from local document and audio files and writes cleaned markdown notes to the vault inbox — same format as `ingest.py`, but for files on disk instead of web URLs.

**Supported formats:**

| Extension | Backend | Notes |
|-----------|---------|-------|
| `.docx` | python-docx | Full text extraction |
| `.doc` | LibreOffice → win32com → error | Tries LibreOffice headless first, then MS Word COM automation (Windows), then fails with instructions |
| `.pdf` | pymupdf | Text extracted page-by-page, separated by `---` |
| `.mp3` | stub only | Creates a placeholder note with Whisper transcription instructions |

**Usage:**

```bash
# Ingest all supported files in a folder (top-level only)
python scripts/ingest_local.py /path/to/folder

# Recurse into subfolders
python scripts/ingest_local.py /path/to/folder --recursive

# Tag notes with a source label in frontmatter
python scripts/ingest_local.py /path/to/folder --source-label "My Document Collection"

# Write to a custom output directory instead of the vault inbox
python scripts/ingest_local.py /path/to/folder --output-dir /custom/output

# Preview what would be written without writing anything
python scripts/ingest_local.py /path/to/folder --dry-run
```

**`.doc` support** requires either [LibreOffice](https://www.libreoffice.org) (cross-platform) or Microsoft Word (Windows, via `pip install pywin32`). If neither is available, `.doc` files are skipped with a clear error message.

**`.mp3` files** produce stub notes only. To transcribe audio, install [Whisper](https://github.com/openai/whisper) and run the command shown in the stub note, then process the output with `transcript_processor.py`.

### Media Handling

| Script | Purpose | Usage |
|--------|---------|-------|
| `media_handler.py` | Extract and download media from markdown content | `python scripts/media_handler.py --extract content.md --attachments-dir /vault/Attachments --slug name` |
| `attach_media.py` | Attach a media file (local, web, YouTube, audio) to a note | `python scripts/attach_media.py note.md --url "https://example.com/image.png"` |

`media_handler.py` supports images (JPG, PNG, GIF, SVG, WebP), YouTube videos (thumbnail + transcript via yt-dlp), and audio files (copy + optional Whisper transcription). `attach_media.py` wraps this for attaching media to existing notes with proper Obsidian embeds and citation frontmatter.

## Analysis & Synthesis

| Script | Purpose | Usage |
|--------|---------|-------|
| `claude_pipe.py` | Pipe any note through Claude with a prompt template | `python scripts/claude_pipe.py --file note.md --prompt summarize` |
| `synthesize_folder.py` | Synthesize a folder of notes into a MOC | `python scripts/synthesize_folder.py --folder "Research/AI" --output "AI-MOC.md"` |
| `produce_output.py` | Transform a note into an output format | `python scripts/produce_output.py --file note.md --format web_article` |
| `transcript_processor.py` | Process a Whisper transcript into research notes | `python scripts/transcript_processor.py interview.vtt` |
| `daily_digest.py` | Summarize recent vault activity into a daily note | `python scripts/daily_digest.py` |
| `find_related.py` | Find related notes by keyword extraction | `python scripts/find_related.py note.md` |

### Vault Rules

All analysis and synthesis scripts automatically append shared vault rules (`scripts/prompts/vault_rules.txt`) to Claude API calls. These enforce consistent wikilinks, source citations, and tagging across all output. Use `--no-vault-rules` with `claude_pipe.py` to skip them for utility tasks.

### Output Formats

Available via `produce_output.py --format <name>`:

- `web_article` — Blog-style article
- `video_script` — Documentary-style video script
- `social_post` — Social media thread
- `briefing` — Executive briefing
- `talking_points` — Bullet-point talking points
- `email_newsletter` — Email newsletter

### Prompt Templates

Analysis prompts live in `scripts/prompts/`. Output format prompts live in `scripts/prompts/output_formats/`. See `scripts/prompts/README.md` for the assembly pattern.

## Vault Utilities

| Script | Purpose | Usage |
|--------|---------|-------|
| `discover_vault.py` | One-time setup — scan vault and generate config | `python scripts/discover_vault.py` |
| `vault_lint.py` | Validate frontmatter fields across the vault | `python scripts/vault_lint.py` |
| `find_broken_links.py` | Find unresolved wiki-links | `python scripts/find_broken_links.py` |

## Setup

### 1. Clone and install

```
git clone https://github.com/TimSimpsonJr/research-workflow.git
cd research-workflow
pip install -r requirements.txt
```

### 2. Configure your vault

```
python scripts/discover_vault.py
```

This scans your vault's folder structure and generates `scripts/config.py` (paths) and `.env` (API key). Open `.env` and paste your Anthropic API key on the `ANTHROPIC_API_KEY=` line.

### 3. Install the skills

Copy the skill folders into `~/.claude/skills/`:

```
# macOS / Linux
cp -r skills/research ~/.claude/skills/research
cp -r skills/research-search ~/.claude/skills/research-search
cp -r skills/research-classify ~/.claude/skills/research-classify

# Windows (PowerShell)
Copy-Item -Recurse skills\research $env:USERPROFILE\.claude\skills\research
Copy-Item -Recurse skills\research-search $env:USERPROFILE\.claude\skills\research-search
Copy-Item -Recurse skills\research-classify $env:USERPROFILE\.claude\skills\research-classify
```

Then open each skill's `SKILL.md` and replace the `{{placeholder}}` values:

| Placeholder | What to put there | Example |
|-------------|-------------------|---------|
| `{{VAULT_ROOT}}` | Your Obsidian vault folder | `C:\Users\you\Documents\My Vault` |
| `{{SCRIPTS_DIR}}` | Where you cloned this repo | `C:\Users\you\Projects\research-workflow` |
| `{{PYTHON_PATH}}` | Your Python executable | `python` or full path |
| `{{HOME}}` | Your home directory | `C:\Users\you` or `/Users/you` |

Only `research` and `research-classify` need these — `research-search` has no path references.

### 4. Try it out

```
/research "any topic you're curious about"
```

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- [Obsidian](https://obsidian.md/) vault
- [Anthropic API key](https://console.anthropic.com/)
- Python 3.10+
- Optional: [yt-dlp](https://github.com/yt-dlp/yt-dlp) (YouTube), [Whisper](https://github.com/openai/whisper) (audio transcription)

## Running Tests

```bash
pytest tests/ -v
```

119 tests across all scripts. All tests run offline — no API key needed.
