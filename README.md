# Research Workflow Automation

A modular Python toolkit and Claude Code skills for automating an Obsidian research workflow — from topic research and URL ingestion through transcript processing, note synthesis, and formatted output, all via the Claude API.

## Prerequisites

- Python 3.10+
- An Anthropic API key
- An Obsidian vault
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (for the research pipeline skills)

## Quick Start

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

**2. Configure your vault**

```bash
python discover_vault.py
```

This scans your vault, generates `config.py` and `.env`. Review `.env` and fill in `ANTHROPIC_API_KEY`.

**3. Verify config**

```bash
python -c "import config; print(config.VAULT_PATH, config.INBOX_PATH)"
```

## Research Pipeline (3-Tier)

The main feature is a 3-tier research pipeline invoked via Claude Code's `/research` command. It takes a topic or note path and produces fully-formed vault notes.

**How it works:**

1. **Tier 1 — Search (Haiku):** A Haiku agent searches the web and selects the 3-7 most relevant URLs for the topic.
2. **Tier 2 — Fetch (Python):** `fetch_and_clean.py` fetches each URL via [Jina Reader](https://jina.ai/reader/), converts to markdown, and caches results locally (MD5 key, 7-day TTL). Falls back to the Wayback Machine if the primary fetch fails.
3. **Tier 3 — Classify (Haiku):** A Haiku agent scans the vault file structure, classifies each article, and determines where new notes should go (create vs. update, folder placement, tags, wikilinks).
4. **Write (Sonnet):** The Sonnet orchestrator synthesizes the fetched content and classification into final vault notes, matching existing format conventions.

**Usage in Claude Code:**

```
/research "topic to research"
/research path/to/existing-note.md
```

### Skills

The pipeline is driven by four Claude Code skills (in `skills/`). To use them, copy or symlink them into your `~/.claude/skills/` directory:

| Skill | Model | Role |
|-------|-------|------|
| `research` | Sonnet | Orchestrator — parses input, coordinates the other tiers, writes final notes |
| `research-search` | Haiku | Tier 1 — web search and URL selection |
| `research-classify` | Haiku | Tier 3 — vault structure mapping and article classification |
| `research-haiku` | *(deprecated)* | Original single-agent approach, kept for reference |

The orchestrator spawns the Haiku skills as subagents automatically. You only invoke `/research` directly.

## Scripts

### Research Pipeline

| Script | Purpose | Usage |
|--------|---------|-------|
| `fetch_and_clean.py` | Fetch URLs via Jina Reader with caching | `python fetch_and_clean.py --input urls.json --output results.json` |

### Vault Utilities

| Script | Purpose | Usage |
|--------|---------|-------|
| `discover_vault.py` | One-time setup — generate config | `python discover_vault.py` |
| `ingest.py` | Fetch a URL into vault inbox | `python ingest.py "https://example.com/article"` |
| `ingest_batch.py` | Batch URL ingestion from file | `python ingest_batch.py urls.txt` |
| `claude_pipe.py` | Pipe any note through Claude | `python claude_pipe.py --file note.md --prompt summarize` |
| `vault_lint.py` | Validate frontmatter fields | `python vault_lint.py` |
| `find_broken_links.py` | Find unresolved wiki-links | `python find_broken_links.py` |
| `find_related.py` | Find related notes by keyword | `python find_related.py note.md` |

### Synthesis & Output

| Script | Purpose | Usage |
|--------|---------|-------|
| `synthesize_folder.py` | Synthesize a folder into a MOC | `python synthesize_folder.py --folder "Research/AI" --output "AI-MOC.md"` |
| `produce_output.py` | Transform note to output format | `python produce_output.py --file synthesis.md --format web_article` |
| `transcript_processor.py` | Process Whisper transcript | `python transcript_processor.py interview.vtt` |
| `daily_digest.py` | Daily vault summary | `python daily_digest.py` |

## Output Formats

Available via `produce_output.py --format <name>`:

- `web_article` — Blog-style article
- `video_script` — Video/YouTube script
- `social_post` — Social media post
- `briefing` — Executive briefing
- `talking_points` — Bullet-point talking points
- `email_newsletter` — Email newsletter

List all: `python produce_output.py --list-formats`

## Running Tests

```bash
pytest tests/ -v
```

95 tests across all scripts. All tests run offline (no API calls required).

## Design Docs

- `docs/plans/2026-02-25-research-workflow-automation.md` — Original toolkit implementation plan
- `docs/plans/2026-02-25-research-pipeline-3tier-design.md` — 3-tier pipeline design
- `docs/plans/2026-02-25-3tier-pipeline-implementation.md` — 3-tier pipeline implementation plan
