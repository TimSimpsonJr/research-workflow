# Research Workflow

A Claude Code plugin for deep research into Obsidian vaults. Takes a topic, searches the web, fetches and summarizes sources, classifies them against your vault structure, and writes fully-formed notes with frontmatter, tags, wikilinks, and citations.

## Quick Start

1. Clone this repo
2. Add it as a Claude Code plugin: `/install-plugin /path/to/research-workflow`
3. Run `/research-setup` to configure your vault
4. Start researching: `/research "any topic"`

## Three Modes

- **Single topic** --- `/research "quantum computing"` researches one topic end-to-end
- **Batch** --- `/research batch topics.md` processes a list of topics from a file
- **Thread-pull** --- after a batch run, discovers follow-up leads and researches them automatically

## Infrastructure Tiers

The pipeline adapts to what you have installed:

| Tier | Requirements | What it adds |
|------|-------------|--------------|
| **Base** | Claude Code only | Full pipeline via Claude Code subagents |
| **Mid** | + Ollama | Local summarization, faster classify |
| **Full** | + SearXNG (Docker) | Private web search, no API search dependency |

`/research-setup` detects your tier automatically.

## Pipeline Overview

The `/research` skill runs an 8-stage pipeline:

1. **Resolve** --- parse topic into structured research plan
2. **Search** --- find relevant sources (SearXNG or search agent)
3. **Fetch** --- download and clean articles via Jina Reader (cached, 7-day TTL)
4. **Media** --- extract images, video thumbnails, audio
5. **Summarize** --- condense articles (Ollama or Haiku subagent)
6. **Classify** --- map summaries to vault folders, tags, wikilinks
7. **Write** --- produce final vault notes with frontmatter and citations
8. **Discover** --- identify follow-up threads for batch mode

State is checkpointed after every stage. If the pipeline crashes, it resumes from the last checkpoint.

## Project Structure

```
skills/                     Claude Code skill definitions
  research/SKILL.md           Main orchestrator (8-stage pipeline)
  research-setup/SKILL.md     Interactive setup wizard
  research-search/SKILL.md    Web search subagent (legacy)
  research-classify/SKILL.md  Vault classification subagent (legacy)

agents/                     Haiku subagent definitions
  topic-resolver.md           Parses topics into research plans
  search-agent.md             Web search and source scoring
  classify-agent.md           Vault placement, tags, wikilinks
  thread-discoverer.md        Follow-up lead detection

scripts/                    Python tools (I/O, caching, extraction)
  config_manager.py           JSON-based vault config
  state.py                    Pipeline state checkpoints + crash recovery
  detect_tier.py              Infrastructure detection (Ollama, SearXNG, etc.)
  vault_index.py              SQLite FTS5 vault search index
  fetch_and_clean.py          Jina Reader fetch + SHA-256 cache
  fetch_media.py              Media download + Obsidian embed rewriting
  summarize.py                Summarization (Ollama or file output)
  extract_local.py            Local file text extraction
  search_searxng.py           SearXNG search backend (full tier)
  produce_output.py           Note -> article/briefing/video script
  ingest.py                   URL -> vault inbox (raw archival)
  ingest_batch.py             Batch URL ingestion
  ingest_local.py             Local file ingestion (.docx/.pdf/.mp3)
  vault_lint.py               Frontmatter validation
  find_broken_links.py        Unresolved wikilink detection

scripts/prompts/            Prompt templates for summarization, synthesis
docker/                     SearXNG container config (full tier)
template-vault/             Starter vault structure for new users
tests/                      Offline test suite (no API keys needed)
plugin.json                 Claude Code plugin manifest
```

## Development

### Running tests

```bash
pip install -r requirements.txt
pip install pytest pytest-mock
pytest tests/ -v
```

All tests run offline with no API keys required.

### Requirements

- Python 3.10+
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- [Obsidian](https://obsidian.md/) vault

Python dependencies (`requirements.txt`):
- `requests` --- HTTP requests
- `pymupdf` --- PDF text extraction
- `python-docx` --- Word document extraction

Optional (for full tier):
- `yt-dlp` --- YouTube video extraction
- `openai-whisper` --- audio transcription
- Docker --- for running SearXNG
- Ollama --- for local summarization
