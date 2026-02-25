# Research Workflow Automation

A modular Python toolkit that automates an Obsidian research workflow — ingesting URLs, processing transcripts, synthesizing notes, and producing formatted outputs via the Claude API.

## Prerequisites

- Python 3.10+
- An Anthropic API key
- An Obsidian vault

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

## Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `discover_vault.py` | One-time setup — generate config | `python discover_vault.py` |
| `ingest.py` | Fetch a URL into vault inbox | `python ingest.py "https://example.com/article"` |
| `ingest_batch.py` | Batch URL ingestion from file | `python ingest_batch.py urls.txt` |
| `claude_pipe.py` | Pipe any note through Claude | `python claude_pipe.py --file note.md --prompt summarize` |
| `vault_lint.py` | Validate frontmatter fields | `python vault_lint.py` |
| `find_broken_links.py` | Find unresolved wiki-links | `python find_broken_links.py` |
| `find_related.py` | Find related notes by keyword | `python find_related.py note.md` |
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

72 tests across all scripts. All tests run offline (no API calls required).

## Implementation Plan

See `docs/plans/2026-02-25-research-workflow-automation.md` for the full task-by-task implementation plan.
