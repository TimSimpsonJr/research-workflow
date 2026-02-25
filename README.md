# Research Workflow Automation

A modular Python toolkit and Claude Code skills for automating an Obsidian research workflow — from topic research and URL ingestion through transcript processing, note synthesis, and formatted output, all via the Claude API.

## Why This Exists

Research in Obsidian means a lot of manual work: finding sources, reading articles, deciding where notes go, maintaining consistent formatting, keeping wikilinks and MOCs up to date. This toolkit automates the tedious parts so you can focus on thinking.

**The `/research` command** lets you type a topic and walk away. It searches the web, fetches and caches the best sources, figures out where new notes belong in your vault's folder structure, and writes them with proper frontmatter, tags, wikilinks, and source citations — all matching your existing conventions.

**The standalone scripts** handle the rest of the workflow: ingesting URLs into an inbox, linting frontmatter across the vault, finding broken wikilinks, surfacing related notes, synthesizing folders into MOCs, processing interview transcripts, and transforming research into output formats like articles, briefings, or newsletters.

Everything runs locally through the Claude API. Your vault stays on your machine, and fetched web content is cached so you're not re-downloading pages you've already read.

## What you need

- An [Obsidian](https://obsidian.md/) vault (the folder of markdown files you already have)
- An [Anthropic API key](https://console.anthropic.com/) (costs a few cents per research run)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (the CLI tool that runs the skills)
- Python 3.10 or newer

If you're not sure whether you have Python installed, open a terminal and type `python --version`. If you get a version number back, you're good. If not, grab it from [python.org](https://www.python.org/downloads/).

## Setup

### 1. Clone the repo and install dependencies

Open a terminal and run:

```bash
git clone https://github.com/TimSimpsonJr/research-workflow.git
cd research-workflow
pip install -r requirements.txt
```

`pip install` downloads the Python libraries this project depends on. You only need to do this once.

### 2. Point the toolkit at your vault

```bash
python discover_vault.py
```

This looks at your vault's folder structure and generates two files:

- `config.py` — paths to your vault, inbox, and other folders it detected
- `.env` — where your API key goes

Open `.env` in a text editor and paste your Anthropic API key on the `ANTHROPIC_API_KEY=` line.

### 3. Verify it worked

```bash
python -c "import config; print(config.VAULT_PATH, config.INBOX_PATH)"
```

You should see the paths to your vault and inbox printed back. If you get an error, double-check that `.env` has your API key and that the paths in `config.py` look right.

### 4. Install the Claude Code skills

Copy the skill folders into your Claude Code skills directory:

```bash
# macOS / Linux
cp -r skills/research ~/.claude/skills/research
cp -r skills/research-search ~/.claude/skills/research-search
cp -r skills/research-classify ~/.claude/skills/research-classify

# Windows (PowerShell)
Copy-Item -Recurse skills\research $env:USERPROFILE\.claude\skills\research
Copy-Item -Recurse skills\research-search $env:USERPROFILE\.claude\skills\research-search
Copy-Item -Recurse skills\research-classify $env:USERPROFILE\.claude\skills\research-classify
```

Then open the skill files and replace the `{{placeholder}}` paths with your actual paths:

- `{{VAULT_ROOT}}` — your Obsidian vault folder (e.g., `C:\Users\you\Documents\My Vault`)
- `{{SCRIPTS_DIR}}` — wherever you cloned this repo (e.g., `C:\Users\you\Projects\research-workflow`)
- `{{PYTHON_PATH}}` — your Python executable (whatever `python --version` works with)
- `{{HOME}}` — your home directory (e.g., `C:\Users\you` or `/Users/you`)

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