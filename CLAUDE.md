# Research Workflow — Project Guide

## What this is

A Claude Code plugin for deep research into Obsidian vaults. The `/research` skill is the main entry point — it orchestrates an 8-stage pipeline: resolve, search, fetch, media, summarize, classify, write, discover. Three modes: single topic, batch, and thread-pull.

## Architecture

- **Plugin** (`plugin.json`): Declares skills and agents for Claude Code discovery. No direct Claude API calls — everything goes through Claude Code's Task tool and Bash.
- **Skills** (`skills/`): Claude Code skill definitions (Markdown). The orchestrator (`research`) dispatches Haiku subagents defined in `agents/`. The setup wizard (`research-setup`) handles first-run configuration.
- **Agents** (`agents/`): Haiku subagent definitions read by the research skill at runtime and passed as prompts via the Task tool. Four agents: topic-resolver, search-agent, classify-agent, thread-discoverer.
- **Scripts** (`scripts/`): Python tools for I/O, caching, and extraction only. No Claude API calls — `claude_pipe.py` is legacy and being phased out.
- **Config** (`config_manager.py`): JSON-based vault config stored at `{vault}/.research-workflow/config.json`. Replaces the old `config.py` + `.env` pattern.
- **State** (`state.py`): Pipeline checkpoints with crash recovery. The skill checkpoints after every stage and can resume from the last completed stage.
- **Prompts** (`scripts/prompts/`): Text templates for summarization and synthesis. See `scripts/prompts/README.md` for the assembly pattern.

## Infrastructure tiers

`detect_tier.py` determines what's available at startup:

- **Base**: Claude Code only — full pipeline via subagents
- **Mid**: + Ollama — local summarization, faster classify
- **Full**: + SearXNG (Docker) — private web search

## Key conventions

- **No anthropic SDK**: The pipeline does not import or call the Anthropic API directly. All LLM work goes through Claude Code subagents (Task tool) or Ollama.
- **Scripts are I/O only**: Python scripts handle fetching, caching, file extraction, and vault indexing. They do not make Claude API calls.
- **Model allocation**: Haiku for search/classification (cheap, parallel). Sonnet for orchestration. Subagent dispatch via Task tool.
- **Raw ingestion** (`ingest.py`, `ingest_batch.py`): Archives source content with frontmatter only. No Claude processing.
- **State checkpoints**: Every pipeline stage writes state. Crash recovery resumes from the last checkpoint.

## Working on this project

- Tests: `pytest tests/ -v` — all tests run offline (no API key needed)
- Config is generated per-vault by `research-setup` and stored in `{vault}/.research-workflow/config.json`
- Skills reference `{{VAULT_ROOT}}` and `{{REPO_ROOT}}` placeholders filled during plugin setup
- The `.claude/` and `docs/` directories are gitignored (force-add specific docs files when needed)

## Don't

- Don't add direct Claude API calls to skill files or scripts — use subagents (Task tool) or Ollama
- Don't put vault rules in individual prompt templates — they go in `vault_rules.txt` and are auto-included
- Don't modify `ingest.py` to apply vault rules — raw archival stays rule-free
- Don't import from `claude_pipe.py` in new code — it's legacy and being phased out
