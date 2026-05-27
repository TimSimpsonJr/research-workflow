# Research Workflow

A Claude Code plugin for deep research into Obsidian vaults. Takes a topic (or a batch), plans the work, searches the web in confidence-gated multi-hop rounds, fetches and summarizes sources with credibility tiering, classifies them against your vault structure, and writes fully-formed notes with frontmatter, tags, wikilinks, and citations.

Zero paid API calls. All AI work runs through Claude Code subagents (Haiku for parallel tasks, Sonnet for orchestration and between-hop reasoning, Opus for synthesis) or a local Ollama instance.

## Quick Start

Install from the Fieldwork marketplace:

```
/plugin marketplace add TimSimpsonJr/fieldwork-plugins
/plugin install research-workflow@fieldwork-plugins
```

Configure your vault:

```
/research-setup
```

Start researching:

```
/research "any topic"
```

## Three Modes

- **Single topic** — `/research "quantum computing"` researches one topic end-to-end
- **Batch** — `/research batch topics.md` processes a list of topics from a file
- **Thread-pull** — after a batch run, discovers follow-up leads from what you wrote and researches them automatically

## Planning Strategies

The resolver picks a strategy automatically based on the prompt:

- **planning_only** — clear, narrow queries skip the approval gate and dispatch straight to research
- **intent_planning** — ambiguous prompts trigger a short clarifying Q&A before planning
- **unified** — batch prompts and broad topics present the full plan for review

## Depth Profiles

Each topic gets a depth assigned by the resolver:

| Depth        | Max hops | Confidence target | Typical use                                     |
|--------------|----------|-------------------|-------------------------------------------------|
| `quick`      | 1        | 0.65              | one-shot lookup, small clarifying questions     |
| `standard`   | 2        | 0.75              | most everyday topics                            |
| `deep`       | 3        | 0.85              | technical / policy topics needing primaries     |
| `exhaustive` | 4        | 0.90              | research-paper-grade work                       |

## Multi-Hop Pipeline

Each topic runs a loop:

1. **Search** for sources (SearXNG + Claude WebSearch where available), scored by source tier
2. **Fetch** (Jina Reader → Wayback → Playwright fallback) with SHA-256 cache and 7-day TTL
3. **Media** capture — images, video thumbnails, audio — rewritten to Obsidian embeds
4. **Summarize** (Ollama if available, Haiku subagent otherwise)
5. **Hop-planner** (Sonnet) decides what happens next:
   - `continue` with a chosen hop pattern (`entity_expansion`, `temporal_progression`, `conceptual_deepening`, or `causal_chain`)
   - `stop` if confidence target is reached
   - `replan` if contradictions spiked or coverage stalled

The loop runs up to the topic's max-hop ceiling. A quality gate then compares per-topic confidence against its target and either accepts, re-admits with a bumped ceiling (auto-replan, up to twice), or escalates to the user.

## Source Tiering and Confidence

Every source gets a numeric credibility tier:

- **T1 (1.0)** — peer-reviewed, primary documents, official datasets
- **T2 (0.75)** — major news outlets, academic preprints, authoritative reporting
- **T3 (0.5)** — analysis pieces, secondary aggregators
- **T4 (0.3)** — opinion, blogs, social

Sources are also tagged with an orthogonal `is_primary` boolean and a `primary_type` enum (eyewitness / official-record / dataset / interview / etc.) so primary-source presence can be scored independently of tier.

Confidence at the end of each hop is:

```
0.4 * tier_diversity + 0.3 * topic_coverage + 0.2 * primary_presence + 0.1 * source_count_adequacy
```

A second signal — `contradiction_rate` — runs in parallel and can independently trigger a replan if it spikes.

## Pipeline Stages

| Stage | What                                                                          |
|-------|-------------------------------------------------------------------------------|
| 0     | Load config, detect infrastructure tier, build / update vault index           |
| 1     | Check for active or stale run                                                 |
| 2     | Triage — strategy selection                                                   |
| 3     | Resolve — topic plans with depth profiles                                     |
| 4     | Hop loop — search / fetch / media / summarize / hop-planner per topic per hop |
| 5     | Quality gate — confidence + contradiction checks; auto-replan or escalate     |
| 6     | Classify — map summaries to vault folders, tags, wikilinks                    |
| 7     | Write notes — final notes with frontmatter, citations, embedded media         |
| 8     | Wikilink scan — backfill links into existing notes                            |
| 9     | Discover threads — score batch results for follow-up                          |
| 10    | Complete — archive run, write case record for pattern learning                |

State is checkpointed after every stage. If the pipeline crashes, it resumes from the last completed stage.

## Infrastructure Tiers

| Tier     | Requires                                                  | Adds                                                                                  |
|----------|-----------------------------------------------------------|---------------------------------------------------------------------------------------|
| **Base** | Claude Code only                                          | Full pipeline via subagents (search, summarize, classify all via Haiku)               |
| **Mid**  | + Ollama                                                  | Local summarization (no API spend on summary work)                                    |
| **Full** | + SearXNG (Docker) + Playwright + yt-dlp + Whisper        | Private search merging, JS-page rendering, YouTube extraction, audio transcription    |

`/research-setup` auto-detects your tier and can auto-start the SearXNG container.

## Cases — Foundation for Pattern Learning

Each completed run writes a JSON case record to `{vault}/.research-workflow/cases/{run_id}.json` capturing the query, domain tags, strategy used, depth profile, hops executed, confidence achieved, contradiction rate, and which hop patterns worked vs. failed. v3.0.0 writes these records but does not yet read them. v3.1.0 will add the read path — the resolver will surface relevant prior cases at triage so downstream agents bias toward query formulations and hop patterns that have worked for similar topics before.

## Project Structure

```
.claude-plugin/
  plugin.json                 Claude Code plugin manifest
  marketplace.json            Single-plugin marketplace pointer (./ source)

skills/
  research/SKILL.md           Sonnet orchestrator — 11-stage multi-hop pipeline
  research-setup/SKILL.md     Interactive setup wizard

agents/
  topic-resolver.md           Sonnet — NL prompt → research plan, strategy + depth
  hop-planner.md              Sonnet — between-hop confidence math + next-hop decision
  search-agent.md             Haiku — per-topic web search + T1-T4 source scoring
  classify-agent.md           Haiku — summary → folder + tags + wikilinks
  thread-discoverer.md        Haiku — batch-result lead scoring for follow-up research
  wikilink-scanner.md         Haiku — wikilink backfill into existing notes

scripts/
  config_manager.py           JSON vault config (.research-workflow/config.json)
  state.py                    v3 checkpoint schema, atomic transitions, case writer
  detect_tier.py              base/mid/full tier detection + SearXNG auto-start
  vault_index.py              SQLite FTS5 vault search index
  fetch_and_clean.py          Jina → Wayback → Playwright fetch + SHA-256 cache
  fetch_playwright.py         JS-page fallback (full tier only)
  fetch_media.py              Media download + Obsidian embed rewriting
  summarize.py                Map-reduce summarization (Ollama)
  confidence.py               Depth profiles + confidence/contradiction formulas
  ...
```

See [MANIFEST.md](MANIFEST.md) for the complete file tree and key relationships.

## Development

```bash
pip install -r requirements.txt
pip install pytest pytest-mock
pytest tests/ -v
```

All 308 tests run offline. No API keys required.

### Requirements

- Python 3.10+
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- [Obsidian](https://obsidian.md/) vault

### Optional (full tier)

- Docker — for SearXNG search
- Ollama — for local summarization
- Playwright — `pip install playwright && playwright install chromium`
- `yt-dlp` — for YouTube extraction
- `openai-whisper` — for audio transcription

## License

MIT
