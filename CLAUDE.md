# Research Workflow — Project Guide

## What this is

A Python toolkit and Claude Code skill set for automating an Obsidian research vault. The `/research` skill is the main entry point — it orchestrates web search, content fetching, vault classification, and note writing through a 3-tier pipeline.

## Architecture

- **Skills** (`skills/`): Claude Code skill definitions (Markdown). The orchestrator (`research`) spawns Haiku subagents (`research-search`, `research-classify`) via the Task tool. No direct Claude API calls from skills.
- **Scripts** (`scripts/`): Python tools for I/O, caching, and Claude API calls. `claude_pipe.py` is the shared building block — all other scripts that call Claude import from it.
- **Prompts** (`scripts/prompts/`): Text templates appended to source content as trailing instructions. See `scripts/prompts/README.md` for the assembly pattern.
- **Vault rules** (`scripts/prompts/vault_rules.txt`): Shared rules for wikilinks, citations, and tagging — auto-appended to all Claude API calls unless `--no-vault-rules` is passed.
- **Tagging reference** (`docs/TAGGING-REFERENCE.md`): Complete tag taxonomy used by the pipeline.

## Key conventions

- **Prompt assembly**: `{content}\n\n---\n{prompt}\n\n---\n{vault_rules}`. Never send prompts as system messages.
- **Model allocation**: Haiku for search/classification (cheap, parallel). Sonnet for orchestration. Opus for heavy analysis/synthesis via `claude_pipe.py`.
- **Raw ingestion** (`ingest.py`, `ingest_batch.py`): Archives source content with frontmatter only. No Claude processing, no vault rules.
- **Analysis/synthesis** (everything else): Vault rules apply automatically. This covers wikilinks, stub links, source citations, and tagging.

## Working on this project

- Tests: `pytest tests/ -v` — all tests run offline (no API key needed)
- Config is generated per-vault by `discover_vault.py` and gitignored (`scripts/config.py`, `.env`)
- Skills reference `{{placeholder}}` paths that users fill in during setup
- The `.claude/` and `docs/` directories are gitignored (force-add specific docs files when needed)

## Don't

- Don't add direct Claude API calls to skill files — use Python scripts or subagents
- Don't put vault rules in individual prompt templates — they go in `vault_rules.txt` and are auto-included
- Don't modify `ingest.py` to apply vault rules — raw archival stays rule-free
