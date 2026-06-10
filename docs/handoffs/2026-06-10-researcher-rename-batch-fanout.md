# Handoff: Researcher rename + batch fan-out

**Date:** 2026-06-10
**Project:** research-workflow → **researcher** (Fieldwork suite)
**Status:** Design + plan complete and committed. Phase 0 gate passed. Next session = EXECUTE.

---

## What We Did

Explored whether to give the research pipeline "dynamic workflow" capability. Built a throwaway spike (**Dossier**, a separate repo) that ported the whole pipeline into a single self-contained Workflow-tool engine — it works end-to-end, but the exercise proved that packaging a whole product as one bundled workflow **fights the runtime** (5 launch-contract bugs the unit tests structurally couldn't catch). Concluded: for single/small research the existing plugin is the better fit; the Workflow tool only earns its keep at **batch scale**.

So we designed the **grain-aligned** version: keep `research-workflow` as a plugin, rename it to **`researcher`**, and add a Workflow-tool **batch fan-out** that the skill invokes **only when a batch exceeds a topic threshold**. The workflow is pure orchestration glue over *registered* agents via `agentType` (researcher's research agents + Librarian's write agents) — no inlining, no bundler. Brainstorm → design → plan are done and committed; the gating agentType spike already passed.

## Decisions Made

- **Plugin-first, workflow-as-accelerator** (Approach A): one `/researcher` skill; a router branch sends `> THRESHOLD` (default 10, vault-config) batches to the workflow, everything else to the unchanged inline path. (Rejected: Dossier's workflow-replaces-plugin — loses interactivity/transparency.)
- **Full rename** `research-workflow` → `researcher`, incl. commands `/researcher` + `/researcher-setup` (matches the Librarian pattern; user chose maximum uniformity).
- **Mixed depth per topic** → the workflow runs the full hop loop (needs JS confidence/decision).
- **Research + write fan-out;** write span delegated to **Librarian** (the canonical Magpie-era split). research-workflow's agents do research; Librarian's classify/wikilink via `agentType`, the note-write via a Librarian-**skill**-using agent.
- **Gates:** approve up front (with honest cost estimate) → unattended research+write → thread-selection only. No mid-run gates; quality auto (low-confidence flagged, auto-replan to `budget`). No hard deep-cap (thread gate + budget ceiling are the backstops).
- **Reuse from Dossier:** `confidence.js`, schemas, the launch-contract lint + launch-smoke discipline. **Not** Dossier's prompts (researcher's own are canonical).

## Current State

- `research-workflow` repo: on `master`, clean. Three commits added this session (all on master, docs force-added):
  - `dfc6af3` design doc · `ca37760` spike result · `c7bc0e9` implementation plan
- **Design:** `docs/plans/2026-06-10-researcher-batch-fan-out-design.md`
- **Plan:** `docs/plans/2026-06-10-researcher-batch-fan-out-plan.md` (5 phases, bite-sized tasks)
- **Phase 0 (agentType spike): DONE + PASSED** — `research-workflow:search-agent` and `librarian:classify-agent` both resolve by `agentType` inside a workflow; unknown types throw loudly; **Librarian's note-write is the `librarian` skill, not an agentType.**
- Dossier spike repo (reference, untouched going forward): `../dossier` — its `src/confidence.js`, `src/schemas/index.js`, `build.mjs` Guards, and `docs/plans/2026-06-09-dossier-smoke-findings.md` are the reusable assets.
- Rename scope measured: **59 `research-workflow` refs across 23 files**; vault-dir literal `CONFIG_DIR_NAME=".research-workflow"` (scripts/config_manager.py) + `{{REPO_ROOT}}`/`{{VAULT_ROOT}}` placeholders across 13 files. Manifests: `.claude-plugin/plugin.json` (name, v3.1.0→3.2.0, repo URL; deps `["librarian"]` stays) + `.claude-plugin/marketplace.json`.

## What Remains

Execute the plan via **superpowers:executing-plans**, in order:

1. **Branch** `feat/researcher-rename-and-batch`.
2. **Phase 1 — Rename** (merge before Phase 2). Includes `gh repo rename` ⚠️, manifests, skill dirs + command names, internal refs (find-replace + manual review of SKILL.md's 17), **vault `.research-workflow/`→`.researcher/` migration** (TDD'd, runs at Stage 0), external-ref audit (Fieldwork marketplace pointer, other suite plugins, installed config, **the operator's `MEMORY.md` paths**), MANIFEST regen.
3. **Phase 2** — resolver de-throttle (execution_order advisory, no implicit cap) + `batch_threshold` config + skill router branch.
4. **Phase 3** — `.claude/workflows/research-batch.js` (hop loop via agentType + new `fetch-summarize-runner` agent + Librarian write span + thread-discoverer; vendor confidence.js/schemas).
5. **Phase 4** — skill gates: up-front cost estimate, dispatch with `budget` ceiling, thread-selection gate, Librarian-availability check.
6. **Phase 5** — tests: confidence.js synced to Python cases, contract lint, **launch-smoke (non-negotiable)**, ~12-topic e2e fixture batch.

## Open Questions

- **Librarian writer invocation mechanics:** the note-write is the `librarian` skill (not an agentType). Phase 3 Task 3.4 dispatches "an agent instructed to use the librarian skill" — confirm at build time that a workflow subagent can invoke the librarian skill cleanly and consume the neutral-contract `notes_to_create`. If not, fall back to the existing Stage-7.0 shim path.
- **Librarian writer parallel-safety at ~50 notes** (MOC serialization + mtime checks) — verify; if unsafe, the workflow serializes the MOC step.

## Context to Reload

- ⚠️ **`gh repo rename research-workflow → researcher` is outward-facing and not cleanly reversible — get the user's explicit go-ahead before running it.** Not a candidate for autonomous/fire-and-forget execution.
- **Workflow-runtime gotchas** (the hard-won lessons): `meta` must be a pure literal; no `export` but `meta`; the top-level body is the entry (no default-export call); `args` may arrive as a JSON string; `agent(prompt, opts)` has **no `input` channel** (fold input into the prompt). Full list: `~/.claude/.../memory/workflow-tool-authoring-gotchas.md`. **`node -c`/unit-green ≠ launch-valid — a workflow isn't done until launched once.**
- **The inline single/small path (SKILL Stages 4–10) must stay byte-for-byte unchanged** — the diff should show only an added router branch.
- Owned repo → keep `MANIFEST.md` current (50–80 line budget, full rewrite before PR); label issues `autonomous-safe` / `design-input-needed`.
- Toolchain: Python `C:\Users\tim\AppData\Local\Programs\Python\Python312\python.exe`, Node `C:\Program Files\nodejs\node.exe` (neither on PATH — full paths). `pytest tests/ -v` offline.
- After the rename merges, **update the operator's memory** (`MEMORY.md` + any `research-workflow` path refs → `researcher`).
