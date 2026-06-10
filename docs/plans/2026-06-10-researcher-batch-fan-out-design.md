# Researcher — Batch Fan-Out Addition + Rename — Design

**Status:** Approved (brainstorm) · **Date:** 2026-06-10
**Repo/plugin:** `research-workflow` → **`researcher`** (rename is Phase 1 of this work)
**Suite:** Fieldwork (beside Magpie, Librarian, prose-craft)

## Summary

Add large-batch capability (30–50+ topics) to the existing research pipeline by reaching for a **small Workflow-tool fan-out script only when a batch exceeds a threshold**, while the skill stays the conversational orchestrator for single/small/interactive runs. **Plugin-first, workflow-as-accelerator.** Also rename `research-workflow` → Researcher to unify the suite.

This is the grain-aligned alternative to the Dossier spike (a self-contained bundled engine), which fought the Workflow runtime — see `../../dossier/docs/plans/2026-06-09-dossier-smoke-findings.md`. Here the workflow is pure orchestration glue over **registered** plugin agents; nothing is inlined and there is no bundler.

## Motivation

Today the resolver has no hard topic cap, but big batches are throttled by the skill's manual "≤5 topics per round" dispatch (SKILL Stage 4a) and the resolver routing large batches to `execution_order: "sequential"`. The user wants to run wider batches. The session established: for single/small the existing plugin is the better fit; the Workflow tool earns its keep **only at batch scale** (structured, auto-queued parallelism + built-in journaling vs. manual batching + the hand-rolled state machine).

## Non-goals

- Not a rewrite — the inline single/small path (Stages 4–10) is **unchanged**.
- Not Dossier's self-contained bundled engine (rejected: fights the runtime).
- Batch path v1 = `web_research` topics. Local-file / thread-pull batches stay on the inline skill path.

## Critical pre-build verification (GATING — Task 0)

The entire design rests on `agent(…, {agentType: '<plugin>:<agent>'})` resolving **registered plugin agents** (researcher's + librarian's) from inside a Workflow. This is **unvalidated** — Dossier inlined everything precisely to avoid depending on registration. **Task 0 is a cheap agentType-resolution spike** (dispatch one researcher agent + one librarian agent by `agentType`, plus a bad-name control). If it does not resolve, the design must change (different delegation mechanism) **before** any build. This is the session's core lesson applied up front: verify the Workflow API by launching, don't assume it.

## Architecture (Approach A — router branch)

1. **`/researcher` skill — one router branch.** After plan-approval, the skill checks topic count vs `THRESHOLD` (default **10**, in vault config). `≤ THRESHOLD` → today's inline Stage 4–10 path, **unchanged**. `> THRESHOLD` → invoke the batch workflow. Small runs never touch new code.

2. **`researcher/.claude/workflows/research-batch.js` — new.** Pure-JS orchestration (~200–300 lines), **no bundler**; references all work via `agentType`, inlines only the small `confidence.js`. Carries the contract lint + a launch-smoke in its DoD.

3. **Agents (all `agentType`, nothing inlined), across two plugins:**
   - *researcher:* `search-agent`, `hop-planner`, `thread-discoverer` (existing) + **one new thin `fetch-summarize-runner`** agent. The workflow body can't run Bash/Python, but the real fetch/summarize logic *is* Python (`fetch_and_clean.py` cache/SSRF/Wayback; `summarize.py` Ollama). The runner wraps those scripts via Bash — **Python infra preserved, dispatched from inside an agent.** It needs the full Python path + `scripts_dir` (from config — the recurring on-PATH friction).
   - *librarian:* `classify-agent`, the writer, `wikilink-scanner` — the canonical write span, via the existing Stage-7.0 neutral-contract handoff, always-on for the batch path. **Hard runtime precondition:** Librarian must be installed; the skill checks availability before taking the batch path and falls back/warns if absent.

4. **Reused from Dossier:** `confidence.js` (test-synced with `confidence.py`), the agent-return JSON schemas, the contract-lint + launch-smoke discipline. **Not** Dossier's prompts — researcher's own agents are canonical. Dossier repo stays as the spike/reference.

5. **State:** the workflow's `runId`-journal handles intra-batch resume; the skill writes a lightweight run record at the two gates only. No bespoke per-topic state machine on the batch path.

### Flow

```
/researcher "…50 topics…"
 └─[skill] Stage 0 (config + tier + vault index) → resolve → PLAN (N topics) → ◇ approve (honest cost estimate)
 └─ N > THRESHOLD?
      ├─ no  → existing inline Stage 4–10  (UNCHANGED)
      └─ yes → Workflow(research-batch), args = {plan, config, vaultDigest, runId}:
                 per-topic hop loop (depth-driven, parallel + auto-queued, budget-capped):
                   search-agent → fetch-summarize-runner
                                 → [deep: hop-planner + JS confidence/decide/replan]
                 → Librarian write span (classify → write → wikilink), per-topic granularity
                 → thread-discoverer
                 ⇒ { written_notes, updated_notes, threads, summary }
 └─[skill] ◇ thread-selection gate → optional next batch
 └─[skill] complete summary
```

## Data flow specifics

- **No bootstrap agent** — the skill already runs Stage 0, so it passes `config` + `vaultDigest` into the workflow via `args`.
- **Hop loop:** quick topics stop at 1 hop; deep topics multi-hop with JS `computeConfidence`/`decide`/replan, auto-replanning low-confidence topics to `budget` (no gate). Chunked to the concurrency cap so 50 topics auto-queue.
- **Write span → Librarian:** summaries → Librarian `classify-agent` (neutral `notes_to_create`, **per-topic granularity preserved; minor sensible merging allowed**) → Librarian writer → Librarian `wikilink-scanner`. MOC updates must be serialized; confirm Librarian's writer is parallel-safe at ~50-note scale (else the workflow serializes the MOC step).

## Gates & cost posture

- Up-front **plan-approval** with an honest estimate (topics × depth → ~agents / tokens / time / $). Final **thread-selection** gate. No mid-run gates; quality auto (low-confidence flagged inline, never gated).
- **No hard deep-topic cap.** `budget` primitive as a hard ceiling; the thread-selection gate is the don't-compound backstop against multi-round escalation. Revisit if usage limits bite.

## Decisions (settled)

| Decision | Choice |
|---|---|
| Shape | mixed depth per topic; workflow runs the full hop loop |
| Span | research + write fan-out; write delegated to Librarian |
| Gates | approve up front + thread-selection only; quality auto |
| Deep cap | none; budget ceiling + thread gate backstop |
| Granularity | ~per-topic notes; minor merging OK |
| Packaging | `agentType`, no inlining/bundler |
| Threshold | default 10, vault-config |
| Confidence | `confidence.js` (workflow) + `confidence.py` (skill), shared test vectors |
| Command/skill | full rename → `/researcher`, `/researcher-setup` |

## Phases (detail in the impl plan)

- **Phase 0 — agentType spike (GATE).** Verify plugin-agent resolution inside a workflow.
- **Phase 1 — Rename** `research-workflow` → `researcher`, atomic + verified: GitHub `gh repo rename` + local remote; `plugin.json` (id `researcher`, display "Researcher"); skills `research`→`researcher`, `research-setup`→`researcher-setup`; commands `/researcher`(+setup); Fieldwork `marketplace.json` pointer; README/CLAUDE.md; every internal `research-workflow` ref + `{{REPO_ROOT}}` usage; **librarian dependency declaration**; **vault `.research-workflow/` → `.researcher/` migration** (rename-on-first-run + back-compat check); **external-ref audit** (other suite plugins, installed config, the operator's memory files); MANIFEST regen.
- **Phase 2 — Resolver de-throttle.** `execution_order` becomes advisory; the skill's threshold-branch decides routing (`> THRESHOLD` always parallel workflow); audit + remove any implicit topic ceiling so a 50-topic prompt resolves to 50 topics.
- **Phase 3 — `research-batch.js`.** The hop loop (agentType: search / fetch-summarize-runner / hop-planner + JS confidence) + Librarian write span + thread-discoverer.
- **Phase 4 — Skill integration.** Router branch + the two gates + honest cost estimate + `budget` ceiling + Librarian-availability check.
- **Phase 5 — Tests/DoD.** `confidence.js` tests (synced to the Python cases); contract lint on the workflow; **launch-smoke against a fixture vault (non-negotiable)**; one ~12-topic end-to-end fixture batch; validate `fetch-summarize-runner` drives the Python scripts.

## Error handling

Keep-going (`.filter(Boolean)`); per-agent failures collected into `summary.failures`; abort if every topic fetches zero sources. Low-confidence flagged inline.

## Definition of done

- Phase 0 spike passed (agentType resolves) — or the design was revised.
- Rename complete + verified; existing-vault state migrated; no stale `research-workflow` refs.
- `> THRESHOLD` batches route to the workflow and run a real fixture batch end-to-end.
- `confidence.js` synced + tested; contract lint clean; **the workflow has been launched at least once and returned without runtime/meta error.**
- Inline single/small path byte-for-byte unchanged. Librarian-absent path degrades gracefully.
