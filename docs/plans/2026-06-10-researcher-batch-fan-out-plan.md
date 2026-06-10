# Researcher Rename + Batch Fan-Out — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename the `research-workflow` plugin to `researcher`, then add a Workflow-tool batch fan-out invoked only when a batch exceeds a topic threshold — plugin-first, workflow-as-accelerator.

**Architecture:** The `/researcher` skill stays the conversational orchestrator; for `> THRESHOLD` topics it dispatches `.claude/workflows/research-batch.js`, a small JS orchestration that fans out the per-topic hop loop over **registered** agents via `agentType` (researcher's research agents + a new `fetch-summarize-runner` wrapping the Python scripts) and delegates the write span to **Librarian** (classify/wikilink by `agentType`; the write itself via a skill-using agent). No bundler, nothing inlined except a small `confidence.js`.

**Tech Stack:** Python 3.12 (existing scripts/tests, `pytest`), Node ≥18 (`node:test`, zero deps) for `confidence.js`, Claude Code Workflow tool + plugin agents/skills.

**Design:** `docs/plans/2026-06-10-researcher-batch-fan-out-design.md` (read first).

**Phase 0 (agentType spike): DONE + PASSED** (2026-06-10, spike `wsfkpbnha`) — cross-plugin `agentType` resolves inside a workflow; unknown types throw loudly; librarian's note-write is the `librarian` skill, not an agentType. No task here; the design is cleared to build.

---

## Conventions

- **Branch first** (repo is on `master`): `git checkout -b feat/researcher-rename-and-batch`. Do Phase 1 (rename) and merge it before Phase 2+ so the rename is isolated and verified.
- `docs/` is gitignored — `git add -f` plan/design docs.
- Python: `C:\Users\tim\AppData\Local\Programs\Python\Python312\python.exe`. Node: `C:\Program Files\nodejs\node.exe` (NOT on PATH — use full paths). Tests: `pytest tests/ -v`.
- DRY / YAGNI / TDD / frequent commits. Co-author trailer on every commit. Owned repo → keep `MANIFEST.md` current; label any issues `autonomous-safe` / `design-input-needed`.
- **Reuse from `../dossier`:** `src/confidence.js`, `src/schemas/index.js`, the launch-contract lint + launch-smoke discipline. NOT dossier's prompts.

---

## Phase 1 — Rename `research-workflow` → `researcher`

> Atomic + verified, merged before any feature work. 59 refs / 23 files; vault-dir literal + placeholders in 13.

### Task 1.1: Branch + GitHub rename
**Step 1:** `git checkout -b feat/researcher-rename-and-batch`
**Step 2:** Rename the GitHub repo: `gh repo rename researcher --repo TimSimpsonJr/research-workflow` (GitHub keeps a redirect).
**Step 3:** Update local remote: `git remote set-url origin https://github.com/TimSimpsonJr/researcher.git`; verify `git remote -v`.
**Step 4:** Commit nothing yet (no file changes). **Verify:** `gh repo view TimSimpsonJr/researcher` resolves.

### Task 1.2: Manifests
**Files:** `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`
- `plugin.json`: `"name": "researcher"`, `"version": "3.2.0"`, `"repository": "https://github.com/TimSimpsonJr/researcher"`. Leave `"dependencies": ["librarian"]` (Librarian is not renamed). Update description if it says "research-workflow".
- `marketplace.json`: top-level `"name": "researcher"` and `plugins[0].name = "researcher"`; keep `"source": "./"`.
**Verify:** `python -c "import json;json.load(open('.claude-plugin/plugin.json'));json.load(open('.claude-plugin/marketplace.json'))"` (valid JSON). **Commit:** `chore(rename): manifests → researcher`.

### Task 1.3: Skill directories + command names
- `git mv skills/research skills/researcher` and `git mv skills/research-setup skills/researcher-setup`.
- In each `SKILL.md` frontmatter: `name: researcher` / `name: researcher-setup`; update every `Usage: /research` → `/researcher` and `/research-setup` → `/researcher-setup` in the descriptions/bodies.
**Verify:** `ls skills/` shows `researcher/ researcher-setup/`; `grep -rn "/research\b" skills/` returns nothing. **Commit:** `chore(rename): skills + command names → researcher`.

### Task 1.4: Internal string references
Find-replace `research-workflow` → `researcher` across the repo, then **manually review** the high-count files (`skills/researcher/SKILL.md` had 17, `MANIFEST.md` 4, `scripts/config_manager.py` 4) so URLs/paths/prose stay correct.
**Step 1:** List: `grep -rln "research-workflow" .` (expect ~22 files post-manifest/skill edits).
**Step 2:** Replace in tracked text files (review each):
```bash
grep -rln "research-workflow" --include=*.md --include=*.py --include=*.json --include=*.txt --include=*.css . \
  | while read -r f; do sed -i 's/research-workflow/researcher/g' "$f"; done
```
**Step 3:** Handle the underscore form `research_workflow` (Python module/identifier refs) if any: `grep -rn "research_workflow" .` and fix case-by-case.
**Verify:** `grep -rn "research-workflow" .` returns only intentional historical refs (e.g. a CHANGELOG line); `pytest tests/ -v` still green. **Commit:** `chore(rename): internal references → researcher`.

### Task 1.5: Vault-dir literal + migration (TDD)
**Files:** `scripts/config_manager.py`, `scripts/migrate.py`, `tests/test_migrate.py`
The vault dir is `CONFIG_DIR_NAME = ".research-workflow"`. Renaming to `.researcher` orphans existing vault state, so add a migration.

**Step 1 — failing test** (`tests/test_migrate.py`): create a temp vault with a populated `.research-workflow/` (config.json, state/, cases/), run the migration, assert `.researcher/` now holds the content and `.research-workflow/` is gone; and that running it again (idempotent) is a no-op; and that a vault with neither dir is untouched.
```python
def test_migrate_vault_dir(tmp_path):
    old = tmp_path / ".research-workflow"; (old / "state").mkdir(parents=True)
    (old / "config.json").write_text('{"vault_root":"x"}')
    from migrate import migrate_vault_dir
    migrate_vault_dir(tmp_path)
    assert (tmp_path / ".researcher" / "config.json").exists()
    assert not old.exists()
    migrate_vault_dir(tmp_path)  # idempotent
    assert (tmp_path / ".researcher" / "config.json").exists()
```
**Step 2:** Run → FAIL. **Step 3:** Set `CONFIG_DIR_NAME = ".researcher"`; implement `migrate_vault_dir(vault_root)`: if `.research-workflow/` exists and `.researcher/` does not, `shutil.move` it; if both exist, leave both + warn (manual merge). **Step 4:** `pytest tests/test_migrate.py -v` → PASS.
**Step 5 — wire it:** call `migrate_vault_dir` once at skill Stage 0 (before `load_config`) so existing vaults migrate on first `/researcher` run. **Commit:** `feat(rename): vault .research-workflow→.researcher migration`.

### Task 1.6: External-ref audit (document, don't guess)
Check + update refs that live OUTSIDE this repo:
- The **Fieldwork marketplace** repo (the suite pointer) — update its entry/URL for `researcher`.
- Other suite plugins (magpie, librarian, prose-craft) — `grep -rl research-workflow` across `../magpie ../librarian ../prose-craft`; fix any dependency/reference.
- Installed Claude Code config (`~/.claude/`) — re-point if the plugin was installed by old name.
- The operator's memory files — note for the assistant to update `MEMORY.md` + `research-workflow` paths post-merge (handled outside the repo).
- `../dossier` docs reference research-workflow as port-source — **historical, leave**.
**Verify:** a written checklist in the PR of what was found + changed. **Commit (where applicable in other repos):** `chore: point at researcher (was research-workflow)`.

### Task 1.7: MANIFEST regen + merge
Rewrite `MANIFEST.md` from scratch to the 50–80-line budget (owned-repo convention), reflecting the `researcher` name + the new `.claude/workflows/` once Phase 3 lands (for now, the rename state). **Verify:** `pytest tests/ -v` green; plugin loads under the new name. Open PR; **merge** (merge commit) before Phase 2.

---

## Phase 2 — Resolver de-throttle + threshold routing

### Task 2.1: `batch_threshold` config (TDD)
**Files:** `scripts/config_manager.py`, `tests/test_config_manager.py`
**Step 1 — failing test:** `default_config(...)["batch_threshold"] == 10`. **Step 2:** FAIL. **Step 3:** add `"batch_threshold": 10` to `default_config`. **Step 4:** PASS. **Commit:** `feat: batch_threshold config (default 10)`.

### Task 2.2: Resolver — execution_order advisory + no implicit cap
**Files:** `agents/topic-resolver.md`
- Add a field note: `execution_order` is **advisory**; the skill routes by topic count vs `batch_threshold`, not by this field.
- Audit Step 2 (Parse Topics) wording to confirm it splits a many-topic prompt into all N topics with **no implicit ceiling**; add an explicit "do not cap the number of topics" note.
**Verify:** structural — the prompt states no cap + advisory execution_order. **Commit:** `feat(resolver): de-throttle large batches`.

### Task 2.3: Skill router branch
**Files:** `skills/researcher/SKILL.md` (insert at the Stage 3b/2f → Stage 4 boundary)
Add: after plan approval, compute `N = len(topics)`. If `N > batch_threshold` AND every topic `mode == "web_research"` AND the `librarian` plugin is available → take the **batch-workflow path** (Phase 3/4). Else → the existing inline Stage 4–10 (unchanged). Document the fallback (Librarian absent, or mixed local/thread-pull modes → inline path + a one-line note to the user).
**Verify:** structural — the branch + conditions + fallback are present; the inline path text is untouched (diff shows only an added branch). **Commit:** `feat(skill): batch-workflow router branch`.

---

## Phase 3 — `research-batch.js` workflow

### Task 3.1: Vendor `confidence.js` + sync tests
**Files:** Create `lib/confidence.js` (copy from `../dossier/src/confidence.js`), `test/confidence.test.js` (copy from dossier), and a parity test.
**Step 1:** Copy both. **Step 2:** Add a parity check that the JS results match `scripts/confidence.py` on the same vectors (port the assertions from `tests/test_confidence*`). **Step 3:** `"<node>" --test` → PASS. **Commit:** `feat: vendor confidence.js (synced with confidence.py)`.

### Task 3.2: Vendor agent-return schemas
**Files:** Create `lib/schemas.js` (the relevant objects from `../dossier/src/schemas/index.js`: SEARCH, SUMMARIES, HOP_NEXT, plus MOC_RESULT/WIKILINK_RESULT for the Librarian wikilink return; classify uses Librarian's own contract). **Verify:** `node --test` structural check. **Commit:** `feat: vendor agent-return schemas`.

### Task 3.3: `fetch-summarize-runner` agent (NEW)
**Files:** Create `agents/fetch-summarize-runner.md`
A thin agent (tools: Bash) that, given `{topic, selected_urls, config:{scripts_dir, python_path, ollama_model, tier}}` folded into its prompt, runs `fetch_and_clean.py --input … --output …` then `summarize.py …` (Ollama if `tier!=base`, else `--prepare-for-claude` + summarize inline) via the **full Python path**, and returns the `SUMMARIES` schema. Port the exact invocations from `skills/researcher/SKILL.md` Stages 4b/4d. **Verify:** structural — ends with a `## Output` block matching SUMMARIES; uses the python_path from input, not bare `python`. **Commit:** `feat: fetch-summarize-runner agent`.

### Task 3.4: The workflow
**Files:** Create `.claude/workflows/research-batch.js`
Pure-JS orchestration (inline `confidence.js` + schemas at the top; everything else via `agentType`). Structure:
- `export const meta` (pure literal; name `research-batch`, phases `['Research','Write','Discover']`).
- Read `args`: `{ plan, config, vaultDigest, runId }` (string-normalize: `typeof args === 'string' ? JSON.parse(args) : args`).
- **Hop loop** (depth-driven, chunked to the concurrency cap, `budget`-capped): per topic, `agent(fold(input), {agentType:'researcher:search-agent', schema: SEARCH})` → `agent(…, {agentType:'researcher:fetch-summarize-runner', schema: SUMMARIES})` → for deep topics, JS `computeConfidence`/`decide`/replan with `agent(…, {agentType:'researcher:hop-planner', schema: HOP_NEXT})`. Use a `callAgent` helper that folds `input` into the prompt (the agent() API has no input channel).
- **Write span → Librarian:** `agent(…, {agentType:'librarian:classify-agent'})` for the neutral contract (per-topic granularity; minor merging OK) → a **skill-using writer agent** (`agent('Use the librarian skill to write these notes: …', {})` — NOT an agentType, per the spike) → `agent(…, {agentType:'librarian:wikilink-scanner', schema: WIKILINK_RESULT})`. Serialize the MOC step.
- `agent(…, {agentType:'researcher:thread-discoverer', schema: THREADS})`.
- `return { written_notes, updated_notes, threads, summary }`. `.filter(Boolean)` everywhere; abort if all topics fetch zero.
- **End with** the top-level entry the workflow runtime needs (the body IS the entry; no default export).
**Verify (contract lint):** `node`-evaluate that the file has `export const meta` only-export, no import/require, compiles as an async-fn body (reuse dossier's Guard logic). `node -c` is NOT the check. **Commit:** `feat: research-batch workflow`.

---

## Phase 4 — Skill integration (gates + cost + budget)

### Task 4.1: Up-front cost estimate + approval
**Files:** `skills/researcher/SKILL.md` (batch branch)
Before launching, render an honest estimate from the plan: `topics × depth → ~agents / tokens / time / $` (reuse the resolver's `estimated_usage` + a per-depth agent multiplier). Present at the existing plan-approval gate. **Verify:** structural. **Commit:** `feat(skill): batch cost estimate at approval`.

### Task 4.2: Dispatch + thread gate + budget
**Files:** `skills/researcher/SKILL.md`
On approval, `Workflow({name:'research-batch', args:{plan, config, vaultDigest, runId}})` with the turn's `budget` as the ceiling. On return: present the **thread-selection** gate (pick follow-ups → optional next batch by re-dispatch), then the completion summary (notes written, N low-confidence, threads). Record a lightweight run marker at approve + complete. **Verify:** structural — the two gates + budget pass-through + re-dispatch loop present. **Commit:** `feat(skill): batch dispatch + thread gate`.

---

## Phase 5 — Tests / DoD

### Task 5.1: Fixture vault
Copy `../dossier/test/fixtures/vault` → `test/fixtures/vault` (3 interlinked notes). **Commit:** `test: fixture vault`.

### Task 5.2: LAUNCH-SMOKE (non-negotiable)
Launch `research-batch.js` once via the Workflow tool against the fixture vault with a small batch (and `outputDir`/scratch copy so fixtures stay pristine). Confirm it **launches and returns without runtime/meta error**. This is the gate the Dossier session proved indispensable — `node -c`/unit-green do NOT substitute. Document the run. (Requires researcher + librarian installed.)

### Task 5.3: End-to-end fixture batch (~12 topics)
Drive a ~12-topic `web_research` batch end-to-end against a scratch copy of the fixture vault: assert ≥1 note per several topics, the MOC updated, fixtures pristine, `fetch-summarize-runner` actually ran the Python scripts (check `.cache/fetch`), and the thread gate returned threads. Record results.

### Task 5.4: Final verify + MANIFEST + PR
`pytest tests/ -v` + `node --test` green; contract lint clean; rewrite `MANIFEST.md` (now incl. `.claude/workflows/research-batch.js`, `lib/`, `agents/fetch-summarize-runner.md`). Open PR; merge.

---

## Definition of done

- Phase 0 spike PASSED (✓ already).
- Rename complete + merged; existing-vault state migrates; no stale `research-workflow` refs (bar intentional history); external refs audited.
- `> batch_threshold` `web_research` batches route to `research-batch.js` and run a ~12-topic fixture batch end-to-end; Librarian-absent + mixed-mode batches fall back to the inline path.
- `confidence.js` synced + tested; contract lint clean; **the workflow has been launched at least once and returned cleanly.**
- Inline single/small path (Stages 4–10) byte-for-byte unchanged.
