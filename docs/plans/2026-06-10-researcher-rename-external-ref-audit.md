# External-Reference Audit — research-workflow → researcher rename

**Task:** Phase 1 / Task 1.6 (executing-plans). Audit refs that live OUTSIDE this
repo. "Document, don't guess." Scans were code-scoped (`*.md`/`*.json`/`*.py`/`*.txt`);
magpie scanned code-files-only per the PII-corpus rule.

Repos scanned (siblings under `Projects/`): `fieldwork-plugins`, `librarian`,
`prose-craft`, `prose-craft-pro`, `magpie`, `dossier`; plus installed Claude config
under `~/.claude/plugins/` and the operator memory file.

## A. Real updates required — at cutover (after `gh repo rename`)

These belong to the **`fieldwork-plugins`** marketplace repo (Tim-owned). They must
change in lockstep with the GitHub rename so the member name + URL stay canonical.
GitHub keeps a redirect from the old repo URL, so the marketplace does not hard-break
in the interim, but it should be made canonical:

- [ ] `fieldwork-plugins/.claude-plugin/marketplace.json:13` — member entry:
      `"name": "research-workflow"` → `"researcher"`; URL
      `https://github.com/TimSimpsonJr/research-workflow.git` → `.../researcher.git`.
- [ ] `fieldwork-plugins/tests/test_marketplace.py:18` — `EXPECTED_MEMBERS` set:
      `"research-workflow"` → `"researcher"`.
- [ ] `fieldwork-plugins/README.md:18,23,35` — member table + prose.
- [ ] `fieldwork-plugins/NOTES.md:74,97` — prose dependency notes.

Commit in that repo: `chore: point at researcher (was research-workflow)`.

> Sequencing: do A **after** `gh repo rename` succeeds, as its own commit/PR in the
> `fieldwork-plugins` repo. Not part of this repo's PR.

## B. Operator actions (outside any repo)

- [ ] **Installed plugin state** (`~/.claude/plugins/`: `installed_plugins.json`,
      `known_marketplaces.json`, `.install-manifests/*`, `cache/*`) still references
      `research-workflow`. This is **machine-managed** — do NOT hand-edit the JSON.
      Re-point via the plugin manager after cutover: remove the old marketplace/plugin
      entry and re-add the renamed marketplace (`/plugin marketplace add ...` +
      `/plugin install researcher@fieldwork-plugins`), or `/reload`.
- [ ] **Operator `MEMORY.md`** (`~/.claude/projects/…research-workflow…/memory/`) and any
      `research-workflow` path references → `researcher`. Handled post-merge by the
      assistant (per the handoff). Note: the memory *directory* itself is keyed off the
      project path and will move when the local repo folder is renamed.

## C. Historical — leave as-is (rewriting falsifies the record)

- **`dossier/`** — design/impl/smoke docs + README reference `research-workflow` as the
  *port source*. Explicitly "historical, leave" per the plan.
- **`librarian/references/prior-art.md`, `references/acceptance-test.md`, `MANIFEST.md`,
  `README.md`** — extraction prior-art: "all file references verified by reading the
  actual research-workflow source." These document a past extraction; leave.
  (`acceptance-test.md` also has operational `/plugin install research-workflow@…`
  scenarios — these are a *librarian* doc concern, refreshable in a future librarian
  update; not in scope for this PR.)
- **`magpie/.codex-review/*`, `magpie/docs/handoffs/*`** — review logs + handoff records
  citing research-workflow's `detect_tier` as prior-art and the (since-merged)
  `wire-librarian-dependency` branch. Historical; leave.

## D. No-change confirmations

- **No sibling declares a dependency *on* `research-workflow`.** The dependency edge is
  `researcher → librarian` (this repo's `plugin.json`, unchanged). `magpie` and
  `librarian` depend on `librarian`/nothing, not on this plugin — so the rename causes
  **no runtime dependency breakage** in siblings.
- **`prose-craft`, `prose-craft-pro`** — zero references found.

## Disposition summary

| Location | Refs | Disposition |
|---|---|---|
| `fieldwork-plugins` marketplace+tests+README+NOTES | 7 | **Update at cutover** (separate repo commit) |
| `~/.claude/plugins/*` installed state | many | **Operator: re-point via plugin manager** |
| operator `MEMORY.md` + path | — | **Assistant: update post-merge** |
| `dossier`, `librarian` refs, `magpie` logs/handoffs | many | **Historical — leave** |
| `prose-craft*` | 0 | none |
