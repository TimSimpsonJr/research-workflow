# SuperClaude Methodology Rework — Design

**Status:** Design approved 2026-05-26. Implementation plan to follow (writing-plans skill).
**Target release:** v3.0.0 (Stage A), v3.1.0 (Stage B follow-up)
**Predecessor:** `docs/plans/2026-05-26-superclaude-methodology-rework.md` (advisory input, not a prescription)
**Related:** GitHub Issue [#4](https://github.com/TimSimpsonJr/research-workflow/issues/4) — robust contradiction-detection signal (deferred, design-input-needed)

---

## Context

The `research-workflow` plugin currently runs a linear single-hop pipeline: resolve → search → fetch → media → summarize → classify → write → wikilink-scan → discover-threads → complete. It produces high-quality vault notes via Haiku subagents, but lacks **research methodology depth** — no confidence measurement, no multi-hop reasoning, no replanning when sources are weak.

The advisory doc proposed adopting SuperClaude's research methodology on top of our existing infrastructure (Jina, SearXNG, Ollama, Haiku subagents). After auditing both methodologies in detail (see brainstorming session), we've decided to adopt SuperClaude's methodology layer wholesale, refined for the civic-research use case and our Obsidian-vault output model.

This document captures the design. An implementation plan in `docs/plans/2026-05-26-...-plan.md` will follow.

### Why a major version bump

This is v3.0.0, not v2.x. The pipeline shape changes substantially: the linear flow becomes a hop loop with replanning, the resolver gains strategy triage, and source credibility shifts to a numeric model. CLI compatibility is preserved (`/research "topic"` still works), but state schema, agent contracts, and note frontmatter all change. Major version signals the upgrade impact.

### Secondary cleanup: legacy SDK fossils

Folded in as a small first step. The orchestrator no longer uses the Anthropic SDK (confirmed by audit), but legacy quality-gate scripts (`find_broken_links.py`, `vault_lint.py`) still pull in `utils.py → config.py`, which forces tests to shim `ANTHROPIC_API_KEY`. Cleanup deletes `config.py`, refactors `utils.py` (or removes it entirely), drops the test shims, and updates `scripts/prompts/README.md` to remove stale references to the long-deleted `claude_pipe.py`. CLAUDE.md gets an explicit "no Anthropic SDK, no `claude -p`" rule.

---

## Decisions reference

Locked-in choices from the brainstorming session.

| Area | Decision |
|---|---|
| Scope | Full methodology adoption (all twelve items), two-stage ship |
| Stage A | Methodology behavior (depth, credibility, confidence, multi-hop, strategy, write-stage improvements, Playwright fallback, SDK cleanup) |
| Stage B | Pattern learning / case-based reasoning (v3.1.0 follow-up) |
| Depth × batch | Per-topic depth assignment by resolver; depth absorbs the old priority concept |
| Confidence model | Two-signal: `confidence_score` + `contradiction_rate`, each can trigger replan |
| Confidence formula | `0.4 × tier_diversity + 0.3 × topic_coverage + 0.2 × primary_source_presence + 0.1 × source_count_adequacy` |
| Source credibility | T1-T4 tiers + numeric `credibility_score` (0.3-1.0) + orthogonal `is_primary` boolean |
| Quality gate UX | Auto-replan up to 2 cycles, then block with diagnostic prompt. One user-granted extension max (3 total replan cycles ceiling). |
| Strategy selection | Full triage: planning_only / intent_planning / unified, with one-line confirm even in planning_only |
| intent_planning scope | ≤3 questions for single ambiguous topic; ≤1 batch-level question for batches |
| Time budgets | Dropped entirely (hop count + source count are the ceilings) |
| Hop patterns | All four kept: entity expansion, temporal progression, conceptual deepening, causal chain |
| Hop-planner cadence | Once per hop per topic (not per link) |
| Hop-planner model | Sonnet (judgment-heavy, ~$0.18 per standard batch) |
| Topic-resolver model | Upgraded Haiku → Sonnet (one call per run, negligible cost, reliability matters) |
| Parallelism | Hop-level batching: all topics' hop-1, then all topics' hop-2, ... |
| Hop failure handling | Try one alternate pattern; if that also fails, early-terminate that topic with lowered confidence |
| Search query cache | **Dropped** — SHA-256 fetch cache already covers the meaningful cost |
| Playwright | Added as full-tier fetch fallback when Jina returns empty/blocked |
| Token telemetry | Per-model usage tracked from day one; Stage 10 displays breakdown + cost estimate |
| Case storage (Stage B) | Hidden: `.research-workflow/cases/`, JSON, one per run |
| Contradiction signal (v1) | Folded into classify-agent's key_claims comparison; robust replacement design tracked in [#4](https://github.com/TimSimpsonJr/research-workflow/issues/4) |
| Vault retrofit (existing notes) | Out of scope; separate follow-up session |
| Schema migration | Drop in-flight runs on schema mismatch (only one run at a time, low impact) |
| Slash-command flags | None — resolver reads natural language; "edit plan" handles overrides in unified mode |
| Default depth | `standard` (resolver fallback when prompt has no signal) |
| Tavily vs SearXNG | Keep SearXNG (free, private, fits "no paid APIs") |
| Frontmatter hygiene | Diagnostic fields (`hop_genealogy`, `research_run`, `write_model`) hidden via CSS snippet shipped with plugin |

---

## Pipeline architecture

### New stage flow

```
0. Load config + detect tier
1. Check active run (resume detection)
2. Triage (NEW) — classify strategy (planning_only / intent_planning / unified)
3. Resolve — topics + per-topic depth + execution order
4. Hop loop (NEW)
   for hop_level in 1..max(topic.max_hops for topic in topics):
     for topic where current_hop < topic.max_hops and status == "active":
       a. Search (per-topic, in parallel across topics at this hop level)
       b. Fetch
       c. Media
       d. Summarize
       e. Hop-planner → decide continue/stop/replan + pick next pattern
5. Quality gate (NEW)
   compute confidence_score + contradiction_rate per topic and overall
   if below threshold:
     auto-replan up to 2x (extend hop loop with replan hints)
   if still below after 2x:
     prompt user → replan more (one extension) / continue anyway / abandon
6. Classify (with contradiction detection extension)
7. Write notes (with uncertainty + contradiction body callouts on low-confidence runs)
8. Wikilink scan
9. Discover threads (unchanged)
10. Complete (with usage telemetry + cost + hop genealogy summary)
```

### What stays the same

- Tier detection
- Vault FTS5 index
- Fetch pipeline (Jina + SHA-256 cache)
- Media capture & Obsidian embed rewriting
- Local file extraction (`.pdf/.docx/.doc/.mp3`)
- Map-reduce summarization via Ollama
- Vault-aware classify (folder mapping, wikilinks, MOCs)
- Mtime conflict detection
- Wikilink scanner
- Thread-discoverer at end-of-run (multi-hop within-run does NOT replace it)
- Post-write structural lints (`vault_lint`, `find_broken_links`)
- State checkpointing & crash recovery (schema-bumped to v3)
- Resume/restart/abandon UX for in-flight runs

---

## Components

### Agents

| Agent | Status | Model | Change |
|---|---|---|---|
| `topic-resolver` | modified | **Sonnet** (upgraded from Haiku) | Classifies strategy (planning_only / intent_planning / unified). Assigns per-topic depth (quick/standard/deep/exhaustive) — replaces priority. |
| `search-agent` | modified | Haiku | Emits numeric `credibility_score` (0.3-1.0), `tier` (T1-T4), and orthogonal `is_primary` boolean with `primary_type` enum. Source count from depth profile. |
| `classify-agent` | modified | Haiku | Extended to surface cross-source contradictions in `contradictions_detected` field. |
| `hop-planner` | **NEW** | Sonnet | Runs between hops per topic. Computes confidence + contradiction rate from hop summaries; picks next hop pattern; scores candidate hops using thread-discoverer's 4-factor rubric; decides continue/stop/replan. |
| `thread-discoverer` | unchanged | Haiku | Same role at end-of-run for between-run follow-ups. |
| `wikilink-scanner` | unchanged | Haiku | — |

### Scripts

| Script | Status | Change |
|---|---|---|
| `state.py` | extended | Schema v2 → v3: per-topic depth, current_hop, hop_genealogy, confidence_history, contradiction_rate, status. Run-level replan_count, user_decisions, usage. New helpers: `add_usage(model, in_tokens, out_tokens, stage)`, `record_hop(topic, hop_data)`, `mark_topic_status(topic, status)`. |
| `confidence.py` | **NEW** | Computes `confidence_score` and `contradiction_rate` from per-topic state. Pure Python, fully testable offline. Exports the formula from the decisions table as a single function. |
| `detect_tier.py` | extended | Detects Playwright as a full-tier component. |
| `fetch_and_clean.py` | extended | Playwright fallback when Jina returns empty/blocked. Single-page fallback path, not a wholesale swap. |
| `utils.py` | refactored | Remove `import config` + `require_api_key` branch. If nothing useful remains, delete the file. |
| `config.py` | **DELETED** | Legacy auto-generated `.env` loader. |
| `vault_lint.py` | modified | Drop `import config` and `from utils import startup_checks`. Use `config_manager` directly. |
| `find_broken_links.py` | modified | Same as above. |
| `scripts/prompts/README.md` | rewritten | Remove dead references to `claude_pipe.py` and `call_claude()`. |
| `config_manager.py`, `vault_index.py`, `fetch_media.py`, `summarize.py`, `search_searxng.py`, `extract_local.py`, `produce_output.py`, `migrate.py`, `text_utils.py` | unchanged | — |

### Skill

`skills/research/SKILL.md` — single comprehensive rewrite to encode the new stage flow.

### CSS snippet

`assets/research-metadata-hide.css` — shipped with the plugin. Hides diagnostic fields in Obsidian's Properties panel:

```css
.metadata-property[data-property-key="hop_genealogy"],
.metadata-property[data-property-key="research_run"],
.metadata-property[data-property-key="write_model"] {
  display: none;
}
```

`research-setup` wizard offers to install it during initial vault configuration.

### Tests

| Test file | Status | Notes |
|---|---|---|
| `test_confidence.py` | **NEW** | Formula math, edge cases (zero sources, all T4, all primary, mixed) |
| `test_hop_planner.py` | **NEW** | Pattern selection, scoring math, continue/stop decisions; mocked summaries |
| `test_state.py` | extended | Hop genealogy, usage tracking, abandoned flag, schema v3 |
| `test_fetch_and_clean.py` | extended | Playwright fallback path (mocked); drops `ANTHROPIC_API_KEY` shim |
| `test_summarize.py`, `test_find_broken_links.py`, `test_vault_lint.py` | modified | Drop `ANTHROPIC_API_KEY` shims |
| All other tests | unchanged | — |

All tests offline. Multi-hop integration test uses pre-recorded subagent responses as fixtures, replayed by a mock Task dispatcher.

---

## Data flow & schemas

### state.py v3 schema

```json
{
  "run_id": "2026-05-26-sc-alpr-batch",
  "version": 3,
  "tier": "full",
  "started_at": "2026-05-26T14:22:01Z",
  "stage": "hop_loop",
  "strategy": "unified",
  "topics": [
    {
      "topic": "SC ALPR programs",
      "mode": "web_research",
      "depth": "standard",
      "max_hops": 3,
      "current_hop": 2,
      "status": "active",
      "hop_genealogy": [
        {
          "hop": 1,
          "pattern": null,
          "queries": ["..."],
          "sources_found": 12,
          "sources_kept": 7,
          "ended_at": "2026-05-26T14:25:00Z"
        },
        {
          "hop": 2,
          "pattern": "entity_expansion",
          "from": "Flock Safety",
          "queries": ["..."],
          "sources_found": 8,
          "sources_kept": 5,
          "ended_at": "2026-05-26T14:28:30Z"
        }
      ],
      "confidence_history": [0.42, 0.71],
      "contradiction_rate": 0.18,
      "seen_urls": ["...", "..."]
    }
  ],
  "replan_count": 0,
  "user_decisions": [],
  "usage": {
    "haiku": {"calls": 0, "in_tokens": 0, "out_tokens": 0},
    "sonnet": {"calls": 0, "in_tokens": 0, "out_tokens": 0},
    "opus": {"calls": 0, "in_tokens": 0, "out_tokens": 0},
    "ollama": {"calls": 0}
  }
}
```

On schema mismatch (any in-flight run with `version != 3`), drop quietly with one-line message: `"Your in-flight run was on an older schema (v2) and has been abandoned. Run /research to start fresh."`

### Intermediate file layout per hop

```
{vault}/.research-workflow/state/
  current_run.json
  research_plan.json
  search_context_hop1.json
  fetch_results_hop1.json
  summaries_hop1.json
  search_context_hop2.json
  fetch_results_hop2.json
  summaries_hop2.json
  ...
  classification.json
  written_notes.json
```

`state.py.archive_run()` extended to sweep all per-hop intermediate files into `state/archive/{run_id}/` alongside the main state file. Single sweep, no orphans. Abandoned runs go through the same path with `abandoned: true` marker.

### Topic-resolver output (Sonnet)

```json
{
  "project": "SC County ALPR Research",
  "strategy": "unified",
  "shared_context_files": ["..."],
  "topics": [
    {
      "topic": "Greenville County ALPR program",
      "mode": "web_research",
      "depth": "standard",
      "existing_urls": [],
      "related_vault_notes": ["..."]
    }
  ],
  "local_sources": [],
  "thread_pulls": [],
  "execution_order": "tier_1_first",
  "estimated_usage": { "...": "..." }
}
```

Strategy classification rules (in resolver prompt):
- `planning_only`: clear single topic with specific terms (bill number, named entity, specific question)
- `intent_planning`: single topic with ambiguous terms OR batch with ambiguous shared intent
- `unified`: multi-topic batch with clear individual topics, OR thread-pull, OR mixed-source (local files + topics)

Depth assignment signals (resolver prompt):
- Words like "deeply", "thoroughly", "comprehensive" → `deep` or `exhaustive`
- Words like "quickly", "scan", "brief", "just" → `quick`
- Topic specificity: named bill / specific incident → `standard` or `deep`; broad theme → match user signals
- Default (no signal): `standard`

### Search-agent output (per topic per hop)

```json
{
  "topic": "...",
  "depth": "standard",
  "hop": 2,
  "queries_used": ["..."],
  "selected_urls": [
    {
      "url": "https://sled.sc.gov/...",
      "title": "...",
      "snippet": "...",
      "relevance_score": 0.82,
      "credibility_score": 0.95,
      "tier": "T1",
      "is_primary": true,
      "primary_type": "agency_data",
      "reason": "..."
    }
  ],
  "rejected_urls": [...]
}
```

`primary_type` enum: `agency_data | legal_record | foia | official_statement | peer_reviewed | null` (null when `is_primary == false`).

### Hop-planner output

```json
{
  "topic": "SC ALPR programs",
  "current_hop": 2,
  "decision": "continue",
  "confidence_score": 0.68,
  "contradiction_rate": 0.22,
  "next_hop": {
    "pattern": "causal_chain",
    "from": "Flock Safety federal data sharing",
    "rationale": "Multiple sources reference federal sharing arrangements but no source provides the actual agreements.",
    "candidate_score": {
      "frequency": 3,
      "novelty": 3,
      "connectedness": 1,
      "specificity": 2,
      "total": 9
    },
    "runner_up_alternatives": [
      {"pattern": "temporal_progression", "from": "SC ALPR adoption history", "total": 6}
    ]
  },
  "self_reflection": "Confidence is below target (0.68 vs 0.7). Source diversity is good but we lack primary sources on federal sharing specifically. Following causal_chain on that entity is the highest-value next step."
}
```

`decision` enum: `continue | stop | replan`. `next_hop` is `null` when `decision == "stop"`.

### Classify-agent additions

```json
{
  "topic": "...",
  "notes_to_create": [...],
  "vault_context": {...},
  "contradictions_detected": [
    {
      "claim_a": "Flock Safety shares data with DHS via formal agreement",
      "claim_b": "Flock Safety claims no formal federal sharing agreements exist",
      "source_a": "https://...",
      "source_b": "https://...",
      "tier_a": "T2",
      "tier_b": "T2",
      "nature": "factual"
    }
  ]
}
```

`nature` enum (v1, may expand): `factual | interpretive | temporal | jurisdictional`.

### Note frontmatter

```yaml
---
title: "Greenville County ALPR Surveillance"
tags: [research, surveillance, greenville-sc]
source: ["https://...", "https://..."]
created: 2026-05-26
write_model: sonnet                                                      # hidden via CSS
research_run: 2026-05-26-sc-alpr-batch                                   # hidden via CSS
confidence: 0.78                                                          # visible
contradictions_noted: false                                               # visible
primary_sources: 2                                                        # visible
hop_genealogy: ["entity_expansion(Flock Safety)", "causal_chain(federal sharing)"]  # hidden via CSS; omitted on single-hop runs
---
```

### Body callouts (write stage)

Low-confidence runs (user chose "continue anyway"):

```markdown
> ⚠ **Research confidence: 0.52**. Several topics in this run did not reach the standard confidence target. Verify claims before citing.
```

Notes with contradictions involving this note's sources:

```markdown
> ⚠ **Source contradictions noted.** Two sources disagree on [topic]. See `## Sources` section for details.
```

The contradiction callout's body content is rendered from the classify-agent's `contradictions_detected` entries matched to this note's `source_urls`.

### Depth profiles (constants in `confidence.py`)

| Depth | Max hops | Target sources | Confidence target |
|---|---|---|---|
| `quick` | 1 | 10 | 0.6 |
| `standard` | 3 | 20 | 0.7 |
| `deep` | 4 | 40 | 0.8 |
| `exhaustive` | 5 | 50 | 0.9 |

Time budgets dropped — hops × sources are the ceilings.

### Confidence formula (in `confidence.py`)

```python
def compute_confidence(topic_state) -> float:
    sources = topic_state["all_sources"]   # union across hops

    tier_diversity_weight = weighted_avg(
        sources,
        weights={"T1": 1.0, "T2": 0.75, "T3": 0.5, "T4": 0.25}
    )
    topic_coverage = (
        1.0 if count_sources_at(sources, min_tier="T2") >= 3 else
        count_sources_at(sources, min_tier="T2") / 3
    )
    primary_source_presence = min(1.0, count_primary(sources) / 2)
    source_count_adequacy = min(1.0, len(sources) / depth_target(topic_state["depth"]))

    return (
        0.4 * tier_diversity_weight +
        0.3 * topic_coverage +
        0.2 * primary_source_presence +
        0.1 * source_count_adequacy
    )
```

Contradiction rate:

```python
def compute_contradiction_rate(topic_state, classification) -> float:
    sources = topic_state["all_sources"]
    contradictions = [c for c in classification["contradictions_detected"]
                     if c["source_a"] in sources or c["source_b"] in sources]
    if len(sources) < 2:
        return 0.0
    # contradictions involve pairs; normalize by source pair count
    return min(1.0, len(contradictions) / (len(sources) * 0.3))
```

Triggers:
- Replan if `confidence_score < depth_target(depth)` OR `contradiction_rate > 0.3`
- Stop if `confidence_score >= depth_target(depth)` AND `contradiction_rate <= 0.3`
- Continue otherwise (within hop budget)

### Case JSON schema (Stage B preview, stub-only in Stage A)

```json
{
  "case_id": "2026-05-26-sc-alpr-batch",
  "version": 1,
  "query": "research ALPR programs in Greenville, Spartanburg, Anderson",
  "domain_tags": ["surveillance", "alpr", "south-carolina"],
  "strategy_used": "unified",
  "depths_used": {"standard": 3, "deep": 0, "quick": 0, "exhaustive": 0},
  "hops_executed": 6,
  "confidence_per_topic": {"SC ALPR programs": 0.78, "...": 0.71},
  "contradiction_rate": 0.12,
  "patterns_that_worked": {
    "queries": ["..."],
    "source_tiers": {"T1": 8, "T2": 12, "T3": 3, "T4": 0},
    "hop_chain": ["entity_expansion", "causal_chain"]
  },
  "patterns_that_failed": {
    "queries": ["..."],
    "dead_ends": ["..."]
  },
  "outcomes": {
    "sources_processed": 23,
    "notes_created": 8,
    "notes_updated": 2,
    "user_decisions": []
  }
}
```

In Stage A, `state.py.complete_run()` writes one case file to `{vault}/.research-workflow/cases/{case_id}.json` at completion. Nothing reads it yet. Stage B will add the read path (resolver consults cases at triage time and surfaces learned patterns).

---

## Behavior specifications

### Triage (new Stage 2)

The resolver, on first invocation:

1. Read the user's prompt.
2. Classify into `planning_only` / `intent_planning` / `unified` (rules above).
3. If `intent_planning`: ask up to 3 clarifying questions (single topic) or 1 batch-level question (batch). Update the prompt with the user's answers. Re-classify; usually upgrades to `unified`.
4. Resolve topics (existing logic, now also assigning per-topic depth).
5. Branch on final strategy:
   - `planning_only`: one-line confirm — `"Researching {project} at depth {depth}, {topic_count} topic(s). Proceed? [yes/edit/cancel]"`. `edit` upgrades to full plan view.
   - `unified`: full plan presentation (existing UX with the added depth column).
6. On approval, write `research_plan.json` and proceed to hop loop.

Mid-Q&A crash → run abandoned (Q&A state is too fragile to checkpoint).

### Hop loop (new Stage 4)

Parallelism strategy: **hop-level batching across topics**. For each hop level from 1 to `max(topic.max_hops)`:

1. Collect topics where `current_hop < topic.max_hops AND status == "active"`.
2. Dispatch search agents in parallel (one per active topic at this level, batched by 5).
3. Run fetch + media + summarize for each active topic's hop results.
4. Dispatch hop-planner in parallel (one per active topic at this level).
5. For each topic's hop-planner response:
   - `decision == "continue"`: append next-hop entry to `hop_genealogy`, increment `current_hop`, ready for next hop level.
   - `decision == "stop"`: mark `status = "complete"`.
   - `decision == "replan"`: mark `status = "replan_pending"` (reset to active on quality-gate replan).
6. Per-hop URL dedup at the topic level via `seen_urls` (each topic carries its own set).
7. Cross-topic hop sharing **not enabled** in Stage A (each topic runs independently).

Loop exits when all topics have `status != "active"` or all topics hit `current_hop == max_hops`.

### Hop failure handling

If a hop's search + fetch produces zero usable sources (all duplicates, all failed fetches, all T4):
1. Hop-planner detects this from the hop's outputs.
2. Returns `decision: "continue"` with `next_hop.pattern` set to a different pattern than what just ran. Records this as an "alternate attempt" in genealogy.
3. If the alternate also produces zero usable sources, hop-planner returns `decision: "stop"` with `status = "early_terminated"`. The topic carries its current confidence into the quality gate.

### Quality gate (new Stage 5)

After hop loop completes (or all topics terminated):

1. Compute per-topic `confidence_score` and `contradiction_rate` via `confidence.py`.
2. Aggregate to run-level: `min(confidence_per_topic)` and `max(contradiction_rate_per_topic)`.
3. If aggregate is below threshold:
   - If `replan_count < 2`: trigger auto-replan. Identify weakest topic(s); construct replan hints (which pattern to try, which entity to investigate, which source type is missing); extend the hop loop for those topics with a new hop. Increment `replan_count`.
   - If `replan_count == 2`: present diagnostic prompt to user (see UX below).
4. If above threshold: proceed to classify (Stage 6).

Diagnostic prompt format:

```
⚠ Quality gate triggered after {replan_count} auto-replan attempts.

Topic-by-topic results:
  - SC ALPR programs: confidence 0.52, contradictions 38%
  - Flock Safety contracts: confidence 0.81, contradictions 12%
  - Federal data sharing: confidence 0.41, contradictions 8%

Weakest topics:
  - "SC ALPR programs": only 1 primary source (need 2+); T4 sources dominate
  - "Federal data sharing": insufficient sources (3 found, need 6+ for standard)

Options:
  - replan: try one more cycle with focused hints (1 extension max)
  - continue: write notes anyway, with low-confidence flags
  - abandon: stop here, preserve search/fetch results for inspection
```

User decision recorded in `user_decisions[]`.

`continue` path: run completes, but `low_confidence: true` propagates to:
- All written notes' frontmatter `confidence:` field
- Body callout at top of each note: `> ⚠ Research confidence: {score}. ...`
- Thread-discoverer output flagged as `from_low_confidence_run: true`
- Final Stage 10 summary highlights the user's choice

`abandon` path: archive state with `abandoned_at_gate: true`. No notes written. Search/fetch results preserved for inspection. Case record written (with abandoned flag) for Stage B learning.

### Write stage additions

When `low_confidence == true`: prepend the confidence callout to each note body before the H1 title.

When this note's `source_urls` overlap with any `contradictions_detected[].source_a` or `source_b`: prepend the contradiction callout AND extend the `## Sources` section with contradiction details.

Otherwise: write the note as in v2.

### Stage 10 telemetry

```
Research complete: SC County ALPR Research

Created (8 notes):
  - Projects/Surveillance/South Carolina/Greenville County ALPR.md (confidence 0.83)
  - Projects/Surveillance/South Carolina/Spartanburg County ALPR.md (confidence 0.78)
  ...

Updated:
  - Projects/Surveillance/SC ALPR Overview.md

Hop genealogy:
  Topic: SC ALPR programs (3 hops, confidence 0.83)
    Hop 1: 5 T1, 3 T2 sources found
    Hop 2 (entity_expansion → Flock Safety): 4 T2, 2 T3
    Hop 3 (causal_chain → federal data sharing): 2 T1, 1 T2
  Topic: Flock Safety contracts (2 hops, confidence 0.81)
    Hop 1: 4 T1, 2 T2
    Hop 2 (temporal_progression → 2020-2024): early_terminated (insufficient sources)
    Final confidence carried from hop 1.

Model usage:
  Haiku:   38 calls,  142,000 in /  18,000 out
  Sonnet:  12 calls,   89,000 in /  22,000 out
  Opus:     1 call,    18,000 in /   3,000 out
  Ollama: 142 calls (local — no token cost)

Estimated cost: $0.42

Threads queued for follow-up: 3
  Run /research again to execute these.

Tier: full | Sources fetched: 23 | Notes written: 8 | Replans: 1
```

---

## Error handling

| Scenario | Behavior |
|---|---|
| Crash mid-stage | state.py checkpoint resumes from last completed stage on next `/research` invocation. Schema v3 checkpoints include per-hop position. |
| Crash mid-hop | Resume picks up at the topic's `current_hop` and re-runs the search/fetch/media/summarize/hop-planner sequence for that hop. |
| Crash mid-Q&A (intent_planning) | Run abandoned. Q&A state is too fragile to checkpoint reliably. User reruns `/research`. |
| Schema mismatch on resume | Drop the in-flight run with a one-line message. User reruns. |
| Hop search returns zero results | Hop-planner picks alternate pattern. If alternate also zero, early-terminate that topic. |
| Hop fetch fails for all URLs | Same as above — alternate pattern attempt, then early-terminate. |
| Subagent JSON parse failure | Log warning; treat as zero results from that subagent; continue. |
| Ollama unreachable mid-run | Fall back to Haiku subagent per-article summarization (existing tier fallback path). |
| Playwright unavailable | Skip Playwright fallback; treat Jina failure as fetch failure. |
| User cancellation (Ctrl-C) | state.py last checkpoint is the resume point. No mid-stage state lost beyond the in-progress hop. |
| Quality gate failure after 3 replan attempts | User must choose continue / abandon. Cannot replan further. |
| Mtime conflict on write | Existing behavior — skip the note with warning. |

---

## Migration & cleanup

### Legacy SDK fossil cleanup

In order:

1. Delete `scripts/config.py`.
2. Refactor `scripts/utils.py` — remove `import config`, remove `require_api_key` branch and the `import anthropic` check. If nothing useful remains, delete the file. (`startup_checks()` is called only without args from `vault_lint.py` and `find_broken_links.py`; just inline the vault-path existence check there.)
3. Update `scripts/find_broken_links.py` and `scripts/vault_lint.py` — drop `import config` and `from utils import startup_checks`. Use `config_manager.load_config()` to get the vault path.
4. Update test files — drop `os.environ.setdefault("ANTHROPIC_API_KEY", ...)` from `test_summarize.py`, `test_fetch_and_clean.py`, `test_find_broken_links.py`, `test_vault_lint.py`.
5. Rewrite `scripts/prompts/README.md` to remove stale `claude_pipe.py` and `call_claude()` references; describe the actual current pattern (prompts assembled inline by the orchestrator).
6. Update `CLAUDE.md` to add explicit "no Anthropic SDK, no `claude -p`" rule.

### State schema migration

No formal migration. On `/research` invocation, `state.py.load_run()` checks `version`. If `version != 3`, log `"Your in-flight run was on an older schema and has been abandoned."` and call `abandon_run()` quietly. Then proceed with a fresh run.

### Plugin version

Bump `plugin.json` from `2.0.0` to `3.0.0`. Update marketplace inline copy at `TimSimpsonJr/fieldwork-plugins/research-workflow/` as a follow-up PR after merge.

---

## Testing strategy

All tests offline. No API keys required at any tier.

### New test files

| File | Coverage |
|---|---|
| `tests/test_confidence.py` | Formula math; edge cases (zero sources, all T4, all primary, mixed); contradiction rate normalization; threshold checks per depth. |
| `tests/test_hop_planner.py` | Pattern selection given various source distributions; scoring math (4-factor); continue/stop/replan decisions; early-termination behavior. Mocked summaries as input. |

### Extended test files

| File | New cases |
|---|---|
| `tests/test_state.py` | Schema v3 round-trip; hop genealogy append; usage tracking; abandoned flag; archive sweeps hop intermediate files. |
| `tests/test_fetch_and_clean.py` | Playwright fallback path (mocked); drops `ANTHROPIC_API_KEY` shim. |
| `tests/test_summarize.py`, `tests/test_find_broken_links.py`, `tests/test_vault_lint.py` | Drop `ANTHROPIC_API_KEY` shims. |
| `tests/test_topic_resolver.py` (NEW) | JSON-output contract tests for the new strategy + depth fields. |
| `tests/test_search_agent.py` (NEW) | JSON-output contract tests for `credibility_score`, `tier`, `is_primary`, `primary_type`. |

### Integration test

A new `tests/test_research_skill_integration.py` exercises the full multi-hop pipeline using:
- Pre-recorded subagent responses as fixtures (one fixture file per hop per topic).
- Mock Task dispatcher that returns fixture contents based on agent name + topic + hop level.
- Mocked Jina fetch responses (cached HTML samples).
- Pure-Python confidence calculation (real, not mocked).
- Real state.py writes to a tmpdir.

This validates the orchestrator's hop loop, quality gate, and end-to-end flow without external calls.

---

## Stage B preview (out of scope here, design follows separately)

Pattern learning will be its own design doc and PR, landing as v3.1.0. Sketch:

- Resolver consults `.research-workflow/cases/` at triage time; finds cases by `domain_tags` overlap with the new prompt's signals.
- Surfaces learned patterns: effective queries, source tiers that scored well, hop chains that produced novel notes, time budgets actually consumed.
- Resolver passes these as hints to search-agent and hop-planner.
- An "evolutionary" score on each pattern: increments on success in subsequent runs, decrements on failure, prunes below threshold.

The Stage B design will reuse the `case_schema` already specified here (since Stage A writes case records). No changes to v3.0.0 case writing.

---

## Open implementation questions

Deliberately deferred to the implementation plan (`writing-plans` skill):

1. Exact JSON parsing strategy for the hop-planner response (retry on malformed JSON? validate against a schema?).
2. Whether `utils.py` should be deleted entirely or kept as a stub (depends on what `startup_checks` callers actually need post-refactor).
3. Whether the contradiction callout should auto-link to the contradicting sources via wikilinks (probably yes).
4. Exact fixture format for the integration test (one JSON file per fixture? a single multi-fixture file?).
5. Whether the resolver should run a small vault-index query during triage to inform strategy classification (could improve accuracy on ambiguous prompts).

---

## Out of scope

- Vault retrofit of existing notes to add `confidence` / `contradictions_noted` / `primary_sources` (separate follow-up session).
- Cross-topic hop sharing (Stage B or later).
- Stage B pattern learning details (separate design doc).
- Replacing the in-classify contradiction detection with a more robust signal ([#4](https://github.com/TimSimpsonJr/research-workflow/issues/4)).
- New MCP integrations (Tavily, Context7, Serena).
- Replacing Haiku subagents.
- Changes to the setup wizard beyond the optional CSS-snippet installation.

---

## References

- Advisory input: [`docs/plans/2026-05-26-superclaude-methodology-rework.md`](2026-05-26-superclaude-methodology-rework.md)
- Predecessor design: [`docs/plans/2026-03-05-pipeline-rework-design.md`](2026-03-05-pipeline-rework-design.md)
- Predecessor plan: [`docs/plans/2026-03-05-pipeline-rework-plan.md`](2026-03-05-pipeline-rework-plan.md)
- Current orchestrator: [`skills/research/SKILL.md`](../../skills/research/SKILL.md)
- SuperClaude methodology sources (in `SuperClaude_Framework` repo): `plugins/superclaude/commands/sc-research.md`, `plugins/superclaude/agents/sc-deep-research-agent.md`, `plugins/superclaude/modes/MODE_DeepResearch.md`, `plugins/superclaude/core/RESEARCH_CONFIG.md`
- Follow-up issue: [research-workflow#4](https://github.com/TimSimpsonJr/research-workflow/issues/4)
