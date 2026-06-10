# MANIFEST

## Stack

Python 3.10+ · requests, pymupdf, python-docx, rich, PyYAML · pytest + pytest-mock (offline) · Claude Code plugin v3.1 (Sonnet orchestrator + Sonnet topic-resolver/hop-planner + Haiku for search/classify/summarize/discover/case-analyzer) · SQLite FTS5 vault index · optional Ollama (mid/full tier) + SearXNG, yt-dlp, Whisper, Playwright (full tier)

## Structure

```
.claude-plugin/plugin.json             # Marketplace manifest — name, version, description, keywords
requirements.txt                       # Python deps

skills/
  research/SKILL.md                    # Sonnet orchestrator — multi-hop pipeline (triage → resolve → hop loop → quality gate → classify → write → wikilinks → discover → analyze → complete)
  research-setup/SKILL.md              # Interactive setup wizard — vault config, tier detection, index build

agents/
  topic-resolver.md                    # Sonnet — parses NL prompts into structured plans; consults learned_patterns
  search-agent.md                      # Haiku — web search per topic, T1-T4 source tiering; biased by learned patterns
  classify-agent.md                    # Haiku — vault folder/tag/wikilink assignment
  thread-discoverer.md                 # Haiku — scores results for follow-up leads
  wikilink-scanner.md                  # Haiku — scans new notes for wikilink opportunities
  hop-planner.md                       # Sonnet — between-hop reasoning; pattern-success aware
  case-analyzer.md                     # Haiku — semantic-compare for accumulator merge (v3.1)

scripts/
  config_manager.py                    # JSON vault config at {vault}/.researcher/config.json
  state.py                             # v3 schema + atomic transitions (apply_hop_decision, apply_replan_readmit, acquire_state_lock)
  accumulator.py                       # v3.1 — JSON-backed store of candidate patterns at {vault}/.researcher/accumulator.json
  learned_patterns.py                  # v3.1 — Markdown parser/writer for graduated patterns at {vault}/.researcher/learned_patterns.md
  pattern_detection.py                 # v3.1 — pure-Python heuristic candidate detectors (tier dominance, hop dominance, query recurrence)
  score_updates.py                     # v3.1 — run-level W/L computation, score-apply, demotion sweep
  case_analyzer.py                     # v3.1 — Stage 10d top-level analyzer wiring heuristics + accumulator + learned + scoring
  detect_tier.py                       # Detects base/mid/full tier
  vault_index.py                       # SQLite FTS5 index for vault search
  fetch_and_clean.py                   # Jina Reader fetch + SHA-256 cache; Wayback + Playwright fallbacks
  fetch_playwright.py                  # JS-heavy page fallback (chromium); full tier only
  fetch_media.py                       # Download images/PDFs to assets dir, rewrite to Obsidian embeds
  extract_local.py                     # Local file extraction (.pdf, .docx, .doc, .mp3)
  summarize.py                         # Map-reduce summarization via Ollama
  search_searxng.py                    # SearXNG search backend (full tier)
  produce_output.py                    # Downstream format transforms
  confidence.py                        # Pure-Python depth profiles + confidence/contradiction formulas
  migrate.py                           # One-time .env → config.json migration; vault folder renames
  text_utils.py                        # slugify helpers
  vault_lint.py                        # Frontmatter validation (post-write quality gate)
  find_broken_links.py                 # Unresolved wikilink detection (post-write quality gate)

scripts/prompts/
  README.md, vault_rules.txt           # Assembly pattern + auto-appended vault conventions
  summarize_*.txt, extract_*.txt, ...  # Map/reduce/extraction/synthesis templates
  output_formats/                      # Downstream templates: web_article, video_script, briefing

docker/                                # SearXNG container config (full tier)
assets/                                # Optional Obsidian CSS snippet
template-vault/                        # Starter vault scaffold for new users

tests/
  conftest.py                          # Adds scripts/ to sys.path
  test_*.py                            # One module per script — all offline
  test_v3_compat.py                    # v3.1 — empty-state behaves like v3.0.0
  fixtures/case_learning/*.json        # v3.1 — synthesized case fixtures for pattern detection

docs/plans/, docs/handoffs/            # Design docs (gitignored except force-added)
```

## Key Relationships

- `skills/research/SKILL.md` is the sole entry point — orchestrates pipeline, dispatches all 7 agents via Task tool, writes notes (Sonnet) or escalates to Opus
- `state.py` schema v3 adds per-topic depth/hops/confidence + run-level replan/usage/strategy; `apply_hop_decision` (Stage 4e) and `apply_replan_readmit` (Stage 5b/5c) make multi-field updates atomic so crashes can't leave mismatched fields
- `confidence.py` is pure-Python and shared by `hop-planner` (via Bash) and `state.py` (`init_topic` reads depth profiles to set `max_hops`/`confidence_target`)
- `vault_index.py` (FTS5) is shared by classify-agent, thread-discoverer, topic-resolver, and wikilink-scanner — rebuilt incrementally at Stage 0
- `fetch_and_clean.py` → `fetch_media.py` is the fetch pipeline; `fetch_playwright.py` is invoked only when both Jina and Wayback fail or return thin content (full tier)
- `vault_lint.py` and `find_broken_links.py` run as post-write quality gates, reporting violations in the completion summary
- **v3.1 case learning:** `case_analyzer.analyze()` is dispatched from `skills/research/SKILL.md:Stage 10d` and wires `pattern_detection.py` (heuristics), `accumulator.py` (candidates), `learned_patterns.py` (graduated), and `score_updates.py` (W/L scoring)
- **v3.1 semantic merge:** `agents/case-analyzer.md` is dispatched optionally from `analyze()` for semantic merge; its prompt shape is pinned by `tests/test_case_analyzer_contract.py`
- **v3.1 vault state:** `accumulator.json` (candidates) and `learned_patterns.md` (graduated) both live at `{vault}/.researcher/`; `state.acquire_state_lock` serializes Stage 10d/10e writes so concurrent /research runs can't race
