# Research Workflow Automation

A modular Python toolkit and Claude Code skills for automating an Obsidian research workflow — from topic research and URL ingestion through transcript processing, note synthesis, and formatted output, all via the Claude API.

## Why This Exists

Research in Obsidian means a lot of manual work: finding sources, reading articles, deciding where notes go, maintaining consistent formatting, keeping wikilinks and MOCs up to date. This toolkit automates the tedious parts so you can focus on thinking.

**The `/research` command** lets you type a topic and walk away. It searches the web, fetches and caches the best sources, figures out where new notes belong in your vault's folder structure, and writes them with proper frontmatter, tags, wikilinks, and source citations — all matching your existing conventions.

**The standalone scripts** handle the rest of the workflow: ingesting URLs into an inbox, linting frontmatter across the vault, finding broken wikilinks, surfacing related notes, synthesizing folders into MOCs, processing interview transcripts, and transforming research into output formats like articles, briefings, or newsletters.

Everything runs locally through the Claude API. Your vault stays on your machine, and fetched web content is cached so you're not re-downloading pages you've already read.

## Research Pipeline (3-Tier)

The main feature is a 3-tier research pipeline invoked via Claude Code's `/research` command. It takes a topic or note path and produces fully-formed vault notes.

**How it works:**

1. **Tier 1 — Search (Haiku):** A Haiku agent searches the web and selects the 3-7 most relevant URLs for the topic.
2. **Tier 2 — Fetch (Python):** `fetch_and_clean.py` fetches each URL via [Jina Reader](https://jina.ai/reader/), converts to markdown, and caches results locally (7-day TTL). Falls back to the Wayback Machine if the primary fetch fails.
3. **Tier 3 — Classify (Haiku):** A Haiku agent scans the vault file structure, classifies each article, and determines where new notes should go (create vs. update, folder placement, tags, wikilinks).
4. **Write (Sonnet):** The Sonnet orchestrator synthesizes the fetched content and classification into final vault notes, matching existing format conventions.

**Usage in Claude Code:**

```
/research "topic to research"
/research path/to/existing-note.md
```

### Skills

The pipeline is driven by three Claude Code skills (in `skills/`). To use them, copy or symlink them into your `~/.claude/skills/` directory:

| Skill | Model | Role |
|-------|-------|------|
| `research` | Sonnet | Orchestrator — parses input, coordinates the other tiers, writes final notes |
| `research-search` | Haiku | Tier 1 — web search and URL selection |
| `research-classify` | Haiku | Tier 3 — vault structure mapping and article classification |

The orchestrator spawns the Haiku skills as subagents automatically. You only invoke `/research` directly.

## Scripts

All Python scripts live in the `scripts/` directory. Run them from the repo root.

### Research Pipeline

| Script | Purpose | Usage |
|--------|---------|-------|
| `fetch_and_clean.py` | Fetch URLs via Jina Reader with caching | `python scripts/fetch_and_clean.py --input urls.json --output results.json` |

### Vault Utilities

| Script | Purpose | Usage |
|--------|---------|-------|
| `discover_vault.py` | One-time setup — generate config | `python scripts/discover_vault.py` |
| `ingest.py` | Fetch a URL into vault inbox | `python scripts/ingest.py "https://example.com/article"` |
| `ingest_batch.py` | Batch URL ingestion from file | `python scripts/ingest_batch.py urls.txt` |
| `claude_pipe.py` | Pipe any note through Claude | `python scripts/claude_pipe.py --file note.md --prompt summarize` |
| `vault_lint.py` | Validate frontmatter fields | `python scripts/vault_lint.py` |
| `find_broken_links.py` | Find unresolved wiki-links | `python scripts/find_broken_links.py` |
| `find_related.py` | Find related notes by keyword | `python scripts/find_related.py note.md` |

### Synthesis & Output

| Script | Purpose | Usage |
|--------|---------|-------|
| `synthesize_folder.py` | Synthesize a folder into a MOC | `python scripts/synthesize_folder.py --folder "Research/AI" --output "AI-MOC.md"` |
| `produce_output.py` | Transform note to output format | `python scripts/produce_output.py --file synthesis.md --format web_article` |
| `transcript_processor.py` | Process Whisper transcript | `python scripts/transcript_processor.py interview.vtt` |
| `daily_digest.py` | Daily vault summary | `python scripts/daily_digest.py` |

## Output Formats

Available via `produce_output.py --format <name>`:

- `web_article` — Blog-style article
- `video_script` — Video/YouTube script
- `social_post` — Social media post
- `briefing` — Executive briefing
- `talking_points` — Bullet-point talking points
- `email_newsletter` — Email newsletter

List all: `python scripts/produce_output.py --list-formats`

## What you need

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and working
- An [Obsidian](https://obsidian.md/) vault
- An [Anthropic API key](https://console.anthropic.com/) (if Claude Code is working, you already have one)
- Python 3.10 or newer

## Setup

The easiest way to set this up is to let Claude Code do it for you. Start a Claude Code session and ask it to help you install.

Or do it yourself:

### 1. Clone and install

In Claude Code, or in any terminal:

```
git clone https://github.com/TimSimpsonJr/research-workflow.git
cd research-workflow
pip install -r requirements.txt
```

### 2. Configure your vault

```
python scripts/discover_vault.py
```

This scans your vault's folder structure and generates `scripts/config.py` (paths) and `.env` (API key). Open `.env` and paste your Anthropic API key on the `ANTHROPIC_API_KEY=` line. If you're already using Claude Code, this is the same key from your `ANTHROPIC_API_KEY` environment variable.

### 3. Install the skills

The research pipeline runs through [Claude Code skills](https://docs.anthropic.com/en/docs/claude-code/skills) — markdown files that teach Claude Code how to do specific tasks. You need to copy them to your skills directory and fill in your paths.

Copy the three active skill folders into `~/.claude/skills/`:

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

Then open each skill's `SKILL.md` and replace the `{{placeholder}}` values with your actual paths:

| Placeholder | What to put there | Example |
|-------------|-------------------|---------|
| `{{VAULT_ROOT}}` | Your Obsidian vault folder | `C:\Users\you\Documents\My Vault` |
| `{{SCRIPTS_DIR}}` | Where you cloned this repo (the repo root) | `C:\Users\you\Projects\research-workflow` |
| `{{PYTHON_PATH}}` | Your Python executable | `C:\Users\you\AppData\Local\Programs\Python\Python312\python.exe` |
| `{{HOME}}` | Your home directory | `C:\Users\you` or `/Users/you` |

Only the `research` orchestrator skill and `research-classify` skill need these — `research-search` has no path references.

### 4. Try it out

Start a Claude Code session and type:

```
/research "any topic you're curious about"
```

Claude will search the web, fetch the best sources, figure out where notes belong in your vault, and write them. The first run takes a minute or two — subsequent runs are faster because fetched pages are cached locally.

## Running Tests

```bash
pytest tests/ -v
```

95 tests across all scripts. All tests run offline (no API calls required).
