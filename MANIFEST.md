# MANIFEST

## Stack

Python 3.10+ · requests, pymupdf, python-docx, rich, PyYAML · pytest + pytest-mock (offline tests) · Claude Code plugin v3.0 (Sonnet orchestrator + Sonnet topic-resolver + Sonnet hop-planner + Haiku for parallel search/classify/summarize/discover) · SQLite FTS5 vault index · optional Ollama (mid/full tier) + SearXNG, yt-dlp, Whisper, Playwright (full tier)

## Structure

```
plugin.json                            # Claude Code plugin manifest — declares skills and agents
requirements.txt                       # Python deps: requests, pymupdf, python-docx, rich, PyYAML

skills/
  research/SKILL.md                    # Sonnet orchestrator — multi-hop stateful pipeline (triage → resolve → hop loop → quality gate → classify → write → wikilinks → discover → complete)
  research-setup/SKILL.md              # Interactive setup wizard — vault config, tier detection, index build

agents/
  topic-resolver.md                    # Sonnet — parses NL prompts into structured research plans with approval
  search-agent.md                      # Haiku — web search per topic, source quality scoring with T1-T4 tiering
  classify-agent.md                    # Haiku — maps summaries to vault folders, tags, and wikilinks
  thread-discoverer.md                 # Haiku — scores batch results for follow-up research leads
  wikilink-scanner.md                  # Haiku — scans new notes for wikilink opportunities, updates existing notes
  hop-planner.md                       # Sonnet — between-hop reasoning: confidence, next-hop pattern, continue/stop/replan

scripts/
  config_manager.py                    # JSON vault config at {vault}/.research-workflow/config.json
  state.py                             # v3 schema (per-topic depth/hops/confidence + run-level replan/usage); atomic transitions; auto-archives completed runs
  detect_tier.py                       # Detects base/mid/full tier: Ollama, SearXNG, yt-dlp, Whisper, Playwright
  vault_index.py                       # SQLite FTS5 index for vault full-text search (used by agents)
  fetch_and_clean.py                   # Jina Reader fetch + SHA-256 cache; Wayback + Playwright fallbacks; accepts string or dict URLs
  fetch_playwright.py                  # JS-heavy page fallback (chromium via Playwright); called only when Jina + Wayback both fail or return thin content
  fetch_media.py                       # Download images/PDFs to assets dir, rewrite to Obsidian embeds; --skip-images flag
  extract_local.py                     # Local file text extraction (.pdf, .docx, .doc, .mp3)
  summarize.py                         # Map-reduce summarization via Ollama (no truncation); file output for Haiku fallback
  search_searxng.py                    # SearXNG search backend with scored results (full tier only)
  produce_output.py                    # Transforms vault notes to downstream formats via Ollama/Claude Code
  confidence.py                        # Pure-Python depth profiles + confidence/contradiction formulas; consumed by hop-planner (via Bash) and state.py
  migrate.py                           # One-time migration: .env → config.json, Areas/ → Projects/ rename
  text_utils.py                        # Zero-dependency helpers: slugify
  vault_lint.py                        # Frontmatter validation across vault (post-write quality gate)
  find_broken_links.py                 # Unresolved wikilink detection (post-write quality gate)

scripts/prompts/
  README.md                            # Assembly pattern: {content}\n\n---\n{prompt}\n\n---\n{vault_rules}
  vault_rules.txt                      # Vault conventions (wikilinks, citations, tags) — auto-appended
  summarize_fetch.txt                  # Summarization prompt for fetched articles (map phase)
  summarize_merge.txt                  # Merge prompt for combining chunk summaries (reduce phase)
  summarize.txt                        # Generic summarization prompt
  extract_claims.txt                   # Claim extraction prompt
  extract_transcript.txt               # Transcript extraction prompt
  identify_stakeholders.txt            # Stakeholder identification prompt
  synthesize_topic.txt                 # Topic synthesis prompt
  find_related.txt                     # Related note discovery prompt
  output_formats/                      # Downstream templates: web_article, video_script, briefing, etc.

docker/
  docker-compose.yml                   # SearXNG container (full tier)
  searxng/settings.yml                 # SearXNG engine config (Google, DuckDuckGo, Bing)

assets/
  research-metadata-hide.css           # Optional Obsidian CSS snippet — hides v3 diagnostic frontmatter from Properties panel

template-vault/                        # Starter vault: Inbox/, Projects/, Resources/, Meta/, assets/
  .research-workflow/config.json       # Default config for new users

tests/
  conftest.py                          # Adds scripts/ to sys.path
  test_*.py                            # One module per script — all offline, no API keys required

docs/
  TAGGING-REFERENCE.md                 # Complete tag taxonomy used by classify agent
  handoff-token-efficiency.md          # Token optimization roadmap
  plans/                               # Design documents (pipeline-rework, 3-tier, local ingestion)
```

## Key Relationships

- `plugin.json` declares the plugin — lists both skills and all 6 agents for Claude Code discovery
- `skills/research/SKILL.md` is the sole entry point — orchestrates the multi-hop pipeline, dispatches all 6 agents via the Task tool, and writes final notes itself (Sonnet) or escalates synthesis notes to Opus
- `state.py` enables crash recovery — checkpoints after every stage to `{vault}/.research-workflow/state/`; auto-archives completed runs so new runs start cleanly
- `state.py` v3 schema adds per-topic `depth`, `current_hop`, `max_hops`, `hop_genealogy`, `confidence_history`, `contradiction_rate`, `seen_urls`, `replan_hint`, `next_hop`, and run-level `replan_count`, `user_decisions`, `usage`, `strategy`, `version: 3`. On-disk version mismatch auto-archives the stale run and starts fresh
- `confidence.py` is pure-Python and shared by the `hop-planner` agent (called via Bash for confidence/contradiction math) and by `state.py` (`init_topic` looks up depth profiles via `get_depth_profile` to set `max_hops` / `confidence_target`); fully testable offline
- `hop-planner` agent runs once per hop per topic — reads `sources_so_far` + `summaries_so_far` from state, returns a `continue`/`stop`/`replan` decision with a hop pattern choice. Orchestrator applies the full transition atomically via `state.apply_hop_decision()` (genealogy + current_hop + confidence + routing + status in one save) so a crash mid-transition can't leave a topic with mismatched fields
- SKILL.md Stage 4 (hop loop) calls `apply_hop_decision` for atomic state transitions; Stage 5 (quality gate) compares per-topic confidence against the topic's `confidence_target` from its depth profile and re-admits failing topics by bumping `max_hops`
- `config_manager.py` is the config authority — loaded at Stage 0, replaces old `config.py` + `.env`; all scripts derive vault paths from it
- `detect_tier.py` drives pipeline branching — base tier routes summarize/classify to Haiku subagents; mid/full tier routes to Ollama
- `vault_index.py` is shared by classify-agent, thread-discoverer, topic-resolver, and wikilink-scanner — FTS5 queries replace glob-all-markdown; rebuilt incrementally at Stage 0
- `fetch_and_clean.py` → `fetch_media.py` is the fetch pipeline — URLs go through Jina Reader with SHA-256 cache, then media refs are downloaded and rewritten to Obsidian embed syntax
- `fetch_playwright.py` is the JS-page fallback inside `fetch_and_clean.fetch_url()`, invoked only when both Jina and Wayback fail or return thin (<200 char) content; full tier only
- `summarize.py` uses map-reduce for Ollama: short articles get a single call, long articles are chunked (20K chars with overlap), each chunk summarized, then merged via `summarize_merge.txt`. `--prepare-for-claude` writes per-article files for Haiku subagents (fallback)
- `extract_local.py` replaces the fetch stages for local files — .pdf/.docx/.doc/.mp3 extracted and injected into the fetch_results format so the hop loop runs unchanged
- `migrate.py` is a one-time tool — reads old `.env`, writes `config.json` via `config_manager`, renames vault folders, rebuilds index, and removes stale `.tmp/` state
- `vault_lint.py` and `find_broken_links.py` run automatically after the write stage as quality gates, reporting violations in the final completion summary
