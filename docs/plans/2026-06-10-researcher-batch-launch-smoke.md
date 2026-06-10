# research-batch — Launch-Smoke Findings

**Date:** 2026-06-10 · Phase 5 / Task 5.2. The non-negotiable launch-smoke for
`.claude/workflows/research-batch.js` (the dossier lesson: a Workflow artifact is
not "done" until it has been LAUNCHED once — `node -c` + unit-green do NOT
substitute).

## Minimal launch-smoke — PASSED

Launched via the Workflow tool (`scriptPath: .claude/workflows/research-batch.js`)
with an **empty-topics** plan:

```
args = { plan: { project: "launch-smoke", topics: [] },
         config: { vault_root: "test/fixtures/vault", tier: "base" } }
```

Result (run `wf_676c0983-d45`):
```json
{"error":"no_web_research_topics","written_notes":[],"updated_notes":[],"threads":[],"summary":{"topics":0}}
```
`0 agents · 0 subagent tokens · 0 tool uses · 11 ms` — **no runtime/meta error.**

### What this proves (the launch contract — the bug class unit tests miss)
- `export const meta` is a launch-valid **pure literal** (parsed by the runtime).
- The **top-level body is the entry** — `run()` executed and its top-level
  `return` was used (not a defined-but-uncalled default export).
- `args` **normalization** works (object form here; the `typeof args === 'string'`
  JSON.parse branch is present + contract-tested).
- Zero `import`/`require` at runtime; the file loads and runs with no module/fs.
- `run()`'s empty-topics guard returns cleanly before any `agent()` dispatch.

### What it does NOT yet prove (→ Task 5.3, the full e2e)
The empty-topics run returns before dispatching any agent, so these are
**unvalidated by launch**:
- **agentType resolution for the renamed plugin.** The workflow dispatches
  `researcher:search-agent`, `researcher:fetch-summarize-runner`,
  `researcher:hop-planner`, `researcher:thread-discoverer`, `librarian:classify-agent`.
  The Phase-0 spike validated the OLD `research-workflow:` names; the new
  `researcher:` names are **unvalidated** until the plugin is reinstalled under
  the new name and a workflow dispatches them.
- The `agent()` input-fold path with real agents (`callAgent` is byte-identical to
  dossier's proven version + contract-tested, but not launch-exercised here).
- The hop loop / JS confidence-decide-replan over real sources.
- The **Librarian write span** (the skill-using writer — the handoff's open
  question: confirm a workflow subagent can invoke the `librarian` skill cleanly
  and consume the neutral `notes_to_create`).

## Prerequisites for the full e2e (Task 5.3)
1. **Reinstall/reload the plugin as `researcher`** so `researcher:*` agentTypes
   resolve (currently installed as `research-workflow`; the rename's reinstall is
   the documented operator action). Without this, the first `searchAgent` dispatch
   throws "unknown agentType".
2. **`librarian` installed** (the batch write span has no inline fallback).
3. A real **token budget** — the comparable dossier capstone was ~780K tokens /
   ~12 min for a full single-topic crawl; a ~12-topic batch is materially larger.

## DoD status
- [x] **Launch-smoke: launched once, returns without runtime/meta error.** ✅
- [ ] Full e2e (~12-topic fixture batch; agentType resolution; Librarian write
      span) — pending the reinstall + budget above.
