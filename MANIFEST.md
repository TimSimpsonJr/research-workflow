# MANIFEST

## Stack

Python 3.10+ · requests, PyYAML, rich, python-docx, pymupdf · pytest + pytest-mock (offline tests) · Claude Code skills (Sonnet orchestrator + Haiku subagents) · SQLite FTS5 vault index

## Structure

```
skills/
  research/SKILL.md              # Sonnet orchestrator — stateful 11-stage pipeline (resolve, search, fetch, media, summarize, classify, write, discover)
  research-search/SKILL.md       # Haiku subagent — web search & URL selection
  research-classify/SKILL.md     # Haiku subagent — vault placement, tags, wikilinks
  research-setup/SKILL.md        # Interactive setup wizard — vault config, tool detection, index build

agents/
  topic-resolver.md              # Haiku agent — parses NL prompts into structured research plans
  search-agent.md                # Haiku agent — web search per topic, source quality scoring
  classify-agent.md              # Haiku agent — maps summaries to vault structure, tags, links
  thread-discoverer.md           # Haiku agent — scans batch results for follow-up research leads

scripts/
  config_manager.py              # JSON-based vault config (replaces config.py + .env)
  state.py                       # Pipeline state checkpoints with crash recovery
  detect_tier.py                 # Infrastructure detection: Ollama, SearXNG, yt-dlp, Whisper
  vault_index.py                 # SQLite FTS5 index for vault full-text search
  fetch_and_clean.py             # Jina Reader fetch + SHA-256 cache (7-day TTL, SSRF protection)
  fetch_media.py                 # Media download (images, PDFs, video via yt-dlp) + Whisper transcription + Obsidian embed rewriting
  summarize.py                   # Article summarization via Ollama or file output for Haiku
  extract_local.py               # Local file text extraction (.pdf, .docx, .doc, .mp3)
  claude_pipe.py                 # Universal Claude API pipe (legacy — being phased out)
  utils.py                       # Shared helpers: startup_checks, slugify
  ingest.py                      # URL → vault inbox (raw archival via Jina Reader)
  ingest_batch.py                # Batch URL ingestion from file list
  ingest_local.py                # Local file ingestion (.docx/.doc/.pdf/.mp3 → inbox)
  vault_lint.py                  # Frontmatter validation across vault
  find_broken_links.py           # Unresolved wikilink detection
  produce_output.py              # Note → downstream format via Ollama or file output for Claude Code

scripts/prompts/
  README.md                      # Assembly pattern docs
  summarize_fetch.txt            # Summarization prompt for fetched articles
  summarize.txt                  # Generic summarization
  extract_transcript.txt         # Transcript claim extraction
  extract_claims.txt             # Claim extraction
  find_related.txt               # Related note search prompt
  identify_stakeholders.txt      # Stakeholder identification
  synthesize_topic.txt           # Topic synthesis (MOC generation)
  output_formats/                # Downstream templates: web_article, video_script, etc.

tests/
  conftest.py                    # Adds scripts/ to sys.path
  test_*.py                      # One test module per script (all offline, no API keys)

docs/
  plans/                         # Design documents and implementation plans
  handoff-token-efficiency.md    # Token optimization roadmap
```

## Key Relationships

- `research/SKILL.md` is the main entry point — dispatches all 4 agents and calls all pipeline scripts via Bash
- `state.py` provides crash recovery — `research/SKILL.md` checkpoints after every stage and can resume from last checkpoint
- `config_manager.py` stores config in `{vault}/.research-workflow/config.json` — loaded by the skill at startup, replaces old `config.py` + `.env`
- `vault_index.py` provides SQLite FTS5 search — used by classify-agent, thread-discoverer, and topic-resolver instead of globbing
- `fetch_and_clean.py` + `fetch_media.py` are the fetch pipeline — URLs go through Jina Reader with cache, then media refs are downloaded separately
- `summarize.py` branches on infrastructure: Ollama (mid/full tier) or file output for Haiku subagents (base tier)
- `detect_tier.py` determines base/mid/full tier at startup — drives branching in summarize, search, and classify stages
- Skills use `{{VAULT_ROOT}}` and `{{REPO_ROOT}}` placeholders — filled during plugin setup
- Agent definitions in `agents/` are read by the skill at runtime and passed as prompts to Haiku subagents via the Task tool
