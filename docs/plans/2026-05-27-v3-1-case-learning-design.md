# v3.1.0 — Case-Based Pattern Learning Design

**Status:** Design approved 2026-05-27. Implementation plan to follow (writing-plans skill).
**Target release:** v3.1.0
**Predecessor:** [v3.0.0 SuperClaude methodology rework](2026-05-26-superclaude-methodology-rework-design.md) — Stage B preview section is the starting point for this doc.

---

## 1. Why this design exists

v3.0.0 already writes a case record at the end of every research run (`scripts/state.py:write_case_record()` called at Stage 10c) to `{vault}/.research-workflow/cases/{run_id}.json`. The reader was deferred. This document designs that reader, plus the surrounding machinery for **evolutionary pattern learning** — accumulating observations across runs, promoting them to durable rules under user approval, and surfacing them to downstream subagents at run time.

The model is **prose-craft's learning loop**, adapted to research-workflow's signals:

- Prose-craft accumulates observations from user manual edits to generated text (a strong ground-truth signal).
- Research-workflow accumulates observations from case records — run-level outcome metrics (confidence, contradiction rate, user accept/replan/abandon) plus per-case statistical signatures (source tier distributions, hop pattern → confidence delta, query template recurrence).
- Prose-craft promotes graduated observations into rule files (registers, SKILL.md, prose-review.md).
- Research-workflow promotes graduated observations into a **separate** `learned_patterns.md` file the orchestrator injects at run time. **Agent definition files (`search-agent.md`, `hop-planner.md`, `classify-agent.md`) stay untouched in v3.1.0.**

Why split? Research-workflow lacks prose-craft's strong ground-truth signal. Our outcome signals are noisier proxies for "did this work." Editing core agent prompts based on noisy proxies is too aggressive for v3.1.0 — and creates a multi-agent credit-assignment problem (when a run scores well, which agent's prompt earned the credit?). v3.2.0 may revisit this with SkillOpt-style validation discipline once `learned_patterns.md` has earned trust over months of use.

## 2. Scope summary

| Item | Decision |
|---|---|
| Pattern storage (graduated) | `learned_patterns.md` — markdown, orchestrator-injection-friendly |
| Candidate storage | `accumulator.json` — JSON, analyzer-friendly |
| Pattern source | Case records + analyzer pass at end of every run |
| Analyzer | Hybrid: heuristic Python (bulk aggregation) + Haiku subagent (semantic compare only) |
| Promotion ceremony | User-approved at Stage 10c when analyzer flags eligible candidates |
| Injection point | Orchestrator at each subagent dispatch — search-agent (Stage 4a), hop-planner (Stage 4e), classify-agent (Stage 6) |
| Scoring | Run-level W/L per applied pattern. Win = avg confidence ≥ target AND no abandon AND contradiction_rate ≤ 0.3 |
| Demotion | `W:L < 0.4 AND uses ≥ 5` → back to accumulator with raised re-graduation bar. 2nd demotion → permanent `rejected`. |
| Contradiction handling | At promotion time, analyzer checks for semantic conflict in same `domain × target_stage`. User resolves at graduation prompt. |
| Bootstrap | Forward-only — no v3.0.0 cases exist yet. Analyzer is silent until cases accumulate. |
| Out of scope (v3.1.0) | Editing agent definition files; mid-run pattern reload; bulk backfill; A/B testing of patterns |

## 3. Architecture

Three pieces of persistent state under `{vault}/.research-workflow/`:

- **`cases/{run_id}.json`** — per-run records. Append-only, kept indefinitely. Written by v3.0.0; v3.1.0 adds an `applied_patterns: [pattern_id, ...]` field.
- **`accumulator.json`** — candidate patterns observed but not yet promoted. Holds `sessions_seen`, `sessions_since_last_seen`, `evidence` list, and `status` (`hold` / `rejected` / `promotion_pending`).
- **`learned_patterns.md`** — graduated patterns. Human-readable markdown, grouped by domain → stage. Each entry carries W/L score, promotion date, and demotion counter.

Three new behaviors get added to the pipeline:

- **Stage 2 (after triage)** — orchestrator loads `learned_patterns.md`, filters entries by `domain_tags` overlap with the run's prompt, groups by `target_stage`. The filtered set rides along through the rest of the pipeline as injection context.
- **Each subagent dispatch (Stage 4a / 4e / 6)** — orchestrator appends a `## Learned Patterns` block to the user prompt for that subagent, pulling stage-relevant entries from the filtered set. Records `pattern_id`s used into a run-level `applied_patterns` set.
- **Stage 10b (after case write)** — new analyzer step runs. Heuristic Python pass over recent cases + accumulator state, score updates for `applied_patterns` (read from the just-written case), demotion sweep, candidate detection (optional Haiku for semantic compare), accumulator update. If any candidates crossed promotion threshold → **Stage 10c graduation prompt**.

Nothing about agent definition files (`search-agent.md`, etc.) changes. **v3.1.0 is purely additive** — with empty `accumulator.json` and `learned_patterns.md`, the pipeline behaves identically to v3.0.0.

## 4. Data flow

```
Run starts:
  └─ Stage 2 (Resolver):
     ├─ Load learned_patterns.md
     ├─ Filter by domain_tags overlap with prompt → relevant
     ├─ Group by target_stage → relevant_by_stage
     └─ Carry relevant_by_stage as context through the pipeline

Run executes:
  └─ At each subagent dispatch (Stage 4a search / 4e hop-planner / 6 classify):
     ├─ Orchestrator builds user prompt as usual
     ├─ Appends ## Learned Patterns block with relevant_by_stage[that_stage]
     ├─ Records pattern_ids used → run-level applied_patterns set
     └─ Dispatches to subagent via Task tool

Run completes:
  └─ Stage 10a: complete_run() writes case JSON, now including applied_patterns: [...]
  └─ Stage 10b (analyzer):
     ├─ Read just-written case + recent N cases
     ├─ Read current accumulator
     ├─ For each pattern_id in case.applied_patterns:
     │   ├─ Compute run-level outcome (W or L)
     │   └─ Update learned_patterns.md score for that pattern
     ├─ Demotion sweep:
     │   ├─ Any graduated patterns where W:L < 0.4 AND uses ≥ 5?
     │   ├─ First demotion → back to accumulator (status=hold, raised_bar=true)
     │   └─ Second demotion → status=rejected (permanent)
     ├─ Candidate detection (heuristic Python):
     │   ├─ Aggregate signals across recent cases
     │   ├─ Compare to existing accumulator entries
     │   └─ Haiku dispatch only if semantic compare needed
     │       (on timeout: treat candidate as distinct — conservative default)
     ├─ Accumulator update:
     │   ├─ New observations → status=hold, sessions_seen=1
     │   ├─ Existing observations recurring → increment sessions_seen, reset sessions_since_last_seen
     │   └─ Existing not recurring → increment sessions_since_last_seen
     └─ Promotion eligibility check:
        ├─ Any hold entries crossed threshold (sessions_seen ≥ 3, or ≥ 5 if raised_bar)?
        ├─ Contradiction check vs. already-graduated in same domain × target_stage
        └─ Mark eligible entries promotion_pending=true → continue to Stage 10c
  └─ Stage 10c (graduation prompt — only if eligible candidates exist):
     ├─ For each candidate:
     │   ├─ Show pattern body + evidence table (case_ids + signals)
     │   ├─ Show contradiction warning if applicable
     │   └─ Ask: promote / reject / hold
     ├─ For "promote":
     │   ├─ Write learned_patterns.md entry FIRST (atomic)
     │   ├─ Then accumulator: clear promotion_pending, remove from candidates (atomic)
     │   └─ Cross-file transaction: if accumulator write fails, next-run analyzer dedupes
     │       by checking learned_patterns.md before re-proposing
     ├─ For "reject":
     │   └─ Accumulator: status=rejected, clear promotion_pending (sticky — never re-proposed)
     ├─ For "hold":
     │   └─ Accumulator: clear promotion_pending only (keep at hold for future evidence)
     └─ Aborted prompt (Ctrl+C, dismissal, network hiccup):
        └─ promotion_pending stays set in accumulator
           → next-run Stage 10c re-prompts when analyzer detects the flag still set
```

## 5. Schemas

### 5.1 Case JSON (v3.1.0 additive change)

Existing v3.0.0 fields unchanged. One new field:

```json
{
  "applied_patterns": [
    "civic-alpr-t1-dominance-3f7a",
    "tech-entity-expansion-h2-9c2b"
  ]
}
```

Empty list (`[]`) when no patterns were surfaced this run. v3.0.0 cases missing this field are treated as `[]` (forward-compat — though moot since no v3.0.0 cases exist yet).

### 5.2 accumulator.json

```json
{
  "version": 1,
  "entries": [
    {
      "pattern_id": "civic-alpr-t1-dominance-3f7a",
      "name": "T1 sources dominate for civic ALPR queries",
      "category": "source-tier-bias",
      "target_stage": "search",
      "domain_tags": ["civic", "alpr"],
      "sessions_seen": 3,
      "sessions_since_last_seen": 0,
      "status": "hold",
      "raised_bar": false,
      "promotion_pending": false,
      "demotion_count": 0,
      "evidence": [
        {"case_id": "2026-05-22-alpr-charleston", "signal": "T1=6/9, conf=0.79"},
        {"case_id": "2026-05-25-alpr-greenville", "signal": "T1=8/12, conf=0.84"},
        {"case_id": "2026-05-27-alpr-columbia", "signal": "T1=7/10, conf=0.81"}
      ],
      "proposed_promotion_body": "T1 sources dominate: government sites, fusion center reports, ACLU policy memos.",
      "created_at": "2026-05-22T10:14:00Z",
      "last_updated_at": "2026-05-27T15:30:00Z"
    }
  ]
}
```

**Status values:**
- `hold` — accumulating evidence; not yet eligible for promotion
- `promotion_pending` — analyzer flagged it; user hasn't decided yet (or graduation prompt was aborted)
- `rejected` — user rejected promotion, or pattern hit permanent retirement after 2 demotions; never re-proposed

**`pattern_id` format:** `slug(domain) + "-" + slug(category) + "-" + short_hash(name + created_at)`. The hash guards against ID collisions when similar-sounding patterns emerge with the same domain/category.

**`raised_bar`:** `false` initially. Set to `true` after first demotion. Re-graduation requires `sessions_seen ≥ 5` instead of `≥ 3`.

### 5.3 learned_patterns.md

```markdown
---
version: 1
---

## civic / alpr

### Search patterns

- **T1 sources dominate** — government sites, fusion center reports, ACLU policy memos.
  - id: `civic-alpr-t1-dominance-3f7a`
  - score: 12W / 1L (13 uses)
  - promoted: 2026-04-15
  - demotions: 0

### Hop planning patterns

- **entity_expansion at hop 2** — typically lifts confidence 0.5→0.75 for SC topics.
  - id: `civic-alpr-entity-h2-9c2b`
  - score: 5W / 1L (6 uses)
  - promoted: 2026-05-02
  - demotions: 0

## technical / general

### Search patterns

- **Prefer preprints + official docs** — arXiv, RFC, vendor docs outweigh blog posts.
  - id: `tech-general-preprints-2d4f`
  - score: 9W / 2L (11 uses)
  - promoted: 2026-04-20
  - demotions: 0
```

**Grouping:** Top-level `##` heading is `domain1 / domain2 / …` (joined with `/` from `domain_tags`). Sub-headings are `### {target_stage} patterns`. Entries are bulleted with bold name, em-dash description, and indented metadata.

**Parsing:** Tolerant — orchestrator parser skips any entry missing `id` or `score` and logs the skip rather than crashing.

## 6. Components

### 6.1 Analyzer (new)

**Python module:** `scripts/case_analyzer.py`

Main entry point:
```python
def analyze(
    case_path: Path,
    accumulator_path: Path,
    learned_patterns_path: Path,
    cases_dir: Path,
    cases_window: int = 20,
    haiku_dispatch: Callable | None = None,
) -> AnalyzerResult:
    ...
```

Responsibilities:
1. **Score updates** — for each `pattern_id` in `case.applied_patterns`, compute run-level outcome (W/L per Section 2 scoring rule) and update `learned_patterns.md`.
2. **Demotion sweep** — any graduated patterns where `W:L < 0.4 AND uses ≥ 5`? First demotion sends them back to accumulator with `raised_bar=true`; second demotion flips them to `status=rejected`.
3. **Candidate detection** (pure-Python heuristic) — aggregate signals across recent cases:
   - Source tier distributions per domain
   - Hop pattern → confidence delta per hop position
   - Query template recurrence (simple token overlap)
   - Cross-source classify decisions
4. **Compare candidates to accumulator** — direct comparison first (same `pattern_id` exists?). If candidate is *similar* but not identical to an existing entry, optionally dispatch Haiku for semantic compare (with 30s timeout — on timeout treat candidate as distinct).
5. **Accumulator update** — increment `sessions_seen` / `sessions_since_last_seen` appropriately, add new evidence rows, record new candidates.
6. **Promotion eligibility** — flag entries crossing the threshold with `promotion_pending=true`, plus contradiction check against already-graduated patterns in the same `domain × target_stage` bucket.
7. **Return** — `AnalyzerResult` with: list of eligible candidates for the graduation prompt, list of warnings (contradictions, Haiku timeouts, parser errors).

**Haiku subagent:** `agents/case-analyzer.md`

- **Input:** candidate observation body + existing accumulator entry body
- **Output:** structured JSON: `{"is_same": bool, "reason": "..."}`
- **Bounded prompt** — fits in a few KB max. No multi-turn reasoning.

### 6.2 Orchestrator extensions

**`skills/research/SKILL.md`** — three stages get additions:

- **Stage 2 (after triage):**
  - Load `learned_patterns.md` (markdown parser, tolerant)
  - Filter entries by `domain_tags` overlap with run's prompt
  - Group by `target_stage` → `relevant_by_stage = {"search": [...], "hop_planner": [...], "classify": [...]}`
  - Carry through pipeline as injection context

- **Stage 4a / 4e / 6 (subagent dispatches):**
  - When building subagent user prompt, append `## Learned Patterns` block from `relevant_by_stage[that_stage]` if non-empty
  - Record dispatched `pattern_id`s into the run-level `applied_patterns` set
  - At end of run, `applied_patterns` gets folded into the case record (Stage 10a)

- **Stage 10b/10c (new):**
  - 10b: dispatch analyzer via Bash (`python scripts/case_analyzer.py ...`)
  - 10c: if analyzer returned any promotion-eligible entries → run graduation prompt loop

### 6.3 State extensions

**`scripts/state.py`:**

- Helper for accumulating `applied_patterns` during a run (set updated at each dispatch, persisted to current run state)
- Atomic write helpers for `accumulator.json` and `learned_patterns.md` (reuse existing `_atomic_write` pattern)
- Lock acquisition helper (`acquire_state_lock()`) — wraps the shared-state write pair with a `.lock` file in `.research-workflow/`, 5s timeout

## 7. Error handling

### Atomic writes
`accumulator.json` and `learned_patterns.md` use the same temp-file-then-rename pattern as `state.py:_atomic_write`. No partial writes survive a crash.

### Cross-file transactional update
Promotion touches both files. Write order:

1. `learned_patterns.md` first (with new entry)
2. `accumulator.json` second (clear `promotion_pending`, remove from candidates)

If step 2 fails, the pattern exists in both files. Next-run analyzer detects duplicates by checking `learned_patterns.md` IDs before re-proposing accumulator entries. No corruption, no lost graduations.

If step 1 fails, `promotion_pending` stays set in accumulator. Next-run Stage 10c re-prompts.

### Concurrency lock
A simple `.research-workflow/.lock` file (containing PID + ISO timestamp) is acquired around the shared-state write pair. Acquisition fails fast (5s timeout) with a clear error if another `/research` run holds the lock.

Stale lock detection: if the holding PID is dead AND the timestamp is older than 1 hour, the lock is considered stale and cleared.

### Schema versioning
- `accumulator.json` top-level `version: 1`
- `learned_patterns.md` YAML frontmatter `version: 1`

Version mismatch logs a clear error and continues with empty state (graceful degradation — pipeline still runs, just without learned patterns this round). Auto-migration happens for known version bumps.

### Tolerant parser for learned_patterns.md
Orchestrator parser logs and skips malformed entries (missing `id`, malformed score line, unrecognized section heading) instead of crashing. One bad entry doesn't kill the run.

### Corrupt accumulator detection + rebuild
If `accumulator.json` fails JSON parsing or schema validation, log loudly and prompt the user at Stage 10b to confirm rebuild.

- **Rebuild** = re-run heuristic pass over all cases, reconstruct candidate entries.
- **Warning:** rebuild loses any prior `rejected`-status flags. User must re-reject patterns as they're re-proposed.

### Analyzer failures are non-fatal
If the heuristic pass crashes OR the Haiku dispatch times out, the run completes anyway. The error is logged into the run's state telemetry. The case is still written; the analyzer just doesn't update the accumulator this round.

### Haiku timeout fallback
Hard 30s timeout on semantic-compare Haiku dispatch. On timeout, the analyzer treats the candidate as **distinct** from the existing accumulator entry (conservative — adds a new entry rather than risking a wrong merge that conflates two patterns). Logged as a warning in state telemetry.

### Empty-state handling
First run with no `accumulator.json`, no `learned_patterns.md`, and no `cases/` directory: analyzer skips silently, no graduation prompt, pipeline behaves exactly like v3.0.0.

### Promotion-pending interruption
If the user `Ctrl+C`s, dismisses, or otherwise aborts the graduation prompt at Stage 10c, `promotion_pending` stays set on the accumulator entry. Next-run analyzer sees the flag still set and re-prompts at the next Stage 10c.

To explicitly defer indefinitely, the user picks `hold` at the prompt — this clears `promotion_pending` without deciding promote/reject, returning the entry to plain `hold` status.

## 8. Testing

All tests offline. No API keys, no real Ollama calls, no real Haiku subagent dispatches.

### 8.1 New test files

| File | Coverage |
|---|---|
| `tests/test_accumulator.py` | Schema round-trip (read/write). `sessions_seen` / `sessions_since_last_seen` increment logic. `rejected`-set persistence — rejected patterns never re-proposed. Demotion counter (1st → back to `hold`, 2nd → permanent `rejected`). Atomic write under simulated mid-write crash. |
| `tests/test_pattern_detection.py` | Heuristic candidate detection over fixture cases. T1 dominance for civic domain. Hop chain bias (entity_expansion preferred for tech topics). Query template recurrence. No LLM dispatch — pure Python aggregation. |
| `tests/test_score_updates.py` | W/L computation: run-level outcome → +1 or -1. Demotion threshold (`W:L < 0.4 AND uses ≥ 5` → demoted). Permanent retirement after 2nd demotion. Edge cases: zero uses, all-wins, all-losses, tied W:L. |
| `tests/test_learned_patterns_parser.py` | Markdown round-trip (read, parse, modify, write back, verify identity). Tolerant skip on malformed entries (missing `id`, mangled score line, unrecognized heading). Version mismatch handling. |
| `tests/test_case_analyzer_contract.py` | Haiku semantic-compare subagent contract. Input/output shape verification with fixture. Mocked at the Bash layer — no real Haiku calls. |
| `tests/test_pattern_evolution.py` | **Multi-run trajectory integration test.** Drive analyzer through N synthesized runs in sequence. Verify full state machine lifecycle (see below). |

### 8.2 Extended test files

| File | New coverage |
|---|---|
| `tests/test_state.py` | `applied_patterns` field round-trip. Lock acquisition + release. Stale-lock detection. Cross-file transactional write (learned_patterns first, accumulator second). |
| `tests/test_research_state_mechanics.py` | Stage 10b/10c integration: full sequence `complete_run` → analyzer → accumulator write → graduation prompt → learned_patterns write. Re-graduation with raised bar. Promotion-pending interruption + re-prompt on next run. |

### 8.3 Multi-run trajectory integration test (`test_pattern_evolution.py`)

The high-value test. Drives the analyzer through a sequence of synthesized cases and verifies the full pattern lifecycle:

| Run | Expected state |
|---|---|
| 1 | Observation appears, accumulator gains entry with `sessions_seen=1`, status `hold` |
| 2 | Same observation, `sessions_seen=2` |
| 3 | `sessions_seen=3` → promotion eligible → user promotes → entry moves to `learned_patterns.md` |
| 4-7 | Pattern earns wins (run outcomes positive) |
| 8-12 | Pattern earns losses (run outcomes negative) → 1st demotion threshold hit → back to accumulator with `raised_bar=true`, `demotion_count=1` |
| 13-17 | Pattern observed again, `sessions_seen` builds back up. Promotion bar is now 5, not 3. |
| 18 | `sessions_seen=5` (raised bar) → promotion eligible again → user promotes |
| 19-23 | More losses → 2nd demotion → status flips to `rejected` (permanent) |
| 24+ | Observation recurs in new cases but is never re-proposed (rejected sticky) |

### 8.4 Backward-compat empty-state test

Pipeline runs with no accumulator file and no `learned_patterns.md`. Verify:
- Analyzer is silent (no error, no warning)
- No graduation prompt appears
- Run completes identically to v3.0.0 (same state shape, same outputs)

### 8.5 Pattern injection contract test

Verify orchestrator's prompt-assembly logic at Stage 4a / 4e / 6:
- Correctly filters `learned_patterns.md` entries by `domain_tags` overlap
- Groups by `target_stage` correctly
- Injects `## Learned Patterns` block at the correct location in the user prompt
- Records `pattern_id`s into the run's `applied_patterns` set

Run as a contract test against the Bash invocations encoded in SKILL.md, not a Python unit test.

### 8.6 Fixture set

`tests/fixtures/case_learning/`:

- `civic_alpr_cases.json` — 6-10 representative civic-domain cases for T1-dominance detection
- `tech_cases.json` — 6-10 technical-domain cases for entity_expansion bias detection
- `contradictory_outcomes.json` — cases producing semantically conflicting candidate patterns (tests contradiction detection at promotion time)
- `sparse_domain.json` — one or two cases — verifies analyzer produces no spurious candidates from thin evidence

## 9. Tuneable defaults

These are knobs that may move once we have real usage data. Defaults proposed:

| Knob | Default | Rationale |
|---|---|---|
| Promotion threshold (first graduation) | `sessions_seen ≥ 3` | Prose-craft spirit: once is curiosity, twice is interest, three times is a rule |
| Promotion threshold (re-graduation after demotion) | `sessions_seen ≥ 5` | Higher bar prevents ping-pong |
| Demotion trigger | `W:L < 0.4 AND uses ≥ 5` | Need enough uses for the ratio to be meaningful |
| Permanent retirement | 2nd demotion | Strict but reversible only by manual file edit |
| Accumulator staleness pruning | `sessions_since_last_seen > 5` | Prose-craft default; piece-specific candidates expire |
| Analyzer recent-cases window | `max(20, last 60 days)` | Bounded for performance; broader window for sparse vaults |
| Haiku dispatch timeout | 30s | Defensive; conservative-distinct fallback on timeout |
| Lock acquisition timeout | 5s | Concurrent `/research` runs should be rare; fail-fast is better than queue |
| Stale-lock detection | PID dead OR timestamp > 1hr | Recovers from crashes |

## 10. Out of scope for v3.1.0

- **Editing agent definition files** — deferred to v3.2.0. By then `learned_patterns.md` will have earned trust and we'll have data on how to fold patterns into agent prompts safely.
- **Mid-run pattern reload** — patterns load once at Stage 2 and stay static through the run. Hops may reveal new domains, but reloading would be expensive and inconsistent. Patterns relevant to a discovered domain surface in the *next* run.
- **Bulk backfill command** — no v3.0.0 cases exist yet, so unnecessary at ship time. Add later if a user accumulates cases via long pipeline runs before installing v3.1.0.
- **A/B testing of patterns** — some runs include a pattern, some don't, compare outcomes. Solves the credit-assignment problem (a learned pattern might be earning wins from baseline agent behavior, not from itself). Too much machinery for v3.1.0; revisit for v3.2.0.
- **`/research-learn status` command** — inspect accumulator + learned patterns interactively. Useful affordance, not a v3.1.0 blocker.
- **Property-based / hypothesis-style tests** — defer.
- **Per-hop pattern recording** — only run-level scoring for now.
- **Cross-vault learning** — patterns stay vault-local. Multi-vault aggregation is a separate design question.

## 11. Open items for the implementation plan

- New agent file `agents/case-analyzer.md` — exact system prompt for the Haiku semantic-compare role
- Exact markdown format for the `## Learned Patterns` block injected into subagent prompts
- Stale-lock detection mechanics — PID checking on Windows specifically
- Schema migration path if `accumulator.json` ever bumps to v2 (defer the design; only matters when we need it)

The implementation plan will resolve these and produce the per-phase task breakdown.

---

**Next step:** `writing-plans` skill builds the implementation plan from this design.
