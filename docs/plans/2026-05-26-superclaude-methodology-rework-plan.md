# v3.0.0 — SuperClaude Methodology Rework Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement Stage A of the v3.0.0 rework — depth profiles, source credibility tiers, confidence + replanning, multi-hop loop with hop-planner, strategy auto-selection, and SDK fossil cleanup — without breaking existing test suite. All tests stay offline.

**Architecture:** Linear pipeline becomes a hop loop with confidence-gated replanning. New `confidence.py` for pure math, new `hop-planner` Sonnet agent for between-hop decisions, new `state.py` v3 schema with hop genealogy. SKILL.md gets a full rewrite to encode the new flow.

**Tech Stack:** Python 3.10+, pytest + pytest-mock, Claude Code Task tool dispatch, Jina Reader, optional Ollama/SearXNG/Playwright per-tier.

**Reference:** [Design doc](2026-05-26-superclaude-methodology-rework-design.md)

---

## Working notes

- All tests must pass offline. No API keys, no external services. The integration test uses mocked Task dispatch and pre-recorded fixtures.
- Commit after each task. Push at end of each phase to enable per-phase review.
- Each task should take 2-5 minutes if working straight through. If a task balloons, split it.
- Existing test patterns to follow: see `tests/conftest.py` for sys.path setup, `tests/test_state.py` for state-related test patterns.
- Branch: `feat/v3-superclaude-methodology`
- Anytime a new test file is created, run the full test suite afterward (`pytest tests/ -v`) to confirm no regressions.

---

## Phase 0 — SDK fossil cleanup

Low-risk preparatory work. Removes legacy Anthropic SDK reference fossils so no test needs to shim `ANTHROPIC_API_KEY` going forward.

### Task 0.1 — Audit current SDK references

**Step 1: Confirm the current footprint**

Run: `grep -rn "ANTHROPIC_API_KEY\|^import config\|^from config\|^import anthropic\|^from anthropic" scripts/ tests/`

Expected matches:
- `scripts/utils.py:14`: `import config`
- `scripts/utils.py:29`: `import anthropic as _anthropic`
- `scripts/utils.py:32-33`: references to `config.ANTHROPIC_API_KEY`
- `scripts/find_broken_links.py:19`: `import config`
- `scripts/find_broken_links.py:20`: `from utils import startup_checks`
- `scripts/vault_lint.py:23`: `import config`
- `scripts/vault_lint.py:24`: `from utils import startup_checks`
- `tests/test_summarize.py:10`: `os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")`
- `tests/test_fetch_and_clean.py:11`: same
- `tests/test_find_broken_links.py:8`: same
- `tests/test_vault_lint.py:8`: same
- `scripts/prompts/README.md:18`: references to `claude_pipe.py` and `call_claude()`

If anything else matches, stop and ask.

**Step 2: No commit — this is a read-only audit.**

### Task 0.2 — Replace `startup_checks` calls in find_broken_links.py

**Files:**
- Modify: `scripts/find_broken_links.py`

**Step 1: Read the current usage**

Run: `grep -n "startup_checks\|config\." scripts/find_broken_links.py`

Confirm there are exactly two relevant lines: `import config`, `from utils import startup_checks`, and one call to `startup_checks()` (no `require_api_key=True`).

**Step 2: Replace the legacy imports + call with config_manager**

Edit `scripts/find_broken_links.py`. Two key rules:

1. **Remove `import config` and `from utils import startup_checks` from module scope.** These are at the top of the file (lines 19-20) and cause `ImportError`/`sys.exit(1)` cascade when tests import the module's helper functions.
2. **Add a `--vault` argument and do the config lookup inside `main()` only.** The helpers (`extract_links`, `normalize_link`, `build_note_index`, `find_broken_links`) stay importable without any side-effects.

Replace the existing `main()` function (lines 61-76) with:

```python
def main():
    import argparse
    from config_manager import load_config

    parser = argparse.ArgumentParser(description="Find broken wiki-links in an Obsidian vault.")
    parser.add_argument(
        "--vault",
        type=Path,
        default=Path.cwd(),
        help="Vault root path (defaults to current directory)",
    )
    args = parser.parse_args()

    cfg = load_config(args.vault)
    if cfg is None:
        console.print(f"[red]Error:[/red] No research-workflow config found under {args.vault}. "
                      f"Run /research-setup first, or pass --vault PATH.")
        sys.exit(1)

    vault_path = Path(cfg["vault_root"])
    if not vault_path.exists():
        console.print(f"[red]Error:[/red] vault_root does not exist: {vault_path}")
        sys.exit(1)

    broken = find_broken_links(vault_path)

    if not broken:
        console.print("[green]No broken links found.[/green]")
        sys.exit(0)

    table = Table(title=f"Broken Wiki-Links ({len(broken)} found)")
    table.add_column("File", style="cyan")
    table.add_column("Broken Link", style="red")
    for item in broken:
        rel = item["file"].relative_to(vault_path)
        table.add_row(str(rel), item["link"])
    console.print(table)
    sys.exit(1)
```

Also remove from the top of the file:
```diff
- import config
- from utils import startup_checks
```

**Step 3: Run the script's tests to confirm no regression**

Run: `pytest tests/test_find_broken_links.py -v`
Expected: PASS. (The env-var shim is dropped in Task 0.6; the test imports the module, which now imports cleanly.)

**Step 4: Commit**

```bash
git add scripts/find_broken_links.py
git commit -m "refactor(find_broken_links): drop legacy config/utils, use config_manager via --vault arg"
```

### Task 0.3 — Replace `startup_checks` calls in vault_lint.py

**Files:**
- Modify: `scripts/vault_lint.py`

**Step 1: Replace the imports and rewrite main()**

Same pattern as Task 0.2 — remove module-scope `import config` and `from utils import startup_checks`. Replace the existing `main()` (lines 79-116) with:

```python
def main():
    from config_manager import load_config

    parser = argparse.ArgumentParser(description="Find notes missing required frontmatter.")
    parser.add_argument("--vault", type=Path, default=Path.cwd(),
                        help="Vault root path (defaults to current directory)")
    parser.add_argument("--folder", help="Subfolder within vault to lint (default: whole vault)")
    parser.add_argument("--fix", action="store_true", help="Interactively fix missing fields")
    args = parser.parse_args()

    cfg = load_config(args.vault)
    if cfg is None:
        console.print(f"[red]Error:[/red] No research-workflow config found under {args.vault}. "
                      f"Run /research-setup first, or pass --vault PATH.")
        sys.exit(1)

    vault_path = Path(cfg["vault_root"])
    frontmatter_fields = cfg.get("frontmatter_fields", ["title", "source", "tags", "created"])

    target = (vault_path / args.folder).resolve() if args.folder else vault_path.resolve()
    vault_resolved = vault_path.resolve()
    # Path containment check — use is_relative_to (Py3.10+), not string prefix.
    # String-prefix matching falsely classifies sibling paths like C:\vault2 as
    # being inside C:\vault.
    if target != vault_resolved and not target.is_relative_to(vault_resolved):
        console.print(f"[red]Folder escapes vault path: {args.folder}[/red]")
        sys.exit(1)
    if not target.exists():
        console.print(f"[red]Folder not found: {target}[/red]")
        sys.exit(1)

    issues = lint_vault(target, frontmatter_fields)

    if not issues:
        console.print("[green]No issues found.[/green]")
        sys.exit(0)

    table = Table(title=f"Frontmatter Issues ({len(issues)} notes)")
    table.add_column("File", style="cyan")
    table.add_column("Missing Fields", style="red")
    for issue in issues:
        rel = issue["file"].relative_to(vault_path)
        table.add_row(str(rel), ", ".join(issue["missing"]))
    console.print(table)

    if args.fix:
        for issue in issues:
            console.print(f"\n[bold]{issue['file'].name}[/bold]")
            fix_issue(issue["file"], issue["missing"])
        console.print("[green]Done fixing issues.[/green]")

    sys.exit(1)
```

The `config.FRONTMATTER_FIELDS` reference at the old line 96 is replaced with a value read from the JSON config (`cfg.get("frontmatter_fields", ...)`). If the JSON config doesn't carry this field today, add it to the default config schema in `config_manager.default_config()` in a small follow-up edit within this same task.

**Step 2: Run vault_lint tests**

Run: `pytest tests/test_vault_lint.py -v`
Expected: PASS.

**Step 3: Add a test for the path-containment check**

Append to `tests/test_vault_lint.py`. This pins the sibling-prefix bug fix:

```python
def test_vault_lint_rejects_sibling_folder(tmp_path, capsys):
    """A sibling path that shares a string prefix with the vault root must be rejected."""
    import sys
    import subprocess
    # Make two vault-shaped sibling dirs: vault and vault2
    vault = tmp_path / "vault"
    sibling = tmp_path / "vault2"
    vault.mkdir()
    sibling.mkdir()
    # Minimal config inside vault so load_config doesn't bail early
    (vault / ".research-workflow").mkdir()
    (vault / ".research-workflow" / "config.json").write_text(
        '{"vault_root": "' + str(vault).replace("\\", "/") + '", '
        '"frontmatter_fields": ["title"], "assets": "assets"}'
    )

    # Run vault_lint as a subprocess, asking it to lint a sibling folder.
    # Pass --folder pointing at ../vault2 from the perspective of the vault.
    repo_root = Path(__file__).parent.parent
    script = repo_root / "scripts" / "vault_lint.py"
    result = subprocess.run(
        [sys.executable, str(script), "--vault", str(vault), "--folder", "../vault2"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "escapes vault" in (result.stdout + result.stderr).lower()
```

Run: `pytest tests/test_vault_lint.py::test_vault_lint_rejects_sibling_folder -v`
Expected: PASS with the `is_relative_to` containment check; would FAIL with the old `startswith` prefix check.

**Step 4: Commit**

```bash
git add scripts/vault_lint.py scripts/config_manager.py tests/test_vault_lint.py
git commit -m "refactor(vault_lint): drop legacy config/utils, use config_manager via --vault arg; fix sibling-path escape bug"
```

### Task 0.4 — Delete utils.py (now unused)

**Files:**
- Delete: `scripts/utils.py`

**Step 1: Confirm nothing imports utils**

Run: `grep -rn "^from utils\|^import utils" scripts/ tests/`
Expected: no matches (the previous tasks removed the last importers).

**Step 2: Delete the file**

Run: `git rm scripts/utils.py`

**Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: all tests still pass (anything that depended on utils has been fixed in 0.2/0.3).

**Step 4: Commit**

```bash
git commit -m "chore: delete unused utils.py (legacy SDK fossil)"
```

### Task 0.5 — Delete config.py

**Files:**
- Delete: `scripts/config.py`

**Step 1: Confirm no remaining importers**

Run: `grep -rn "^import config\|^from config" scripts/ tests/`
Expected: no matches.

**Step 2: Delete the file**

Run: `git rm scripts/config.py`

**Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: PASS for all tests except those that shim `ANTHROPIC_API_KEY` — those may now show "import config" failures cascading from removed imports. We fix the test shims in 0.6.

If unrelated failures appear, investigate before continuing.

**Step 4: Commit**

```bash
git commit -m "chore: delete legacy config.py (replaced by config_manager)"
```

### Task 0.6 — Drop `ANTHROPIC_API_KEY` env shims from tests

**Files:**
- Modify: `tests/test_summarize.py`
- Modify: `tests/test_fetch_and_clean.py`
- Modify: `tests/test_find_broken_links.py`
- Modify: `tests/test_vault_lint.py`

**Step 1: Remove the shim line from each file**

In each of the four files, remove the line:
```python
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
```

Also remove any `os.environ.setdefault("VAULT_PATH", ...)` or `os.environ.setdefault("INBOX_PATH", ...)` lines if they exist — those were part of the same fossil chain.

If the `import os` line was only used for these shims, remove it too.

**Step 2: Run full test suite**

Run: `pytest tests/ -v`
Expected: all 211 tests pass (per MEMORY.md count).

**Step 3: Commit**

```bash
git add tests/test_summarize.py tests/test_fetch_and_clean.py tests/test_find_broken_links.py tests/test_vault_lint.py
git commit -m "test: drop ANTHROPIC_API_KEY env shims (config.py is gone)"
```

### Task 0.7 — Rewrite scripts/prompts/README.md

**Files:**
- Modify: `scripts/prompts/README.md`

**Step 1: Replace the stale content**

The current README references `claude_pipe.py` and `call_claude()`, neither of which exist. Replace the file with a description of the actual prompt assembly pattern used today:

```markdown
# Prompts

Text templates used by the orchestrator and subagents.

## Assembly pattern

The orchestrator assembles prompts inline as:

```
{content}

---

{prompt_template}

---

{vault_rules}
```

`content` is the source material (article text, summary, etc.). `prompt_template` is one of the `.txt` files in this directory. `vault_rules` is `vault_rules.txt`, automatically appended to all writes/synthesis prompts. To skip vault rules for utility prompts (e.g., keyword extraction), omit `vault_rules` from the assembly.

## Files

- `vault_rules.txt` — shared rules for note creation (wikilinks, citations, tags). Auto-appended.
- `summarize.txt`, `summarize_fetch.txt`, `summarize_merge.txt` — summarization prompts (map and reduce).
- `extract_claims.txt`, `extract_transcript.txt` — extraction prompts.
- `identify_stakeholders.txt` — stakeholder extraction.
- `synthesize_topic.txt`, `find_related.txt` — synthesis prompts.
- `output_formats/` — downstream format templates (web_article, video_script, briefing, etc.).
```

**Step 2: Commit**

```bash
git add scripts/prompts/README.md
git commit -m "docs(prompts): rewrite README to reflect actual assembly pattern"
```

### Task 0.8 — Update CLAUDE.md with "no Claude SDK / no claude -p" rule

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Strengthen the existing "no anthropic SDK" rule**

In the "Key conventions" section of `CLAUDE.md`, replace:

```
- **No anthropic SDK**: The pipeline does not import or call the Anthropic API directly. All LLM work goes through Claude Code subagents (Task tool) or Ollama.
```

with:

```
- **No anthropic SDK, no `claude -p`**: The pipeline does not import or call the Anthropic API directly, and does not shell out to `claude -p`. All LLM work goes through Claude Code subagents (Task tool) or Ollama. The legacy `config.py` + `utils.py` + `claude_pipe.py` pattern has been fully removed.
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(CLAUDE.md): codify 'no Anthropic SDK, no claude -p' rule"
```

---

## Phase 1 — confidence.py (pure functions)

Add the formula library. All math is pure Python, fully testable offline.

### Task 1.1 — Create depth profile constants

**Files:**
- Create: `scripts/confidence.py`
- Create: `tests/test_confidence.py`

**Step 1: Write the failing test**

```python
# tests/test_confidence.py
from confidence import DEPTH_PROFILES, get_depth_profile


def test_depth_profiles_have_required_fields():
    for name in ["quick", "standard", "deep", "exhaustive"]:
        profile = DEPTH_PROFILES[name]
        assert "max_hops" in profile
        assert "target_sources" in profile
        assert "confidence_target" in profile


def test_get_depth_profile_returns_dict():
    profile = get_depth_profile("standard")
    assert profile["max_hops"] == 3
    assert profile["target_sources"] == 20
    assert profile["confidence_target"] == 0.7


def test_get_depth_profile_invalid_raises():
    import pytest
    with pytest.raises(KeyError):
        get_depth_profile("nonsense")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_confidence.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'confidence'`.

**Step 3: Create the minimal implementation**

```python
# scripts/confidence.py
"""confidence.py — research quality scoring.

Pure functions for computing confidence and contradiction signals from
hop summaries. No I/O, no API calls — fully testable offline.
"""

DEPTH_PROFILES = {
    "quick":      {"max_hops": 1, "target_sources": 10, "confidence_target": 0.6},
    "standard":   {"max_hops": 3, "target_sources": 20, "confidence_target": 0.7},
    "deep":       {"max_hops": 4, "target_sources": 40, "confidence_target": 0.8},
    "exhaustive": {"max_hops": 5, "target_sources": 50, "confidence_target": 0.9},
}


def get_depth_profile(name: str) -> dict:
    """Return the depth profile for the given name. Raises KeyError if unknown."""
    return DEPTH_PROFILES[name]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_confidence.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/confidence.py tests/test_confidence.py
git commit -m "feat(confidence): add depth profile constants"
```

### Task 1.2 — Tier-diversity weighted average

**Files:**
- Modify: `scripts/confidence.py`
- Modify: `tests/test_confidence.py`

**Step 1: Write the failing test**

Append to `tests/test_confidence.py`:

```python
def test_tier_diversity_all_t1():
    sources = [{"tier": "T1"} for _ in range(3)]
    assert tier_diversity_weight(sources) == 1.0


def test_tier_diversity_all_t4():
    sources = [{"tier": "T4"} for _ in range(3)]
    assert tier_diversity_weight(sources) == 0.25


def test_tier_diversity_mixed():
    sources = [{"tier": "T1"}, {"tier": "T2"}, {"tier": "T3"}, {"tier": "T4"}]
    expected = (1.0 + 0.75 + 0.5 + 0.25) / 4
    assert tier_diversity_weight(sources) == expected


def test_tier_diversity_empty():
    assert tier_diversity_weight([]) == 0.0
```

Also add the import: `from confidence import tier_diversity_weight`.

**Step 2: Run to confirm failure**

Run: `pytest tests/test_confidence.py::test_tier_diversity_mixed -v`
Expected: FAIL with `ImportError`.

**Step 3: Implement**

Append to `scripts/confidence.py`:

```python
TIER_WEIGHTS = {"T1": 1.0, "T2": 0.75, "T3": 0.5, "T4": 0.25}


def tier_diversity_weight(sources: list[dict]) -> float:
    """Average tier weight across sources. Empty list returns 0.0."""
    if not sources:
        return 0.0
    return sum(TIER_WEIGHTS.get(s["tier"], 0.25) for s in sources) / len(sources)
```

**Step 4: Run to confirm pass**

Run: `pytest tests/test_confidence.py -v`
Expected: all tests PASS.

**Step 5: Commit**

```bash
git add scripts/confidence.py tests/test_confidence.py
git commit -m "feat(confidence): add tier_diversity_weight function"
```

### Task 1.3 — Topic coverage

**Step 1: Write the failing test**

Append to `tests/test_confidence.py`:

```python
def test_topic_coverage_three_t2_sources():
    sources = [{"tier": "T2"}, {"tier": "T2"}, {"tier": "T2"}]
    assert topic_coverage(sources) == 1.0


def test_topic_coverage_two_t1_sources():
    sources = [{"tier": "T1"}, {"tier": "T1"}]
    assert topic_coverage(sources) == 2 / 3


def test_topic_coverage_low_tier_excluded():
    sources = [{"tier": "T3"}, {"tier": "T4"}, {"tier": "T3"}]
    assert topic_coverage(sources) == 0.0


def test_topic_coverage_mixed():
    sources = [{"tier": "T1"}, {"tier": "T3"}, {"tier": "T2"}, {"tier": "T4"}]
    # Two T2+ sources → 2/3
    assert topic_coverage(sources) == 2 / 3
```

Add `from confidence import topic_coverage` to imports.

**Step 2: Run to confirm failure**

Run: `pytest tests/test_confidence.py::test_topic_coverage_mixed -v`

**Step 3: Implement**

Append to `scripts/confidence.py`:

```python
def topic_coverage(sources: list[dict]) -> float:
    """Fraction of T2+ sources up to a count of 3. Caps at 1.0."""
    t2plus = sum(1 for s in sources if s["tier"] in {"T1", "T2"})
    return min(1.0, t2plus / 3)
```

**Step 4: Run to confirm pass**

Run: `pytest tests/test_confidence.py -v`

**Step 5: Commit**

```bash
git add scripts/confidence.py tests/test_confidence.py
git commit -m "feat(confidence): add topic_coverage function"
```

### Task 1.4 — Primary source presence

**Step 1: Write the failing test**

Append:

```python
def test_primary_source_presence_zero():
    sources = [{"is_primary": False}, {"is_primary": False}]
    assert primary_source_presence(sources) == 0.0


def test_primary_source_presence_one():
    sources = [{"is_primary": True}, {"is_primary": False}]
    assert primary_source_presence(sources) == 0.5


def test_primary_source_presence_two():
    sources = [{"is_primary": True}, {"is_primary": True}]
    assert primary_source_presence(sources) == 1.0


def test_primary_source_presence_caps_at_two():
    sources = [{"is_primary": True}] * 5
    assert primary_source_presence(sources) == 1.0
```

Add `from confidence import primary_source_presence` to imports.

**Step 2: Run to confirm failure.**

**Step 3: Implement**

```python
def primary_source_presence(sources: list[dict]) -> float:
    """Capped at 1.0 when 2+ primary sources present."""
    primary_count = sum(1 for s in sources if s.get("is_primary"))
    return min(1.0, primary_count / 2)
```

**Step 4: Run to confirm pass.**

**Step 5: Commit**

```bash
git commit -am "feat(confidence): add primary_source_presence function"
```

### Task 1.5 — Source count adequacy

**Step 1: Write the failing test**

```python
def test_source_count_adequacy_below_target():
    assert source_count_adequacy(sources_count=10, target=20) == 0.5


def test_source_count_adequacy_at_target():
    assert source_count_adequacy(sources_count=20, target=20) == 1.0


def test_source_count_adequacy_above_target():
    assert source_count_adequacy(sources_count=30, target=20) == 1.0


def test_source_count_adequacy_zero():
    assert source_count_adequacy(sources_count=0, target=20) == 0.0
```

Add `from confidence import source_count_adequacy`.

**Step 2: Run to confirm failure.**

**Step 3: Implement**

```python
def source_count_adequacy(sources_count: int, target: int) -> float:
    """Linear up to target, then capped at 1.0."""
    if target <= 0:
        return 0.0
    return min(1.0, sources_count / target)
```

**Step 4: Run to confirm pass.**

**Step 5: Commit.**

### Task 1.6 — `compute_confidence` (composed)

**Step 1: Write the failing test**

```python
def test_compute_confidence_strong_topic():
    sources = [
        {"tier": "T1", "is_primary": True},
        {"tier": "T1", "is_primary": False},
        {"tier": "T2", "is_primary": True},
        {"tier": "T2", "is_primary": False},
    ]
    score = compute_confidence(sources, depth="standard")
    # tier_diversity ~0.875, coverage 1.0, primary 1.0, adequacy 4/20=0.2
    # 0.4*0.875 + 0.3*1.0 + 0.2*1.0 + 0.1*0.2 = 0.35 + 0.3 + 0.2 + 0.02 = 0.87
    assert 0.86 <= score <= 0.88


def test_compute_confidence_weak_topic():
    sources = [{"tier": "T4", "is_primary": False}]
    score = compute_confidence(sources, depth="standard")
    # tier 0.25, coverage 0.0, primary 0.0, adequacy 1/20=0.05
    # 0.4*0.25 + 0.3*0 + 0.2*0 + 0.1*0.05 = 0.1 + 0 + 0 + 0.005 = 0.105
    assert 0.10 <= score <= 0.11


def test_compute_confidence_empty():
    assert compute_confidence([], depth="standard") == 0.0
```

Add `from confidence import compute_confidence`.

**Step 2: Run to confirm failure.**

**Step 3: Implement**

```python
def compute_confidence(sources: list[dict], depth: str) -> float:
    """Composite confidence score for a topic's sources.

    Weights: 0.4 tier_diversity + 0.3 topic_coverage + 0.2 primary_source_presence
    + 0.1 source_count_adequacy.
    """
    if not sources:
        return 0.0
    target = get_depth_profile(depth)["target_sources"]
    return (
        0.4 * tier_diversity_weight(sources) +
        0.3 * topic_coverage(sources) +
        0.2 * primary_source_presence(sources) +
        0.1 * source_count_adequacy(len(sources), target)
    )
```

**Step 4: Run to confirm pass.**

**Step 5: Commit.**

### Task 1.7 — Contradiction rate

**Step 1: Write the failing test**

```python
def test_contradiction_rate_none():
    sources = [{"url": "a"}, {"url": "b"}, {"url": "c"}]
    contradictions = []
    assert contradiction_rate(sources, contradictions) == 0.0


def test_contradiction_rate_single_pair():
    sources = [{"url": "a"}, {"url": "b"}, {"url": "c"}]
    contradictions = [{"source_a": "a", "source_b": "b"}]
    # 1 / (3 * 0.3) = 1 / 0.9 ≈ 1.11 → capped 1.0
    assert contradiction_rate(sources, contradictions) == 1.0


def test_contradiction_rate_proportional():
    sources = [{"url": f"s{i}"} for i in range(10)]
    contradictions = [{"source_a": "s0", "source_b": "s1"}]
    # 1 / (10 * 0.3) = 1 / 3 ≈ 0.333
    assert 0.33 <= contradiction_rate(sources, contradictions) <= 0.34


def test_contradiction_rate_too_few_sources():
    sources = [{"url": "a"}]
    contradictions = []
    assert contradiction_rate(sources, contradictions) == 0.0
```

Add `from confidence import contradiction_rate`.

**Step 2: Run to confirm failure.**

**Step 3: Implement**

```python
def contradiction_rate(sources: list[dict], contradictions: list[dict]) -> float:
    """Normalize contradictions by (source_count * 0.3). Caps at 1.0."""
    if len(sources) < 2:
        return 0.0
    if not contradictions:
        return 0.0
    return min(1.0, len(contradictions) / (len(sources) * 0.3))
```

**Step 4: Run to confirm pass.**

**Step 5: Commit.**

### Task 1.8 — Tier-from-credibility helper

The search-agent emits `credibility_score` (0.3-1.0); we derive `tier` from it. Add a helper so both the agent prompt and downstream code use the same buckets.

**Step 1: Write the failing test**

```python
def test_tier_from_score_t1():
    assert tier_from_score(0.95) == "T1"
    assert tier_from_score(0.9) == "T1"


def test_tier_from_score_t2():
    assert tier_from_score(0.85) == "T2"
    assert tier_from_score(0.7) == "T2"


def test_tier_from_score_t3():
    assert tier_from_score(0.6) == "T3"
    assert tier_from_score(0.5) == "T3"


def test_tier_from_score_t4():
    assert tier_from_score(0.4) == "T4"
    assert tier_from_score(0.3) == "T4"


def test_tier_from_score_below_range():
    assert tier_from_score(0.1) == "T4"
```

Add `from confidence import tier_from_score`.

**Step 2: Run to confirm failure.**

**Step 3: Implement**

```python
def tier_from_score(score: float) -> str:
    """Bucket a credibility score (0.0-1.0) into tier T1/T2/T3/T4."""
    if score >= 0.9:
        return "T1"
    if score >= 0.7:
        return "T2"
    if score >= 0.5:
        return "T3"
    return "T4"
```

**Step 4: Run to confirm pass.**

**Step 5: Commit.**

---

## Phase 2 — state.py v3 schema

Extend state.py for hop-loop tracking, usage telemetry, and case-record writing.

### Task 2.1 — Bump schema version constant

**Files:**
- Modify: `scripts/state.py`
- Modify: `tests/test_state.py`

**Step 1: Find the current schema version**

Run: `grep -n "version" scripts/state.py`

If a `STATE_VERSION` or similar constant exists, note its value. If not, we add it.

**Step 2: Write the failing test**

Append to `tests/test_state.py`:

```python
def test_state_version_constant():
    from state import STATE_VERSION
    assert STATE_VERSION == 3


def test_create_run_writes_version(tmp_path):
    from state import create_run
    run = create_run(tmp_path, run_id="2026-05-26-test", tier="full")
    assert run["version"] == 3
```

**Step 3: Run to confirm failure.**

**Step 4: Implement**

In `scripts/state.py`:
- Add at top-level: `STATE_VERSION = 3`
- Add `import sys` at the top (next to `import json`/`import shutil`). Subsequent tasks (2.2, 2.6, etc.) reference `sys.stderr` and `sys.exit`; the current file does not import `sys`.
- Add a new public helper next to `_atomic_write`:

```python
def save_state(state_dir: Path, run: dict) -> None:
    """Save the active run state atomically. Public wrapper around _atomic_write."""
    _atomic_write(state_dir / CURRENT_RUN_FILE, run)
```

  This helper is consumed by every subsequent task in Phase 2 (2.4, 2.5, 2.6, 2.7) and by SKILL.md stages. Introducing it here avoids the dependency-order trap of using it in 2.4 before it's defined.

- In `create_run()`, two changes:
  - Include `"version": STATE_VERSION` in the returned dict and written JSON.
  - Change the initial `"stage"` from `"resolve"` to `"triage"`. v3 makes Triage the first stage that does any work after run creation; a crash before Stage 4 must resume at Triage, not Resolve.

  ```diff
   run = {
       "run_id": run_id,
       "started_at": datetime.now(timezone.utc).isoformat(),
  -    "stage": "resolve",
  +    "stage": "triage",
  +    "version": STATE_VERSION,
       "stage_progress": {},
       "tier_detected": tier,
       "plan_approved": False,
   }
  ```

  Add a test for the initial stage:

  ```python
  def test_create_run_initial_stage_is_triage(tmp_path):
      from state import create_run
      run = create_run(tmp_path, run_id="r1", tier="full")
      assert run["stage"] == "triage"
  ```

  **Also update the pre-existing test** at `tests/test_state.py:10-16` (`test_create_run_writes_current_run`) — line 15 asserts `run["stage"] == "resolve"`, which will fail after this change:

  ```diff
   def test_create_run_writes_current_run(tmp_path):
       from state import create_run
       run = create_run(tmp_path, "sc-alpr", "mid")
       assert (tmp_path / "current_run.json").exists()
       assert run["run_id"] == "sc-alpr"
  -    assert run["stage"] == "resolve"
  +    assert run["stage"] == "triage"
       assert run["tier_detected"] == "mid"
  ```

**Step 5: Run to confirm pass.**

Run: `pytest tests/test_state.py -v`
Expected: existing tests still pass (the new STATE_VERSION constant is additive, `save_state` is an additive helper, version field is additive in `create_run` returns).

**Step 6: Commit**

```bash
git add scripts/state.py tests/test_state.py
git commit -m "feat(state): bump schema to v3 + add save_state helper + import sys"
```

### Task 2.2 — Schema-mismatch drop on load

**Step 1: Write the failing test**

```python
def test_load_run_drops_old_schema(tmp_path, capsys):
    from state import load_run
    # Write a fake v2-era state file
    state_file = tmp_path / "current_run.json"
    state_file.write_text(json.dumps({"run_id": "old", "version": 2, "tier": "full"}))
    result = load_run(tmp_path)
    assert result is None
    err = capsys.readouterr().err   # message goes to stderr (see implementation)
    assert "older schema" in err.lower()
    # The state file should have been moved out (abandoned to history/)
    assert not (tmp_path / "current_run.json").exists()


def test_load_run_drops_missing_version(tmp_path, capsys):
    from state import load_run
    state_file = tmp_path / "current_run.json"
    state_file.write_text(json.dumps({"run_id": "old", "tier": "full"}))  # no version
    result = load_run(tmp_path)
    assert result is None
```

Add `import json` if missing.

**Step 2: Run to confirm failure.**

**Step 3: Implement**

In `scripts/state.py`, modify `load_run()`. The schema-mismatch branch must archive the file **without** calling `abandon_run()`, because `abandon_run` → `_archive_run` → `load_run` would recurse infinitely on a stale-version file.

```python
def load_run(state_dir: Path) -> dict | None:
    state_file = state_dir / CURRENT_RUN_FILE
    if not state_file.exists():
        return None
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if data.get("version") != STATE_VERSION:
        print(
            f"Your in-flight run was on an older schema (v{data.get('version', 'unknown')}) "
            f"and has been abandoned. Run /research to start fresh.",
            file=sys.stderr,
        )
        # Archive in-place without recursing through abandon_run → _archive_run → load_run
        old_id = data.get("run_id", "unparseable")
        history_dir = state_dir / "history" / f"{old_id}-stale-v{data.get('version', 'unknown')}"
        history_dir.mkdir(parents=True, exist_ok=True)
        for f in state_dir.glob("*.json"):
            shutil.move(str(f), str(history_dir / f.name))
        return None
    return data
```

**Step 4: Run to confirm pass.**

Run: `pytest tests/test_state.py -v`
Expected: both new tests pass, all existing tests still pass.

**Step 5: Commit.**

### Task 2.3 — Add `topics[]` per-topic schema fields

**Step 1: Write the failing test**

```python
def test_create_run_topic_initialization(tmp_path):
    from state import create_run, init_topic
    run = create_run(tmp_path, run_id="r1", tier="full")
    topic = init_topic("SC ALPR programs", mode="web_research", depth="standard")
    assert topic == {
        "topic": "SC ALPR programs",
        "mode": "web_research",
        "depth": "standard",
        "max_hops": 3,
        "current_hop": 0,
        "status": "active",
        "hop_genealogy": [],
        "confidence_history": [],
        "contradiction_rate": 0.0,
        "seen_urls": [],
        "replan_hint": None,
        "next_hop": None,
    }
```

Two pieces of forward-looking state on each topic:
- `next_hop`: the hop-planner's `next_hop` payload (pattern + from + rationale) when it returned `decision: "continue"`. Stage 4a reads this on hop 2+ to construct the search-agent's hop_context. `None` at start and after `decision: "stop"`.
- `replan_hint`: the hop-planner's `replan_hint` payload when it returned `decision: "replan"`, OR a synthesized hint from Stage 5b/5c. Stage 4a reads this on a re-admitted topic. `None` when no replan is pending.

The two are mutually exclusive in practice: continue → `next_hop` set, `replan_hint` cleared; replan → `replan_hint` set, `next_hop` cleared.

**Step 2: Run to confirm failure.**

**Step 3: Implement**

Add `init_topic()` helper to `scripts/state.py`:

```python
from confidence import get_depth_profile


def init_topic(topic: str, mode: str, depth: str) -> dict:
    """Create a fresh topic state entry for the run."""
    profile = get_depth_profile(depth)
    return {
        "topic": topic,
        "mode": mode,
        "depth": depth,
        "max_hops": profile["max_hops"],
        "current_hop": 0,
        "status": "active",
        "hop_genealogy": [],
        "confidence_history": [],
        "contradiction_rate": 0.0,
        "seen_urls": [],
        "replan_hint": None,
        "next_hop": None,
    }
```

**Step 4: Run to confirm pass.**

**Step 5: Commit.**

### Task 2.4 — `record_hop()` helper

**Step 1: Write the failing test**

```python
def test_record_hop_appends_to_genealogy(tmp_path):
    from state import create_run, init_topic, record_hop, save_state
    run = create_run(tmp_path, run_id="r1", tier="full")
    topic = init_topic("X", mode="web_research", depth="standard")
    run["topics"] = [topic]
    save_state(tmp_path, run)

    hop_data = {
        "hop": 1,
        "pattern": None,
        "queries": ["q1"],
        "sources_found": 12,
        "sources_kept": 7,
        "ended_at": "2026-05-26T14:25:00Z",
    }
    record_hop(tmp_path, topic_name="X", hop_data=hop_data)

    from state import load_run
    reloaded = load_run(tmp_path)
    assert reloaded["topics"][0]["hop_genealogy"] == [hop_data]
    assert reloaded["topics"][0]["current_hop"] == 1
```

**Step 2: Run to confirm failure.**

**Step 3: Implement**

```python
def record_hop(state_dir: Path, topic_name: str, hop_data: dict) -> None:
    """Append a hop record to the topic's genealogy and increment current_hop."""
    run = load_run(state_dir)
    if run is None:
        raise RuntimeError("No active run")
    for t in run["topics"]:
        if t["topic"] == topic_name:
            t["hop_genealogy"].append(hop_data)
            t["current_hop"] += 1
            break
    else:
        raise KeyError(f"Topic not found: {topic_name}")
    save_state(state_dir, run)
```

**Step 4: Run to confirm pass.**

**Step 5: Commit.**

### Task 2.5 — `mark_topic_status()` and `append_confidence()`

**Step 1: Write the failing test**

```python
def test_mark_topic_status(tmp_path):
    from state import create_run, init_topic, mark_topic_status, save_state, load_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    run["topics"] = [init_topic("X", mode="web_research", depth="standard")]
    save_state(tmp_path, run)

    mark_topic_status(tmp_path, topic_name="X", status="complete")
    assert load_run(tmp_path)["topics"][0]["status"] == "complete"


def test_append_confidence(tmp_path):
    from state import create_run, init_topic, append_confidence, save_state, load_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    run["topics"] = [init_topic("X", mode="web_research", depth="standard")]
    save_state(tmp_path, run)

    append_confidence(tmp_path, topic_name="X", score=0.42)
    append_confidence(tmp_path, topic_name="X", score=0.71)
    assert load_run(tmp_path)["topics"][0]["confidence_history"] == [0.42, 0.71]


def test_set_contradiction_rate(tmp_path):
    from state import create_run, init_topic, set_contradiction_rate, save_state, load_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    run["topics"] = [init_topic("X", mode="web_research", depth="standard")]
    save_state(tmp_path, run)

    set_contradiction_rate(tmp_path, topic_name="X", rate=0.18)
    assert load_run(tmp_path)["topics"][0]["contradiction_rate"] == 0.18

    # Overwrites with newer value
    set_contradiction_rate(tmp_path, topic_name="X", rate=0.32)
    assert load_run(tmp_path)["topics"][0]["contradiction_rate"] == 0.32


def test_set_replan_hint(tmp_path):
    from state import create_run, init_topic, set_replan_hint, save_state, load_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    run["topics"] = [init_topic("X", mode="web_research", depth="standard")]
    save_state(tmp_path, run)

    hint = {"issue": "thin sources", "suggested_pattern": "entity_expansion",
            "suggested_query_focus": "official agency data"}
    set_replan_hint(tmp_path, topic_name="X", hint=hint)
    assert load_run(tmp_path)["topics"][0]["replan_hint"] == hint


def test_bump_max_hops(tmp_path):
    """Bumping max_hops lets a topic re-enter the hop loop after exhausting its budget."""
    from state import create_run, init_topic, bump_max_hops, save_state, load_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    run["topics"] = [init_topic("X", mode="web_research", depth="standard")]  # max_hops=3
    save_state(tmp_path, run)

    bump_max_hops(tmp_path, topic_name="X", increment=1)
    assert load_run(tmp_path)["topics"][0]["max_hops"] == 4
```

**Step 2: Run to confirm failure.**

**Step 3: Implement** — three helpers with the same `load → mutate → save` pattern as `record_hop`. `set_contradiction_rate` is a setter (overwrites the latest value), not a history-tracker, because the contradiction rate is recomputed from all hops' summaries each pass:

```python
def mark_topic_status(state_dir: Path, topic_name: str, status: str) -> None:
    run = load_run(state_dir)
    if run is None:
        raise RuntimeError("No active run")
    for t in run["topics"]:
        if t["topic"] == topic_name:
            t["status"] = status
            break
    else:
        raise KeyError(f"Topic not found: {topic_name}")
    save_state(state_dir, run)


def append_confidence(state_dir: Path, topic_name: str, score: float) -> None:
    run = load_run(state_dir)
    if run is None:
        raise RuntimeError("No active run")
    for t in run["topics"]:
        if t["topic"] == topic_name:
            t["confidence_history"].append(score)
            break
    else:
        raise KeyError(f"Topic not found: {topic_name}")
    save_state(state_dir, run)


def set_contradiction_rate(state_dir: Path, topic_name: str, rate: float) -> None:
    """Overwrite the topic's contradiction_rate with the latest measurement."""
    run = load_run(state_dir)
    if run is None:
        raise RuntimeError("No active run")
    for t in run["topics"]:
        if t["topic"] == topic_name:
            t["contradiction_rate"] = rate
            break
    else:
        raise KeyError(f"Topic not found: {topic_name}")
    save_state(state_dir, run)


def set_replan_hint(state_dir: Path, topic_name: str, hint: dict | None) -> None:
    """Set or clear the topic's replan_hint (read by Stage 5b auto-replan)."""
    run = load_run(state_dir)
    if run is None:
        raise RuntimeError("No active run")
    for t in run["topics"]:
        if t["topic"] == topic_name:
            t["replan_hint"] = hint
            break
    else:
        raise KeyError(f"Topic not found: {topic_name}")
    save_state(state_dir, run)


def set_next_hop(state_dir: Path, topic_name: str, next_hop: dict | None) -> None:
    """Set or clear the topic's next_hop (read by Stage 4a on the next iteration).

    Called after a hop-planner decision="continue" to record the pattern/from/rationale
    that should drive the next search. Cleared after consumption in Stage 4a.
    """
    run = load_run(state_dir)
    if run is None:
        raise RuntimeError("No active run")
    for t in run["topics"]:
        if t["topic"] == topic_name:
            t["next_hop"] = next_hop
            break
    else:
        raise KeyError(f"Topic not found: {topic_name}")
    save_state(state_dir, run)


def bump_max_hops(state_dir: Path, topic_name: str, increment: int = 1) -> None:
    """Increase the topic's hop budget. Used by Stage 5b auto-replan to give a topic
    another hop after it exhausts its initial budget; without this, the Stage 4
    admission check (current_hop < max_hops) would silently filter the topic out."""
    run = load_run(state_dir)
    if run is None:
        raise RuntimeError("No active run")
    for t in run["topics"]:
        if t["topic"] == topic_name:
            t["max_hops"] += increment
            break
    else:
        raise KeyError(f"Topic not found: {topic_name}")
    save_state(state_dir, run)
```

**Step 4: Run to confirm pass.**

**Step 5: Commit.**

### Task 2.6 — Usage tracking

**Step 1: Write the failing test**

```python
def test_add_usage_starts_at_zero(tmp_path):
    from state import create_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    assert run["usage"] == {
        "haiku":  {"calls": 0, "in_tokens": 0, "out_tokens": 0},
        "sonnet": {"calls": 0, "in_tokens": 0, "out_tokens": 0},
        "opus":   {"calls": 0, "in_tokens": 0, "out_tokens": 0},
        "ollama": {"calls": 0},
    }


def test_add_usage_accumulates(tmp_path):
    from state import create_run, add_usage, load_run, save_state
    run = create_run(tmp_path, run_id="r1", tier="full")
    save_state(tmp_path, run)

    add_usage(tmp_path, model="haiku", in_tokens=1000, out_tokens=200, stage="search")
    add_usage(tmp_path, model="haiku", in_tokens=500,  out_tokens=100, stage="summarize")
    add_usage(tmp_path, model="ollama", in_tokens=0, out_tokens=0, stage="summarize")

    usage = load_run(tmp_path)["usage"]
    assert usage["haiku"] == {"calls": 2, "in_tokens": 1500, "out_tokens": 300}
    assert usage["ollama"]["calls"] == 1
```

**Step 2: Run to confirm failure.**

**Step 3: Implement**

In `create_run()`, initialize the usage block. The `ollama` bucket only has `"calls"` — no token fields — because Ollama is local and there's nothing to bill or budget:

```python
"usage": {
    "haiku":  {"calls": 0, "in_tokens": 0, "out_tokens": 0},
    "sonnet": {"calls": 0, "in_tokens": 0, "out_tokens": 0},
    "opus":   {"calls": 0, "in_tokens": 0, "out_tokens": 0},
    "ollama": {"calls": 0},
}
```

Add `add_usage()`. Use `dict.get(key, 0) +` rather than `+=` so the ollama bucket (which lacks token keys) doesn't `KeyError`:

```python
def add_usage(state_dir: Path, model: str, in_tokens: int, out_tokens: int, stage: str) -> None:
    """Increment per-model usage counters for the active run.

    Safe against missing buckets and missing keys (the ollama bucket has no
    token fields by design — local inference has no token cost).
    """
    run = load_run(state_dir)
    if run is None:
        return  # silently ignore — telemetry shouldn't block the pipeline
    bucket = run["usage"].setdefault(model, {"calls": 0})
    bucket["calls"] = bucket.get("calls", 0) + 1
    if model != "ollama":
        bucket["in_tokens"] = bucket.get("in_tokens", 0) + in_tokens
        bucket["out_tokens"] = bucket.get("out_tokens", 0) + out_tokens
    save_state(state_dir, run)
```

Note: `stage` is currently unused but kept in the signature for future per-stage breakdown.

**Step 4: Run to confirm pass.**

**Step 5: Commit.**

### Task 2.7 — Replan counter + user decisions log

**Step 1: Write the failing test**

```python
def test_replan_count_starts_at_zero(tmp_path):
    from state import create_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    assert run["replan_count"] == 0
    assert run["user_decisions"] == []


def test_increment_replan(tmp_path):
    from state import create_run, save_state, increment_replan, load_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    save_state(tmp_path, run)
    increment_replan(tmp_path)
    increment_replan(tmp_path)
    assert load_run(tmp_path)["replan_count"] == 2


def test_record_user_decision(tmp_path):
    from state import create_run, save_state, record_user_decision, load_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    save_state(tmp_path, run)
    record_user_decision(tmp_path, decision="continue_anyway", confidence=0.52)
    decisions = load_run(tmp_path)["user_decisions"]
    assert len(decisions) == 1
    assert decisions[0]["decision"] == "continue_anyway"
    assert decisions[0]["confidence"] == 0.52
    assert "at" in decisions[0]
```

**Step 2: Run to confirm failure.**

**Step 3: Implement**

Initialize `replan_count: 0` and `user_decisions: []` in `create_run()`.
Add helpers:

```python
from datetime import datetime, timezone


def increment_replan(state_dir: Path) -> None:
    run = load_run(state_dir)
    if run is None:
        return
    run["replan_count"] += 1
    save_state(state_dir, run)


def record_user_decision(state_dir: Path, decision: str, **details) -> None:
    run = load_run(state_dir)
    if run is None:
        return
    run["user_decisions"].append({
        "decision": decision,
        "at": datetime.now(timezone.utc).isoformat(),
        **details,
    })
    save_state(state_dir, run)
```

**Step 4: Run to confirm pass.**

**Step 5: Commit.**

### Task 2.8 — Archive sweeps per-hop intermediate files (compatible with existing `_archive_run`)

**Important:** The existing `_archive_run` (private) archives to `history/{run_id}/` and is called by `abandon_run` and `complete_run`. Existing tests assert this path. **Do NOT rename it to `archive_run` or change the destination to `archive/`.** We're adding per-hop sweeping to the existing function and keeping the API contract intact.

The good news: `_archive_run` already iterates `state_dir.glob("*.json")`, which transparently picks up any per-hop files written into the state dir (e.g., `fetch_results_hop1.json`). The only "fix" needed is to verify the existing implementation handles per-hop files correctly — no code change required for sweep behavior, just a test that pins the contract.

**Step 1: Write the failing test (against existing `_archive_run` via the public `abandon_run`)**

```python
def test_abandon_run_sweeps_hop_intermediate_files(tmp_path):
    from state import create_run, abandon_run
    create_run(tmp_path, run_id="2026-05-26-hop-test", tier="full")

    # Simulate per-hop intermediate files
    (tmp_path / "fetch_results_hop1.json").write_text("{}")
    (tmp_path / "fetch_results_hop2.json").write_text("{}")
    (tmp_path / "summaries_hop1.json").write_text("{}")
    (tmp_path / "search_context_hop1.json").write_text("{}")

    abandon_run(tmp_path)

    # All per-hop files land alongside current_run.json under history/{run_id}/
    history_dir = tmp_path / "history" / "2026-05-26-hop-test"
    assert history_dir.exists()
    assert (history_dir / "fetch_results_hop1.json").exists()
    assert (history_dir / "fetch_results_hop2.json").exists()
    assert (history_dir / "summaries_hop1.json").exists()
    assert (history_dir / "search_context_hop1.json").exists()
    # Active run file should be gone
    assert not (tmp_path / "current_run.json").exists()
```

**Step 2: Run to confirm — likely passes already**

Run: `pytest tests/test_state.py::test_abandon_run_sweeps_hop_intermediate_files -v`

If it passes immediately: the existing `state_dir.glob("*.json")` already does the right thing. Skip Step 3.

If it fails (e.g., the existing implementation has a hardcoded list of filenames instead of glob): Step 3 updates `_archive_run` to use `glob`.

**Step 3: Update `_archive_run` if needed**

Confirm `_archive_run` matches:

```python
def _archive_run(state_dir: Path) -> None:
    """Move all state-dir JSON files to history/{run_id}/."""
    run_file = state_dir / CURRENT_RUN_FILE
    if not run_file.exists():
        return
    try:
        data = json.loads(run_file.read_text(encoding="utf-8"))
        run_id = data.get("run_id", "unknown")
    except json.JSONDecodeError:
        run_id = "unparseable"
    history_dir = state_dir / "history" / run_id
    history_dir.mkdir(parents=True, exist_ok=True)
    for f in state_dir.glob("*.json"):
        shutil.move(str(f), str(history_dir / f.name))
```

Two changes vs. the current implementation:
- Read the JSON directly instead of calling `load_run` (avoids recursion with the schema-mismatch branch in `load_run`).
- Use a try/except for malformed JSON (defensive — `load_run` does this; keep parity).

**Step 4: Run full test suite**

```bash
pytest tests/test_state.py -v
```
Expected: all existing tests still pass.

**Step 5: Commit**

```bash
git commit -am "feat(state): archive sweeps per-hop intermediate files (test added; _archive_run handles JSON directly)"
```

### Task 2.9 — Make `complete_run()` return the final run data

Stage 10 needs to read the final run state for telemetry, hop genealogy display, and case-record generation BEFORE the archive moves the file. Currently `complete_run()` archives immediately and `load_run()` returns None afterward.

**Step 1: Write the failing test**

```python
def test_complete_run_returns_run_data(tmp_path):
    from state import create_run, complete_run
    create_run(tmp_path, run_id="2026-05-26-complete-test", tier="full")

    result = complete_run(tmp_path)

    assert result is not None
    assert result["run_id"] == "2026-05-26-complete-test"
    assert "completed_at" in result
    # The file is gone (archived)
    assert not (tmp_path / "current_run.json").exists()
```

**Step 2: Run to confirm failure.**

**Step 3: Implement**

Modify `complete_run` in `scripts/state.py`:

```python
def complete_run(state_dir: Path) -> dict | None:
    """Archive completed run to history. Returns the final run dict (with completed_at) before archiving."""
    run = load_run(state_dir)
    if run:
        run["completed_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_write(state_dir / CURRENT_RUN_FILE, run)
    _archive_run(state_dir)
    return run
```

Only the return type changes (was `-> None`). The behavior order — write completed-at, then archive — is unchanged. All existing callers ignore the return value, so this is backwards-compatible.

**Step 4: Run full state tests**

Run: `pytest tests/test_state.py -v`
Expected: all pass, including any existing tests that called `complete_run` without expecting a return.

**Step 5: Commit.**

### Task 2.10 — Case-record writer stub (Stage B prep)

Stage A writes case records at completion; nothing reads them yet.

**Step 1: Write the failing test**

```python
def test_write_case_record(tmp_path):
    from state import write_case_record
    case_data = {
        "case_id": "2026-05-26-test",
        "version": 1,
        "query": "test research",
        "domain_tags": ["test"],
        "outcomes": {"sources_processed": 5},
    }
    # cases_dir is .research-workflow/cases under the vault root
    cases_dir = tmp_path / "cases"
    write_case_record(cases_dir, case_data)

    case_file = cases_dir / "2026-05-26-test.json"
    assert case_file.exists()
    import json
    assert json.loads(case_file.read_text()) == case_data
```

**Step 2: Run to confirm failure.**

**Step 3: Implement**

```python
def write_case_record(cases_dir: Path, case_data: dict) -> None:
    """Write a case record JSON. Creates the directory if needed."""
    cases_dir.mkdir(parents=True, exist_ok=True)
    case_id = case_data["case_id"]
    case_file = cases_dir / f"{case_id}.json"
    case_file.write_text(json.dumps(case_data, indent=2), encoding="utf-8", newline="\n")
```

**Step 4: Run to confirm pass.**

**Step 5: Commit.**

---

## Phase 3 — Playwright fallback in fetch_and_clean.py

Additive change to fetch pipeline. When Jina returns empty/blocked content for a URL, fall through to Playwright (if available).

### Task 3.1 — Tier detection for Playwright

**Files:**
- Modify: `scripts/detect_tier.py`
- Modify: `tests/test_detect_tier.py`

**Step 1: Find current tier detection pattern**

Run: `grep -n "ytdlp\|whisper" scripts/detect_tier.py`

Confirm there's an existing pattern for "is X installed and accessible." Follow it.

**Step 2: Write the failing test**

Append to `tests/test_detect_tier.py`:

```python
import sys   # already at module top in most tests; add if missing


def test_playwright_detection_when_unavailable(monkeypatch):
    from detect_tier import check_playwright
    # If playwright module is not installed, should return status="missing"
    monkeypatch.setitem(sys.modules, "playwright", None)
    result = check_playwright()
    assert result["status"] in {"missing", "error"}


def test_playwright_detection_when_available(monkeypatch):
    from detect_tier import check_playwright
    # Mock the playwright module as present
    fake_module = type(sys)("playwright")
    monkeypatch.setitem(sys.modules, "playwright", fake_module)
    result = check_playwright()
    # With the fake module injected, the import in check_playwright succeeds
    # and status MUST be "ok". Asserting strictly so a wiring regression fails loudly.
    assert result["status"] == "ok"
```

**Step 3: Run to confirm failure (function doesn't exist).**

**Step 4: Implement**

Add `check_playwright()` to `scripts/detect_tier.py`:

```python
def check_playwright() -> dict:
    """Detect whether Playwright is available for JS-heavy page extraction."""
    try:
        import playwright  # noqa: F401
        return {"status": "ok"}
    except ImportError:
        return {"status": "missing", "reason": "playwright package not installed"}
```

Wire it into `build_tier_report()` by adding to the `components` dict literal (around [detect_tier.py:172-185](../../scripts/detect_tier.py:172)) — there is no `report` local variable, the function builds the components dict inline then returns a dict literal at the bottom:

```diff
 components = {
     "ollama":  { ... },
     "searxng": { ... },
     "ytdlp":   {"status": "ok" if ytdlp.get("installed") else "missing"},
     "whisper": {"status": "ok" if whisper.get("installed") else "missing"},
+    "playwright": check_playwright(),
 }
```

Note: Playwright is OPTIONAL — it doesn't downgrade the tier (full tier doesn't require it). No changes to the `tier` / `missing_for_full` / `missing_for_mid` logic.

**Step 5: Run to confirm pass.**

**Step 6: Commit.**

### Task 3.2 — Playwright fetcher module

**Files:**
- Create: `scripts/fetch_playwright.py`
- Create: `tests/test_fetch_playwright.py`

The existing fetch API in `scripts/fetch_and_clean.py` is **tuple-based**:

```python
fetch_via_jina(url, api_key)     -> (content, title)
fetch_via_wayback(url, api_key)  -> (content, title)
fetch_url(url, jina_api_key)     -> (content, title, method)   # main composer
```

To compose, `fetch_via_playwright` returns the same `(content, title)` shape:

**Step 1: Write the failing test**

```python
# tests/test_fetch_playwright.py
import sys
import pytest


def test_playwright_unavailable_raises(monkeypatch):
    """When playwright module isn't installed, fetch_via_playwright raises ImportError-like RuntimeError."""
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    from fetch_playwright import fetch_via_playwright
    with pytest.raises(RuntimeError, match="playwright not available"):
        fetch_via_playwright("https://example.com")
```

The function raises (not returns None) when playwright is unavailable, so callers can distinguish "tried Playwright and it's not installed" from "tried Playwright and the page failed". This matches `fetch_url`'s try/except pattern.

**Step 2: Run to confirm failure (module doesn't exist).**

**Step 3: Implement**

```python
# scripts/fetch_playwright.py
"""fetch_playwright.py — JS-heavy page extraction fallback.

Used by fetch_and_clean.fetch_url() as a fallback when Jina and Wayback both fail.
Returns (content, title) — same shape as fetch_via_jina and fetch_via_wayback.
"""

def fetch_via_playwright(url: str, timeout_ms: int = 15000) -> tuple[str, str]:
    """Fetch a URL with Playwright. Returns (content, title).

    Raises RuntimeError if Playwright isn't installed or the page fails to load.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("playwright not available") from e

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            content = page.content()
            title = page.title() or ""
            browser.close()
            return content, title
    except Exception as e:
        raise RuntimeError(f"playwright fetch failed: {e}") from e
```

**Step 4: Run to confirm pass.**

**Step 5: Commit.**

### Task 3.3 — Wire Playwright into `fetch_url()` (the existing composer)

**Files:**
- Modify: `scripts/fetch_and_clean.py`
- Modify: `tests/test_fetch_and_clean.py`

**Important:** `fetch_url()` at [scripts/fetch_and_clean.py:210-228](../../scripts/fetch_and_clean.py:210) is the single per-URL composer used by BOTH `process_urls` (serial) and `_fetch_single` (parallel worker). Wire Playwright as a fallback INSIDE `fetch_url` so both callers benefit without duplication. Do NOT introduce a parallel `fetch_one_url()` function — that would skip the parallel path.

**Step 1: Write the failing tests**

Append to `tests/test_fetch_and_clean.py`:

```python
MIN_USEFUL_CONTENT_CHARS = 200  # threshold used by fetch_url's thin-content detection


def test_fetch_url_falls_back_to_playwright_when_jina_and_wayback_fail(monkeypatch):
    """When both Jina and Wayback raise, fetch_url uses Playwright as the final fallback."""
    from fetch_and_clean import fetch_url

    def jina_fails(url, key=None):
        raise RuntimeError("jina down")
    def wayback_fails(url, key=None):
        raise RuntimeError("no wayback snapshot")
    def playwright_succeeds(url, **kw):
        return ("Real JS-page content here, longer than 200 chars. " * 10, "JS Page Title")

    monkeypatch.setattr("fetch_and_clean.fetch_via_jina", jina_fails)
    monkeypatch.setattr("fetch_and_clean.fetch_via_wayback", wayback_fails)
    monkeypatch.setattr("fetch_and_clean.fetch_via_playwright", playwright_succeeds)

    content, title, method = fetch_url("https://example-spa.com")
    assert "Real JS-page content" in content
    assert title == "JS Page Title"
    assert method == "playwright"


def test_fetch_url_thin_jina_content_falls_through_to_playwright(monkeypatch):
    """When Jina returns success but the content is below the useful threshold,
    fetch_url tries Wayback then Playwright. This catches blocked-page / cookie-wall
    cases where Jina 200s but the body is empty."""
    from fetch_and_clean import fetch_url

    monkeypatch.setattr(
        "fetch_and_clean.fetch_via_jina",
        lambda url, key=None: ("", ""),  # empty content (think: bot wall)
    )
    monkeypatch.setattr(
        "fetch_and_clean.fetch_via_wayback",
        lambda url, key=None: ("", ""),  # also thin
    )
    monkeypatch.setattr(
        "fetch_and_clean.fetch_via_playwright",
        lambda url, **kw: ("Real content from JS execution. " * 20, "JS Title"),
    )

    content, title, method = fetch_url("https://example-spa.com")
    assert method == "playwright"
    assert "Real content" in content


def test_fetch_url_skips_playwright_when_jina_returns_useful_content(monkeypatch):
    """When Jina returns substantial content, Playwright must not be invoked."""
    from fetch_and_clean import fetch_url

    monkeypatch.setattr(
        "fetch_and_clean.fetch_via_jina",
        lambda url, key=None: ("Jina content. " * 50, "Jina Title"),
    )
    called = []
    monkeypatch.setattr(
        "fetch_and_clean.fetch_via_playwright",
        lambda url, **kw: called.append(url) or ("", ""),
    )

    content, title, method = fetch_url("https://example.com")
    assert method == "jina"
    assert called == []  # Playwright never invoked
```

**Step 2: Run to confirm failure (thin-content branch not implemented yet).**

**Step 3: Implement**

In `scripts/fetch_and_clean.py`:

1. Add at top: `from fetch_playwright import fetch_via_playwright`
2. Add a module-level threshold constant: `MIN_USEFUL_CONTENT_CHARS = 200`
3. Extend `fetch_url()` (lines 210-228) to add (a) thin-content detection after a successful Jina or Wayback call, and (b) Playwright as a final fallback:

```python
MIN_USEFUL_CONTENT_CHARS = 200  # below this, content is likely empty/blocked


def fetch_url(url: str, jina_api_key: str | None = None) -> tuple[str, str, str]:
    """
    Fetch URL content with fallback strategy.
    Returns (content, title, method) where method is "jina", "wayback", or "playwright".
    Raises RuntimeError if all methods fail.

    Treats "succeeded but returned thin content" the same as "raised" — falls through
    to the next fetcher. This catches the case where Jina/Wayback return 200 but the
    page body is empty/blocked/captcha-walled.
    """
    try:
        content, title = fetch_via_jina(url, jina_api_key)
        if len(content) >= MIN_USEFUL_CONTENT_CHARS:
            return content, title, "jina"
        print(f"[fetch_and_clean] Jina returned thin content ({len(content)} chars) for {url}; falling through", file=sys.stderr)
    except ValueError:
        raise  # SSRF validation errors should not be retried
    except Exception as exc:
        print(f"[fetch_and_clean] Jina fetch failed for {url}: {exc}", file=sys.stderr)

    try:
        content, title = fetch_via_wayback(url, jina_api_key)
        if len(content) >= MIN_USEFUL_CONTENT_CHARS:
            return content, title, "wayback"
        print(f"[fetch_and_clean] Wayback returned thin content ({len(content)} chars) for {url}; falling through", file=sys.stderr)
    except Exception as exc:
        print(f"[fetch_and_clean] Wayback fetch failed for {url}: {exc}", file=sys.stderr)

    # Final fallback: Playwright (only if installed)
    try:
        content, title = fetch_via_playwright(url)
        if len(content) >= MIN_USEFUL_CONTENT_CHARS:
            return content, title, "playwright"
        raise RuntimeError(f"Playwright returned thin content ({len(content)} chars)")
    except Exception as e:
        raise RuntimeError(f"All fetch methods failed for {url}") from e
```

The function signature and return type are unchanged. The `method` field already propagates into fetched URL records.

**Step 4: Update pre-existing tests that use short mock bodies**

The new threshold (200 chars) breaks pre-existing tests in `tests/test_fetch_and_clean.py` that use bodies like `"content"` (7 chars) and `"archived content"` (16 chars). Those would now fall through to the next fetcher, not return the expected `"jina"` / `"wayback"` method.

Update the existing mocks to use bodies above the threshold. Specifically:

```diff
-def test_fetch_url_uses_jina_first():
-    from fetch_and_clean import fetch_url
-    with patch("fetch_and_clean.fetch_via_jina", return_value=("content", "title")) as mock_jina:
-        content, title, method = fetch_url("https://example.com")
-    assert method == "jina"
-    mock_jina.assert_called_once()
+def test_fetch_url_uses_jina_first():
+    from fetch_and_clean import fetch_url
+    long_body = "Real Jina content. " * 20  # 380 chars — above MIN_USEFUL_CONTENT_CHARS
+    with patch("fetch_and_clean.fetch_via_jina", return_value=(long_body, "title")) as mock_jina:
+        content, title, method = fetch_url("https://example.com")
+    assert method == "jina"
+    mock_jina.assert_called_once()


-def test_fetch_url_falls_back_to_wayback_when_jina_fails():
-    from fetch_and_clean import fetch_url
-    with patch("fetch_and_clean.fetch_via_jina", side_effect=Exception("timeout")):
-        with patch("fetch_and_clean.fetch_via_wayback", return_value=("archived content", "archived title")) as mock_wb:
-            content, title, method = fetch_url("https://example.com")
-    assert method == "wayback"
-    assert content == "archived content"
+def test_fetch_url_falls_back_to_wayback_when_jina_fails():
+    from fetch_and_clean import fetch_url
+    long_archived = "Archived content from the Wayback Machine. " * 10  # 430 chars
+    with patch("fetch_and_clean.fetch_via_jina", side_effect=Exception("timeout")):
+        with patch("fetch_and_clean.fetch_via_wayback", return_value=(long_archived, "archived title")) as mock_wb:
+            content, title, method = fetch_url("https://example.com")
+    assert method == "wayback"
+    assert content == long_archived
```

The `test_fetch_url_raises_when_both_fail` test (current line 143) **must also be updated** to patch `fetch_via_playwright` to raise. Otherwise the test will reach the real Playwright fallback — which would actually try a network fetch if Playwright is installed locally, breaking the offline guarantee:

```diff
 def test_fetch_url_raises_when_both_fail():
     from fetch_and_clean import fetch_url
     with patch("fetch_and_clean.fetch_via_jina", side_effect=Exception("jina fail")):
         with patch("fetch_and_clean.fetch_via_wayback", side_effect=Exception("wayback fail")):
-            with pytest.raises(RuntimeError, match="All fetch methods failed"):
-                fetch_url("https://example.com")
+            with patch("fetch_and_clean.fetch_via_playwright", side_effect=Exception("playwright fail")):
+                with pytest.raises(RuntimeError, match="All fetch methods failed"):
+                    fetch_url("https://example.com")
```

Rename if helpful (e.g., `test_fetch_url_raises_when_all_fail`) to reflect the three-fetcher reality.

**Step 5: Run to confirm pass**

Run: `pytest tests/test_fetch_and_clean.py -v`
Expected: all tests pass (including the updated pre-existing ones and the three new threshold tests).

**Step 6: Commit.**

---

## Phase 4 — search-agent updates

T1-T4 numeric scoring, `is_primary` boolean, `primary_type` enum.

### Task 4.1 — Update search-agent prompt

**Files:**
- Modify: `agents/search-agent.md`

**Step 1: Find the current scoring section**

Read `agents/search-agent.md` lines 49-72 (the "Evaluate and Score URLs" section).

**Step 2: Replace with the new tier+primary model**

Replace the "Evaluate and Score URLs" section with:

```markdown
## Step 2: Evaluate and Score URLs

For each candidate result, assign three signals:

**Relevance score (0.0-1.0):** How directly the result addresses the topic.
- 0.9-1.0 = directly addresses the core question
- 0.7-0.9 = strong coverage
- 0.4-0.7 = tangentially related
- below 0.4 = barely relevant; reject

**Credibility score (0.3-1.0) + tier bucket:**
- **T1 (0.9-1.0):** Academic journals, peer-reviewed papers, official government publications (.gov, .mil), court records, FOIA responses, .edu research output, legislative text, agency datasets.
- **T2 (0.7-0.9):** Established news media (newspapers, magazines), industry reports from named research firms, expert blogs by domain authorities, technical forums with strong editorial standards.
- **T3 (0.5-0.7):** Community resources, user documentation, social media from verified accounts, Wikipedia, listicles from named publications.
- **T4 (0.3-0.5):** Anonymous user forums, social media (unverified), personal blogs, opinion pieces from unnamed authors, comments sections.

Assign both the numeric `credibility_score` (e.g., 0.92) and the derived `tier` label (e.g., "T1"). The numeric score is the primary data; the tier is the bucket.

**is_primary (boolean):** Is this source the *originator* of the information, or analysis of someone else's data?
- `true` for: a government agency publishing its own data; a court releasing its own record; a company publishing about itself; a FOIA response; raw legislative text; peer-reviewed first-publication papers.
- `false` for: news coverage *about* a government program; analysis citing FOIA data; journalism citing court records; secondary research synthesizing others' work.

If `is_primary` is `true`, also set `primary_type` to one of:
- `agency_data` — government agency publishing its own data/records
- `legal_record` — court records, judgments, filings
- `foia` — FOIA response material
- `official_statement` — company/organization statement about itself
- `peer_reviewed` — first-publication peer-reviewed research

If `is_primary` is `false`, set `primary_type` to `null`.

**Selection rules:**
- Always prefer higher-tier (T1 > T2 > T3 > T4) at similar relevance.
- A T1 source at relevance 0.6 beats a T3 source at relevance 0.9.
- Prefer primary sources when available — primary T2 often beats secondary T1 for civic research.
- Skip URLs that appear in `existing_urls`.
- Skip: paywalled sites, aggregators without original content, obvious spam, social media posts (unless from verified official accounts), forum threads.
- Source count from depth:
  - `quick` → 5-7 URLs
  - `standard` → 8-12 URLs
  - `deep` → 15-20 URLs
  - `exhaustive` → 25+ URLs

Do not fetch the full content of any page. Use snippets and titles only for evaluation.
```

**Step 3: Update the Output section**

Replace the example output JSON block with the new schema:

```json
{
  "topic": "the topic string you were given",
  "depth": "standard",
  "queries_used": ["exact search query 1", "exact search query 2"],
  "selected_urls": [
    {
      "url": "https://...",
      "title": "page title",
      "snippet": "brief description from search results",
      "relevance_score": 0.85,
      "credibility_score": 0.95,
      "tier": "T1",
      "is_primary": true,
      "primary_type": "agency_data",
      "reason": "official government report on the topic"
    }
  ],
  "rejected_urls": [
    {
      "url": "https://...",
      "reason": "paywall",
      "tier": "T2"
    }
  ],
  "search_notes": "any observations about source availability"
}
```

Update the Input section to use `depth` instead of `priority`.

**Step 4: Commit**

```bash
git add agents/search-agent.md
git commit -m "feat(search-agent): T1-T4 numeric scoring + is_primary signal"
```

### Task 4.2 — Contract tests for search-agent output

**Files:**
- Create: `tests/test_search_agent_contract.py`

**Step 1: Write the contract validation tests**

```python
# tests/test_search_agent_contract.py
"""Contract tests for search-agent output schema.

These tests don't dispatch a real agent — they validate that any output
matching the spec can be parsed correctly downstream.
"""
import json
import pytest


def parse_search_output(text: str) -> dict:
    """Parse an agent response. First char must be `{`, last char `}`."""
    text = text.strip()
    if not (text.startswith("{") and text.endswith("}")):
        raise ValueError("Response must be a single raw JSON object")
    return json.loads(text)


def test_valid_search_response_parses():
    response = json.dumps({
        "topic": "SC ALPR programs",
        "depth": "standard",
        "queries_used": ["SC ALPR site:.gov"],
        "selected_urls": [
            {
                "url": "https://sled.sc.gov/data",
                "title": "SLED ALPR data",
                "snippet": "Official SLED data on ALPR usage",
                "relevance_score": 0.92,
                "credibility_score": 0.95,
                "tier": "T1",
                "is_primary": True,
                "primary_type": "agency_data",
                "reason": "Official agency data",
            }
        ],
        "rejected_urls": [],
        "search_notes": "",
    })
    parsed = parse_search_output(response)
    assert parsed["selected_urls"][0]["tier"] == "T1"
    assert parsed["selected_urls"][0]["is_primary"] is True
    assert parsed["selected_urls"][0]["primary_type"] == "agency_data"


def test_secondary_source_has_null_primary_type():
    response = json.dumps({
        "topic": "X",
        "depth": "quick",
        "queries_used": [],
        "selected_urls": [
            {
                "url": "https://example.com",
                "title": "X",
                "snippet": "",
                "relevance_score": 0.7,
                "credibility_score": 0.75,
                "tier": "T2",
                "is_primary": False,
                "primary_type": None,
                "reason": "",
            }
        ],
        "rejected_urls": [],
        "search_notes": "",
    })
    parsed = parse_search_output(response)
    assert parsed["selected_urls"][0]["is_primary"] is False
    assert parsed["selected_urls"][0]["primary_type"] is None


def test_tier_consistent_with_credibility_score():
    """Tier and credibility_score should be consistent per the bucket boundaries."""
    from confidence import tier_from_score
    bucketed = tier_from_score(0.92)
    assert bucketed == "T1"
    bucketed = tier_from_score(0.75)
    assert bucketed == "T2"
```

**Step 2: Run to confirm pass**

Run: `pytest tests/test_search_agent_contract.py -v`
Expected: PASS (no implementation needed — these test parsing logic and the helper from Phase 1).

**Step 3: Commit**

```bash
git add tests/test_search_agent_contract.py
git commit -m "test(search-agent): contract tests for T1-T4 + is_primary output"
```

---

## Phase 5 — classify-agent contradiction extension

### Task 5.1 — Update classify-agent prompt

**Files:**
- Modify: `agents/classify-agent.md`

**Step 1: Read the current agent prompt**

Read `agents/classify-agent.md` end-to-end. Identify the "Output" section.

**Step 2: Append contradiction detection instructions**

Add a new "Step 4: Detect Contradictions" section after the existing classification steps:

```markdown
## Step 4: Detect Contradictions

Scan `key_claims` across all input summaries. Identify pairs of claims that contradict each other on a factual matter. A contradiction is:
- Two sources stating opposing facts about the same event, entity, or quantity.
- A source asserting X happened while another asserts X did not happen.
- Quantitative disagreement that exceeds normal variance (e.g., "1,000 ALPR cameras" vs "10,000 ALPR cameras" in the same jurisdiction).

Do NOT flag as contradictions:
- Different framings of the same fact (one source's "controversial" is another's "innovative")
- Different sources covering different aspects of the same topic
- Outdated information (one source from 2020 vs one from 2024 reporting current state)

For each contradiction found, record:
- `claim_a`, `claim_b` — the two contradicting claims (verbatim or paraphrased ≤25 words each)
- `source_a`, `source_b` — the source URLs
- `tier_a`, `tier_b` — the tier of each source
- `nature` — one of `factual` (verifiable disagreement), `interpretive` (different reading of same data), `temporal` (different points in time), `jurisdictional` (different regions)
```

**Step 3: Update the Output schema**

In the Output JSON example, add the `contradictions_detected` field:

```json
{
  "topic": "...",
  "notes_to_create": [ ... ],
  "vault_context": { ... },
  "contradictions_detected": [
    {
      "claim_a": "Flock Safety shares ALPR data with federal agencies via formal agreement",
      "claim_b": "Flock Safety claims no formal federal data sharing agreements exist",
      "source_a": "https://...",
      "source_b": "https://...",
      "tier_a": "T2",
      "tier_b": "T2",
      "nature": "factual"
    }
  ]
}
```

If no contradictions are found, return `"contradictions_detected": []`.

**Step 4: Commit**

```bash
git add agents/classify-agent.md
git commit -m "feat(classify-agent): detect cross-source contradictions"
```

### Task 5.2 — Contract test for contradiction output

**Files:**
- Create: `tests/test_classify_agent_contract.py`

```python
import json


def test_classify_output_has_contradictions_field():
    response = json.dumps({
        "topic": "X",
        "notes_to_create": [],
        "vault_context": {"existing_notes_found": [], "suggested_moc_update": None,
                          "folder_conventions": {}},
        "contradictions_detected": [],
    })
    parsed = json.loads(response)
    assert "contradictions_detected" in parsed
    assert isinstance(parsed["contradictions_detected"], list)


def test_classify_contradiction_shape():
    response = json.dumps({
        "topic": "X",
        "notes_to_create": [],
        "vault_context": {"existing_notes_found": [], "suggested_moc_update": None,
                          "folder_conventions": {}},
        "contradictions_detected": [
            {
                "claim_a": "A",
                "claim_b": "B",
                "source_a": "url_a",
                "source_b": "url_b",
                "tier_a": "T1",
                "tier_b": "T2",
                "nature": "factual",
            }
        ],
    })
    parsed = json.loads(response)
    c = parsed["contradictions_detected"][0]
    assert {"claim_a", "claim_b", "source_a", "source_b", "tier_a", "tier_b", "nature"} <= c.keys()
    assert c["nature"] in {"factual", "interpretive", "temporal", "jurisdictional"}
```

**Step 1: Run to confirm pass** (pure parsing tests).

**Step 2: Commit.**

---

## Phase 6 — topic-resolver upgrade

Sonnet model, strategy classification, per-topic depth assignment.

### Task 6.1 — Update topic-resolver prompt

**Files:**
- Modify: `agents/topic-resolver.md`

**Step 1: Change the frontmatter `model: haiku` to `model: sonnet`**

```diff
- model: haiku
+ model: sonnet
```

**Step 2: Add strategy classification step**

Insert a new "Step 0: Classify Strategy" section at the top of the Steps:

```markdown
## Step 0: Classify Strategy

Before resolving topics, classify the user's prompt into one of three strategies:

- **`planning_only`** — clear single topic with specific terms. Examples:
  - "Research SC bill H.3456"
  - "Look into Greenville County's ALPR program"
  - "What does Flock Safety's 2024 SEC filing say about federal contracts?"

- **`intent_planning`** — single topic with ambiguous terms, OR a batch with shared but unclear intent. Examples:
  - "Research surveillance issues" → ambiguous (which state? what aspect?)
  - "Research these 5 bills" → may need clarification on scope (legislative analysis vs political angle)

- **`unified`** — multi-topic batch with clear individual topics, OR thread-pull from vault notes, OR mixed-source (local files + topics). Examples:
  - "Research ALPR programs in Greenville, Spartanburg, and Anderson counties"
  - "[[Some Vault Note]] — find more leads from this"
  - "Research these companies: ..." (with multiple specific company names)

If `intent_planning` is selected:
- For single ambiguous topic: produce up to 3 clarifying questions, return them in `clarifying_questions` (and DO NOT resolve topics yet). The orchestrator will present them to the user.
- For ambiguous batch intent: produce 1 batch-level question.

If `planning_only` or `unified` is selected: proceed to resolve topics normally.
```

**Step 3: Replace `priority` with `depth` throughout the prompt**

In Step 2 ("Parse Topics"), replace:

```diff
- 2. **Assign priority tiers.**
-    - `deep` -- the topic is the primary focus, needs thorough multi-source coverage
-    - `standard` -- supporting topic, 3-5 good sources sufficient
-    - `scan` -- peripheral topic, 1-3 sources for basic awareness
+ 2. **Assign depth profile.** Each topic gets one of `quick`, `standard`, `deep`, `exhaustive`.
+    Signals to detect from the prompt:
+    - Words like "deeply", "thoroughly", "comprehensive" → `deep` or `exhaustive`
+    - Words like "quickly", "scan", "brief", "just" → `quick`
+    - Topic specificity: named bill/specific incident → `standard` (or `deep` if prompt emphasizes thoroughness)
+    - Broad theme or named entity without further context → match prompt signals or default to `standard`
+    - When no signal is detectable, default to `standard`.
```

**Step 4: Update the Output schema**

Add to the top-level JSON output:
- `"strategy": "planning_only" | "intent_planning" | "unified"`
- `"clarifying_questions": [...]` (only present when strategy is `intent_planning`; otherwise omit or set to `[]`)

Replace per-topic `"priority"` with `"depth"`:

```diff
-      "priority": "deep",
+      "depth": "standard",
```

**Step 5: Commit**

```bash
git add agents/topic-resolver.md
git commit -m "feat(topic-resolver): upgrade to Sonnet, add strategy + depth assignment"
```

### Task 6.2 — Contract test for topic-resolver output

**Files:**
- Create: `tests/test_topic_resolver_contract.py`

```python
import json
import pytest


def test_planning_only_response():
    response = json.dumps({
        "project": "SC H.3456 Research",
        "strategy": "planning_only",
        "shared_context_files": [],
        "topics": [
            {
                "topic": "SC bill H.3456",
                "mode": "web_research",
                "depth": "standard",
                "existing_urls": [],
                "related_vault_notes": [],
            }
        ],
        "local_sources": [],
        "thread_pulls": [],
        "execution_order": "parallel",
        "estimated_usage": {},
    })
    parsed = json.loads(response)
    assert parsed["strategy"] == "planning_only"
    assert parsed["topics"][0]["depth"] == "standard"
    assert "priority" not in parsed["topics"][0]


def test_intent_planning_response():
    response = json.dumps({
        "strategy": "intent_planning",
        "clarifying_questions": [
            "Which state are you focused on?",
            "Are you looking for legislative analysis or political angle?",
        ],
        # Other fields may be empty since topics aren't resolved yet
        "project": "",
        "topics": [],
        "local_sources": [],
        "thread_pulls": [],
    })
    parsed = json.loads(response)
    assert parsed["strategy"] == "intent_planning"
    assert len(parsed["clarifying_questions"]) <= 3


def test_depth_value_in_response_is_valid():
    """A topic's depth field must be one of the four valid profile names."""
    response = json.dumps({
        "project": "X",
        "strategy": "planning_only",
        "shared_context_files": [],
        "topics": [{"topic": "T", "mode": "web_research", "depth": "standard",
                    "existing_urls": [], "related_vault_notes": []}],
        "local_sources": [],
        "thread_pulls": [],
        "execution_order": "parallel",
        "estimated_usage": {},
    })
    parsed = json.loads(response)
    valid_depths = {"quick", "standard", "deep", "exhaustive"}
    for topic in parsed["topics"]:
        assert topic["depth"] in valid_depths, f"invalid depth: {topic['depth']!r}"


def test_strategy_value_is_valid():
    """Top-level strategy must be one of three values; rejects malformed responses."""
    response = json.dumps({
        "project": "X",
        "strategy": "unified",
        "shared_context_files": [],
        "topics": [],
        "local_sources": [],
        "thread_pulls": [],
        "execution_order": "parallel",
        "estimated_usage": {},
    })
    parsed = json.loads(response)
    valid_strategies = {"planning_only", "intent_planning", "unified"}
    assert parsed["strategy"] in valid_strategies, f"invalid strategy: {parsed['strategy']!r}"
```

These tests are still simple parse-and-check, but they actually verify what they claim — they parse a representative response and check that the *parsed* values are in the valid set. The earlier tautologies (`assert depth in valid_depths` after iterating `valid_depths`) have been removed.

**Step 1: Run to confirm pass.**

**Step 2: Commit.**

---

## Phase 7 — hop-planner agent

### Task 7.1 — Create hop-planner agent definition

**Files:**
- Create: `agents/hop-planner.md`

**Step 1: Write the agent definition**

```markdown
---
name: hop-planner
description: Between-hop reasoning for the research pipeline. Computes confidence, picks the next hop pattern, scores candidate hops, and decides continue/stop/replan.
model: sonnet
tools:
  - Read
  - Bash
---

# Hop Planner Agent

## Your Role

**Do not write, create, edit, or delete any files.**

**Output only the single JSON object described in the Output section. No narration, no explanation, no backticks.**

You run between hops in the multi-hop research pipeline. Given the summaries collected so far for one topic, you decide:
1. Has confidence reached the target? If yes → stop.
2. If not, what's the highest-value next hop to take?
3. Are we in a state that requires replanning?

---

## Input

You will receive:
- `topic` — the research topic string
- `depth` — `quick` / `standard` / `deep` / `exhaustive`
- `current_hop` — integer (1-indexed) for the hop that just completed
- `max_hops` — derived from depth
- `confidence_target` — derived from depth (0.6 / 0.7 / 0.8 / 0.9)
- `summaries_so_far` — array of summaries from all hops so far
- `sources_so_far` — array of source records with tier, credibility_score, is_primary
- `hop_genealogy` — array of prior hop records (pattern, from, sources_kept)
- `seen_urls` — URLs already fetched (for novelty checks on candidates)
- `vault_index_path` — path to vault FTS5 index (for novelty checks)

---

## Step 1: Compute Confidence

Call the confidence formula on `sources_so_far`:

```bash
python -c "
import sys, json
sys.path.insert(0, '{scripts_dir}')
from confidence import compute_confidence
sources = json.loads(open('{sources_file}').read())
print(compute_confidence(sources, depth='{depth}'))
"
```

Record the resulting score.

---

## Step 2: Compute Contradiction Rate

If contradictions have been detected by classify-agent (in a prior pass), the orchestrator passes them in. Otherwise this is 0.0 for now.

---

## Step 3: Decide Continue / Stop / Replan

- If `confidence_score >= confidence_target` AND `contradiction_rate <= 0.3`: `decision: "stop"`. No `next_hop`.
- If `current_hop >= max_hops`: `decision: "stop"`. No `next_hop`.
- If `confidence_score < confidence_target * 0.7` AND `current_hop == 1`: `decision: "replan"`. Indicates the initial search angle was wrong; the orchestrator will reset and re-search.
- Otherwise: `decision: "continue"`. Proceed to Step 4 to pick the next hop.

---

## Step 4: Pick the Next Hop Pattern

Choose one of four patterns based on what's been found and what's missing:

- **`entity_expansion`** — explore entities mentioned in summaries (people, orgs, programs, technologies). Use when summaries mention important entities that haven't been investigated.
- **`temporal_progression`** — follow chronological development (current → recent → historical, or vice versa). Use when temporal context is missing.
- **`conceptual_deepening`** — drill into mechanisms, details, examples, edge cases of the topic. Use when overview is in place but understanding of how/why is shallow.
- **`causal_chain`** — trace cause and effect (effect → immediate cause → root cause; problem → contributing factors). Use when summaries describe outcomes but not their drivers.

Avoid repeating a pattern from `hop_genealogy` unless the prior attempt failed (early-terminated).

---

## Step 5: Score Candidate Hops

For each candidate target (entity, time period, concept, cause), score 0-10 using:

- **Frequency (0-3):** how many summaries mention this candidate
- **Novelty (0-3):** is this new to the vault? Query the vault index via Bash to check.
- **Connectedness (0-2):** does it relate to multiple existing vault notes?
- **Specificity (0-2):** is this a named entity / bill number / data point (high), a named person/org (medium), or a vague concept (low)?

Pick the highest-scoring candidate as `next_hop.from`. Record 1-2 runner-up alternatives.

---

## Step 6: Write Self-Reflection

In `self_reflection`, briefly state (≤80 words):
- Whether confidence is improving or stagnant
- What gap remains (which kind of source is missing? which entity needs deeper coverage?)
- Why the chosen next hop addresses that gap

---

## Output

```
{
  "topic": "...",
  "current_hop": 2,
  "decision": "continue",
  "confidence_score": 0.68,
  "contradiction_rate": 0.22,
  "next_hop": {
    "pattern": "causal_chain",
    "from": "Flock Safety federal data sharing",
    "rationale": "Multiple sources reference federal sharing but none provide the actual agreements.",
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
  "self_reflection": "Confidence below target (0.68 vs 0.7). Source diversity is good but we lack primary sources on federal sharing specifically. Causal chain on that entity is the highest-value next step."
}
```

**Field notes:**
- `decision` is one of: `continue` / `stop` / `replan`
- `next_hop` is `null` when `decision == "stop"`
- For `replan`: include a `replan_hint` field instead of `next_hop`:

```
"replan_hint": {
  "issue": "initial search returned only T3 sources",
  "suggested_pattern": "entity_expansion",
  "suggested_query_focus": "official agency data on SC ALPR usage"
}
```
```

**Step 2: Commit**

```bash
git add agents/hop-planner.md
git commit -m "feat(hop-planner): new Sonnet agent for between-hop reasoning"
```

### Task 7.2 — Contract test for hop-planner output

**Files:**
- Create: `tests/test_hop_planner_contract.py`

```python
import json


def test_hop_planner_continue_response():
    response = json.dumps({
        "topic": "X",
        "current_hop": 2,
        "decision": "continue",
        "confidence_score": 0.68,
        "contradiction_rate": 0.22,
        "next_hop": {
            "pattern": "causal_chain",
            "from": "federal data sharing",
            "rationale": "...",
            "candidate_score": {"frequency": 3, "novelty": 3, "connectedness": 1, "specificity": 2, "total": 9},
            "runner_up_alternatives": [],
        },
        "self_reflection": "...",
    })
    parsed = json.loads(response)
    assert parsed["decision"] == "continue"
    assert parsed["next_hop"]["pattern"] in {
        "entity_expansion", "temporal_progression", "conceptual_deepening", "causal_chain"
    }


def test_hop_planner_stop_response():
    response = json.dumps({
        "topic": "X",
        "current_hop": 3,
        "decision": "stop",
        "confidence_score": 0.82,
        "contradiction_rate": 0.1,
        "next_hop": None,
        "self_reflection": "Confidence target met.",
    })
    parsed = json.loads(response)
    assert parsed["decision"] == "stop"
    assert parsed["next_hop"] is None


def test_hop_planner_replan_response():
    response = json.dumps({
        "topic": "X",
        "current_hop": 1,
        "decision": "replan",
        "confidence_score": 0.31,
        "contradiction_rate": 0.0,
        "replan_hint": {
            "issue": "initial search returned only T3 sources",
            "suggested_pattern": "entity_expansion",
            "suggested_query_focus": "official agency data",
        },
        "self_reflection": "...",
    })
    parsed = json.loads(response)
    assert parsed["decision"] == "replan"
    assert "replan_hint" in parsed
```

**Step 1: Run to confirm pass.**

**Step 2: Commit.**

### Task 7.3 — Register hop-planner in plugin.json

**Files:**
- Modify: `.claude-plugin/plugin.json` (or wherever the plugin manifest lives)

**Step 1: Find the manifest**

Run: `find . -name plugin.json -not -path './.git/*'`

There may be multiple — the root one for development, plus possibly a copy under `.claude-plugin/`.

**Step 2: Read the current agents declaration**

Read the manifest. Find the agents list (or auto-discovery section).

**Step 3: Add hop-planner**

If agents are explicitly listed: add `hop-planner` to the list.
If auto-discovered from `agents/`: no change needed (file presence is enough).

Run: `cat .claude-plugin/plugin.json | python -m json.tool`

Confirm the manifest validates.

**Step 4: Commit (if any changes)**

```bash
git add .claude-plugin/plugin.json
git commit -m "chore(plugin): register hop-planner agent"
```

---

## Phase 8 — SKILL.md rewrite

The orchestrator gets a comprehensive rewrite. Split into sub-tasks by stage area.

### Task 8.1 — Header + bootstrap (Stages 0-1)

**Files:**
- Modify: `skills/research/SKILL.md`

**Step 1: Back up the current SKILL.md**

```bash
cp skills/research/SKILL.md skills/research/SKILL.md.v2.bak
git rm --cached skills/research/SKILL.md.v2.bak 2>/dev/null || true   # don't track the backup
echo "skills/research/SKILL.md.v2.bak" >> .gitignore
```

Stage A doesn't ship the backup — it's only for local reference during the rewrite. Commit the .gitignore change separately:

```bash
git add .gitignore
git commit -m "chore: ignore SKILL.md backup file during v3 rewrite"
```

**Step 2: Open SKILL.md and confirm the new shape**

The new SKILL.md will replace the old 10-stage linear pipeline with the new shape from the design doc. Section structure:

```
# Header (intro + Bootstrap Constants)
## Stage 0: Load Config and Detect Tier
## Stage 1: Check for Active Run
## Stage 2: Triage (NEW)
## Stage 3: Resolve
## Stage 4: Hop Loop (NEW)
## Stage 5: Quality Gate (NEW)
## Stage 6: Classify
## Stage 7: Write Notes
## Stage 8: Wikilink Scan
## Stage 9: Discover Threads
## Stage 10: Complete (with telemetry)
## Error Handling
## Resume Flow
```

For this task, only update the Header + Stages 0-1. Keep Stages 2-10 as-is from the v2 SKILL.md temporarily; subsequent tasks will rewrite them in order.

**Step 3: Update the Header**

Replace lines 1-22 with:

```markdown
---
name: research
description: 'Deep research pipeline for Obsidian vaults. Usage: /research "topic or natural language prompt". Supports batch research, thread-pulling from vault notes, local file ingestion, and multi-hop investigation with confidence-based replanning.'
---

# Research — v3 Orchestrator (Multi-Hop Pipeline)

You are the orchestrator. You run a stateful multi-stage research pipeline that searches, fetches, summarizes, classifies, and writes vault notes — with optional multi-hop investigation gated by confidence scoring. You dispatch Haiku subagents for cheap parallel work, Sonnet for resolver and hop-planner, and write final notes yourself (or escalate to Opus for synthesis notes).

## Bootstrap Constants

- `VAULT` = `{{VAULT_ROOT}}`
- `REPO` = `{{REPO_ROOT}}`
- `SCRIPTS` = `REPO/scripts`
- `STATE_DIR` = `VAULT/.research-workflow/state`
- `CASES_DIR` = `VAULT/.research-workflow/cases`
```

**Step 4: Stage 0 — no functional change; keep existing logic**

Verify Stage 0 still works for the v3 schema. It should — Stage 0 only loads config and detects tier; it doesn't touch run state.

**Step 5: Stage 1 — schema-mismatch handling**

The active-run-check stays the same, but the resume flow needs to handle v2→v3 mismatch silently (Task 2.2 already implemented this in `state.py.load_run()`). The SKILL.md change is just to add a note in the resume prompt:

After the existing "Incomplete run detected: ..." block, add:

```
If state.py.load_run() returned None and the user just ran /research (no other reason for that), it may be that an old-schema run was abandoned silently. Stage 0's load already printed the message — no further action needed.
```

**Step 6: Commit**

```bash
git add skills/research/SKILL.md
git commit -m "feat(skill): v3 header + stages 0-1 with schema-aware resume"
```

### Task 8.2 — Stage 2: Triage (new)

**Files:**
- Modify: `skills/research/SKILL.md`

**Step 1: Insert Stage 2 (Triage) before the existing Stage 2 (now Stage 3)**

Add a new "Stage 2: Triage" section between Stage 1 and the current Stage 2 (which becomes Stage 3):

```markdown
## Stage 2: Triage

The resolver classifies the prompt's strategy before resolving topics. The run is created at the START of this stage so that any downstream state-writing helper (`save_state`, `record_hop`, `add_usage`, etc.) has somewhere to write to — even when the planning_only path bypasses Stage 3's full approval flow.

### 2a. Create the run

Generate a run ID from the current date and a slugified version of the user's input (e.g., `2026-03-05-sc-alpr-research`). Then:

```bash
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from state import create_run
from pathlib import Path
r = create_run(Path('STATE_DIR'), 'RUN_ID', 'TIER')
print(json.dumps(r))
"
```

The run begins with no topics; topics are populated after the resolver returns (in 2c.iv or Stage 3).

### 2b. Dispatch topic-resolver agent (Sonnet)

Read the agent definition: `REPO/agents/topic-resolver.md`

Dispatch via the Task tool:
- `subagent_type`: `general-purpose`
- `model`: `sonnet`
- `prompt`: The full contents of `agents/topic-resolver.md`, followed by a `---` separator, followed by:

```
prompt: {the user's original input}
vault_root: {VAULT}
scripts_dir: {SCRIPTS}
```

### 2c. Parse strategy and persist it

The agent returns a JSON object. Read the top-level `strategy` field.

**Persist the strategy immediately** — every path through Stage 2 ends up needing `run["strategy"]` set, so save it before branching. (`intent_planning` runs may re-dispatch in 2d and produce a different strategy; that re-dispatch overwrites this value.)

```bash
python -c "
import sys
sys.path.insert(0, 'SCRIPTS')
from state import load_run, save_state
from pathlib import Path
run = load_run(Path('STATE_DIR'))
run['strategy'] = 'STRATEGY_VALUE_FROM_RESOLVER'
save_state(Path('STATE_DIR'), run)
"
```

Then branch by strategy:

- `planning_only`: continue to Stage 2e (one-line confirm) with the resolved topics from this response.
- `intent_planning`: continue to Stage 2d (Q&A loop).
- `unified`: continue to Stage 3 (full resolve+plan flow with depth column). Note: the resolver has ALREADY produced topics; Stage 3 uses them rather than re-dispatching.

### 2d. Intent-planning Q&A (if applicable)

If strategy is `intent_planning`, the response contains `clarifying_questions[]` and topics are not yet resolved. For each question (max 3 for single-topic, max 1 for batch):

1. Present the question to the user.
2. Wait for the user's response.
3. Append the answer to the running prompt context.

After all questions are answered, re-dispatch the topic-resolver with the augmented prompt:

```
prompt: {original input}
clarifying_qa: {array of {question, answer} pairs}
vault_root: {VAULT}
scripts_dir: {SCRIPTS}
```

Expect the new response to have `strategy: "unified"` (rare cases: `planning_only`).

**Re-persist the strategy from the second response.** The first dispatch persisted `"intent_planning"` in 2c; that value is now stale because the clarified resolver may have returned a different strategy.

```bash
python -c "
import sys
sys.path.insert(0, 'SCRIPTS')
from state import load_run, save_state
from pathlib import Path
run = load_run(Path('STATE_DIR'))
run['strategy'] = 'NEW_STRATEGY_FROM_SECOND_DISPATCH'
save_state(Path('STATE_DIR'), run)
"
```

Then continue to 2e or Stage 3 accordingly.

If the user abandons mid-Q&A (cancel / explicit abort), call `abandon_run(STATE_DIR)` and stop.

### 2e. Planning-only confirm (skip if strategy is unified)

Only entered when strategy is `planning_only`. Show the user:

```
Researching {project} at depth {topic.depth}, ~{estimated_minutes}min. Proceed? [yes / edit / cancel]
```

- `yes`: initialize topics from the resolver response (see snippet below), then skip to Stage 4 (hop loop). Stage 3 is bypassed. Strategy was already persisted in 2c.
- `edit`: upgrade to `unified` strategy — present the full plan as in Stage 3d below. The run is already created; Stage 3 will populate topics and approve. Also overwrite `run['strategy'] = 'unified'` since the user chose to upgrade.
- `cancel`: call `abandon_run(STATE_DIR)` and stop.

When `yes`: initialize topics now (since Stage 3 is being skipped):

```bash
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from state import load_run, save_state, init_topic
from pathlib import Path
run = load_run(Path('STATE_DIR'))
plan_topics = RESOLVER_RESPONSE['topics']
run['topics'] = [init_topic(t['topic'], t['mode'], t['depth']) for t in plan_topics]
save_state(Path('STATE_DIR'), run)
"
```

Note: strategy persistence now happens once in Stage 2c (immediately after the resolver returns), so every path through Stage 2 ends with `run["strategy"]` set. No separate 2f step needed.
```

**Step 2: Commit**

```bash
git add skills/research/SKILL.md
git commit -m "feat(skill): add Stage 2 triage with strategy classification"
```

### Task 8.3 — Stage 3: Resolve (renumber + per-topic depth)

**Note on the new flow:** The existing Stage 2 (v2) did BOTH "create the run" and "dispatch the resolver" in one step. In v3, run creation moves to Stage 2a (Task 8.2), and the resolver is dispatched in 2b (also Task 8.2). So Stage 3 in v3 is just "present the plan and get approval" — the actual resolver dispatch is upstream.

**Step 1: Strip resolver-dispatch logic from Stage 3**

The existing Stage 2 (v2) lines 158-263 contain three substeps:
- 2a. Create a new run → MOVED to Stage 2a (Task 8.2)
- 2b. Dispatch topic-resolver agent → MOVED to Stage 2b (Task 8.2)
- 2c. Parse response → MOVED to Stage 2c (Task 8.2)
- 2d. Present plan for approval → KEEP, renumber to 3a
- 2e. Save plan → KEEP, renumber to 3b

After this refactor, Stage 3 is just "3a present plan for unified strategy approval" + "3b save the approved plan."

**Step 2: Update the plan presentation to show depth, not priority**

In the plan presentation block (3a, formerly 2d):

```diff
- Topics ({count}):
- {for each topic:}
-   - [{priority}] {topic} ({mode})
- {end}
+ Topics ({count}):
+ {for each topic:}
+   - [{depth}] {topic} ({mode})
+ {end}
```

Update the edit option: user can now edit topics, modes, AND depths.

**Step 3: Initialize per-topic state with depth**

In the "Save plan" subsection (3b, formerly 2e), update the state initialization to use `init_topic` for each topic. Note: the run already exists (created in Stage 2a), so we're appending topics to it, not creating it:

```bash
python -c "
import sys
sys.path.insert(0, 'SCRIPTS')
from state import load_run, save_state, init_topic
from pathlib import Path
run = load_run(Path('STATE_DIR'))
plan_topics = PLAN_JSON['topics']
run['topics'] = [init_topic(t['topic'], t['mode'], t['depth']) for t in plan_topics]
save_state(Path('STATE_DIR'), run)
"
```

**Step 4: Commit**

```bash
git commit -am "feat(skill): Stage 3 resolve with per-topic depth"
```

### Task 8.4 — Stage 4: Hop loop (new — largest task)

**Step 1: Insert Stage 4 (Hop Loop) replacing the old Stages 3-6**

Replace the old Stages 3-6 (Search, Fetch, Media, Summarize) with the new Stage 4 hop loop. Pseudo-code reference:

```
for hop_level in 1..max(topic.max_hops for topic in topics):
    active = [t for t in topics if t.status == "active" and t.current_hop < t.max_hops]
    if not active: break

    # 4a. Per-hop search (parallel across active topics, batched 5)
    for batch in groups_of(active, 5):
        dispatch search agents (Haiku) in parallel
        # If hop_level > 1, pass hop_context with seen_urls and the chosen pattern's "from"
    merge SearXNG if available

    # 4b. Per-hop fetch (Python script, parallel within)
    run fetch_and_clean.py with the new selected_urls
    write fetch_results_hop{N}.json

    # 4c. Per-hop media
    run fetch_media.py per article

    # 4d. Per-hop summarize
    if Ollama: run summarize.py
    else: dispatch Haiku per-article summarizers

    # 4e. Hop-planner (Sonnet, per-topic, parallel)
    for each active topic:
        load all_sources_so_far, summaries_so_far for that topic from per-hop files
        dispatch hop-planner with topic state
        parse decision:
            continue → record_hop(...) and prepare next hop
            stop     → mark_topic_status(topic, "complete")
            replan   → mark_topic_status(topic, "replan_pending"); orchestrator handles in Stage 5
```

Specific instructions (in the SKILL.md text):

```markdown
## Stage 4: Hop Loop

For each hop level from 1 to the maximum `max_hops` across all topics, run the search→fetch→media→summarize→hop-planner sequence for all topics that are still active at this level.

Loop structure:

```python
hop_level = 1
while any(t.status == "active" and t.current_hop < t.max_hops for t in run.topics):
    active = [t for t in run.topics if t.status == "active" and t.current_hop < t.max_hops]

    # 4a-4d: process this hop level for all active topics
    # See substages below.

    # 4e: hop-planner decides continue/stop/replan per topic
    for topic in active:
        dispatch hop-planner
        apply decision

    hop_level += 1
```

### 4a. Search (parallel across topics)

For each active topic, choose hop_context based on how the topic got admitted at this iteration:

- **Hop 1 (fresh topic):** dispatch search-agent normally with `topic`, `existing_urls`, `depth`. No hop_context preamble.

- **Hop 2+ following a hop-planner `continue` decision:** the prior hop-planner returned `next_hop`, which Stage 4e persisted to `topic.next_hop`. Read it from state:
  - `pattern`: `topic.next_hop.pattern`
  - `from`: `topic.next_hop.from`
  - `seen_urls`: the topic's seen_urls list

  After dispatching the search, call `set_next_hop(topic, None)` to clear the consumed direction (the upcoming hop-planner response will set a new one if continuing).

- **Hop following a quality-gate replan (Stage 5b or 5c re-admission):** the topic has a stored `replan_hint` instead of a prior `next_hop`. Use the hint's fields:
  - `pattern`: `topic.replan_hint.suggested_pattern`
  - `from`: `topic.replan_hint.suggested_query_focus` (treated as the focus topic/entity for the search)
  - `seen_urls`: the topic's seen_urls list
  - Optional: include the `issue` field as a brief addition to the preamble (e.g., "previous gap: thin sources")

  After consuming `replan_hint`, the orchestrator clears it via `set_replan_hint(topic, None)` so subsequent continue hops don't re-trigger the same focus.

The search-agent's prompt template doesn't change. The orchestrator prepends a hop-context preamble for hop 2+:

```
HOP CONTEXT: This is hop {N} of {max_hops} for topic "{topic}". Use the {pattern} pattern, focusing on "{from}". Skip URLs in seen_urls.
{if replan_hint: "Previous gap: " + replan_hint.issue}
```

Batch dispatches at ≤5 topics per round.

### 4b. Fetch

Run `fetch_and_clean.py` once for all active topics' selected URLs at this hop:

```bash
python "SCRIPTS/fetch_and_clean.py" --input "STATE_DIR/search_context_hop{N}.json" --output "STATE_DIR/fetch_results_hop{N}.json"
```

Update each topic's `seen_urls` with the URLs that were successfully fetched.

### 4c. Media

Run `fetch_media.py` per article as in v2, but write to per-hop temp dirs:

```bash
python "SCRIPTS/fetch_media.py" --content "STATE_DIR/content_hop{N}_{index}.md" --assets-dir "ASSETS_DIR" --topic "{topic_slug}" --run-id "{RUN_ID}" --output "STATE_DIR/rewritten_hop{N}_{index}.md"
```

### 4d. Summarize

Run `summarize.py` over the hop's fetch_results. Write to `summaries_hop{N}.json`.

### 4e. Hop-planner (parallel per-topic)

For each active topic at this hop level, dispatch the hop-planner agent (Sonnet):

- `subagent_type`: `general-purpose`
- `model`: `sonnet`
- `prompt`: The full contents of `agents/hop-planner.md`, followed by `---`, followed by:

```
topic: {topic.topic}
depth: {topic.depth}
current_hop: {hop_level}
max_hops: {topic.max_hops}
confidence_target: {get_depth_profile(topic.depth)["confidence_target"]}
summaries_so_far: {path to all summaries this topic has collected across all hops}
sources_so_far: {path to all sources this topic has collected}
hop_genealogy: {topic.hop_genealogy as JSON}
seen_urls: {topic.seen_urls}
vault_index_path: {VAULT}/.research-workflow/vault.db
scripts_dir: SCRIPTS
```

Parse each hop-planner response. All three branches first call `record_hop()` to persist what just happened, then differ in what they persist for the future:

- `decision == "continue"`:
  - `record_hop(topic, hop_data)` — persists the just-completed hop into genealogy and increments current_hop.
  - `set_next_hop(topic, response.next_hop)` — persists the planner's chosen pattern/from for Stage 4a to read on the next iteration.
  - `set_replan_hint(topic, None)` — clears any stale hint from a prior aborted replan.
  - Topic stays `active` for the next hop level.

- `decision == "stop"`:
  - `record_hop(topic, hop_data)` — persists the just-completed hop.
  - `set_next_hop(topic, None)` — no future hop.
  - `mark_topic_status(topic, "complete")`.

- `decision == "replan"`:
  - `record_hop(topic, hop_data)` — still persists the just-completed hop. The replan path doesn't discard history.
  - `set_next_hop(topic, None)` — the future direction comes from the replan_hint, not next_hop.
  - `set_replan_hint(topic, response.replan_hint)` — persists the planner's diagnosis for Stage 5 to read.
  - `mark_topic_status(topic, "replan_pending")`. The quality gate (Stage 5) handles re-admission.

For early-termination cases (Stage 4a returned zero sources after one alternate pattern attempt), the hop-planner can also return `decision: "stop"` with `status: "early_terminated"` — same as `stop` above, but call `mark_topic_status(topic, "early_terminated")` instead of `"complete"`.

### 4f. Persist hop-planner's quality signals

After each hop-planner response, persist BOTH the confidence score (append to history) and the contradiction rate (overwrite latest):

```bash
python -c "
import sys
sys.path.insert(0, 'SCRIPTS')
from state import append_confidence, set_contradiction_rate
from pathlib import Path
append_confidence(Path('STATE_DIR'), topic_name='TOPIC',
                  score=HOP_PLANNER_RESPONSE.confidence_score)
set_contradiction_rate(Path('STATE_DIR'), topic_name='TOPIC',
                       rate=HOP_PLANNER_RESPONSE.contradiction_rate)
"
```

Both signals feed the Stage 5 quality gate. Without the `set_contradiction_rate` call, `topic.contradiction_rate` stays at its `0.0` init forever and the contradiction-triggered replan branch never fires.

### 4g. Stage transition

When all topics have status != "active", transition to Stage 5:

```bash
python -c "
import sys
sys.path.insert(0, 'SCRIPTS')
from state import update_stage
from pathlib import Path
update_stage(Path('STATE_DIR'), 'quality_gate')
"
```
```

**Step 2: Commit**

This is the largest single edit. Verify the SKILL.md is still well-formed Markdown before committing.

```bash
git add skills/research/SKILL.md
git commit -m "feat(skill): Stage 4 multi-hop loop with hop-planner dispatch"
```

### Task 8.5 — Stage 5: Quality gate (new)

**Step 1: Insert Stage 5 after the hop loop**

```markdown
## Stage 5: Quality Gate

After all topics have status != "active", compute the run-level quality signals and decide whether to proceed to classify, auto-replan, or prompt the user.

### 5a. Compute per-topic pass/fail

Each topic has its own depth and therefore its own `confidence_target` (via `get_depth_profile(topic.depth)["confidence_target"]`). Check per-topic, not run-aggregate:

```python
from confidence import get_depth_profile

def topic_passes(t) -> bool:
    target = get_depth_profile(t["depth"])["confidence_target"]
    latest_conf = t["confidence_history"][-1] if t["confidence_history"] else 0.0
    return latest_conf >= target and t["contradiction_rate"] <= 0.3

failing_topics = [t for t in run["topics"] if not topic_passes(t)]
```

If `failing_topics` is empty: proceed to Stage 6 (classify).

For diagnostic display and the low-confidence note marker, also compute a "worst-case confidence" proxy across the run:

```python
worst_confidence = min(
    (t["confidence_history"][-1] if t["confidence_history"] else 0.0
     for t in run["topics"]),
    default=0.0,
)
```

This is the value used downstream as `OVERALL_CONFIDENCE` in Stage 5c's user-decision payload and 5d's `final_confidence_score`. There is no single "run target" because depths are per-topic, but the worst-topic confidence is the meaningful number to surface in user prompts and frontmatter callouts.

### 5b. Auto-replan (if eligible)

If `failing_topics` is non-empty AND `replan_count < 2`, run an auto-replan cycle:

1. For each failing topic, construct a replan hint:
   - If the topic has a stored `replan_hint` from a hop-planner `decision: "replan"`: use it directly.
   - Otherwise: synthesize a hint pointing at the gap (e.g., `{"issue": "thin sources", "suggested_pattern": "entity_expansion", "suggested_query_focus": "official agency data"}`). Persist via `set_replan_hint(topic, synthesized_hint)`.
2. **Re-admit each failing topic into the hop loop.** A topic that exhausted its initial budget has `current_hop == max_hops`, so Stage 4's admission filter (`current_hop < max_hops`) would otherwise skip it. To enable another hop without rewinding completed work, call `bump_max_hops(topic, increment=1)`. This gives the topic exactly one additional hop slot.
3. Call `mark_topic_status(topic, "active")` to re-admit.
4. Call `increment_replan(STATE_DIR)`.
5. Return to Stage 4 (the hop loop runs one more pass; only re-admitted topics dispatch search/fetch/summarize/hop-planner). Stage 4a's search-agent reads `topic.replan_hint` to bias the next query toward the suggested pattern/focus.

```bash
python -c "
import sys
sys.path.insert(0, 'SCRIPTS')
from state import load_run, set_replan_hint, bump_max_hops, mark_topic_status, increment_replan
from pathlib import Path
state_dir = Path('STATE_DIR')
run = load_run(state_dir)
for t in FAILING_TOPICS:
    if t['replan_hint'] is None:
        set_replan_hint(state_dir, t['topic'], SYNTHESIZED_HINT)
    bump_max_hops(state_dir, t['topic'], increment=1)
    mark_topic_status(state_dir, t['topic'], 'active')
increment_replan(state_dir)
"
```

### 5c. User prompt (after 2 auto-replan failures)

If `replan_count == 2`, present the diagnostic:

```
⚠ Quality gate triggered after {replan_count} auto-replan attempts.

Topic-by-topic results:
{for each topic:}
  - {topic.topic}: confidence {topic.confidence_history[-1]:.2f}, contradictions {topic.contradiction_rate:.0%}
{end}

Weakest topics:
{for each weak topic:}
  - "{topic}": {gap description}
{end}

Options:
  - replan: try one more cycle with focused hints (1 extension max)
  - continue: write notes anyway, with low-confidence flags
  - abandon: stop here, preserve search/fetch results for inspection
```

Wait for the user's response.

Record the decision:

```bash
python -c "
import sys
sys.path.insert(0, 'SCRIPTS')
from state import record_user_decision
from pathlib import Path
record_user_decision(Path('STATE_DIR'), decision='DECISION_VALUE', confidence=OVERALL_CONFIDENCE)
"
```

Branch by decision:

- **`replan`**: apply the same re-admission recipe as Stage 5b (so the topic actually makes it back into the hop loop):
  - For each failing topic, if `replan_hint` is None, synthesize one (the user may also supply a manual hint via free-text input — capture it as the `issue` field).
  - Call `bump_max_hops(topic, increment=1)` so `current_hop < max_hops` again.
  - Call `mark_topic_status(topic, "active")`.
  - Call `increment_replan(STATE_DIR)` once more (reaching 3).

  Return to Stage 4. After this attempt, no more replans — if it fails again, present continue/abandon only.
- **`continue`**: mark the run with `low_confidence = true` (see 5d). Proceed to Stage 6. The write stage adds body callouts to all written notes.
- **`abandon`**: set `abandoned_at_gate: true` in the run dict, save, then call `abandon_run(STATE_DIR)` (which already exists in state.py and archives via `_archive_run`). Print the archived path so the user can inspect:

  ```bash
  python -c "
  import sys
  sys.path.insert(0, 'SCRIPTS')
  from state import load_run, save_state, abandon_run
  from pathlib import Path
  state_dir = Path('STATE_DIR')
  run = load_run(state_dir)
  if run is not None:
      run['abandoned_at_gate'] = True
      save_state(state_dir, run)
  abandon_run(state_dir)
  "
  ```

  The archived files land under `STATE_DIR/history/{run_id}/` (the existing `_archive_run` destination). Print that path to the user.

### 5d. Save low-confidence flag

If decision was `continue`:

```bash
python -c "
import sys
sys.path.insert(0, 'SCRIPTS')
from state import load_run, save_state
from pathlib import Path
run = load_run(Path('STATE_DIR'))
run['low_confidence'] = True
run['final_confidence_score'] = OVERALL_CONFIDENCE
save_state(Path('STATE_DIR'), run)
"
```
```

**Step 2: Commit**

```bash
git commit -am "feat(skill): Stage 5 quality gate with auto-replan + user prompt"
```

### Task 8.6 — Stage 6 (Classify), Stage 7 (Write)

**Step 1: Update Stage 6 to consume the new summaries shape**

The classify stage is mostly unchanged but now reads ALL per-hop summaries (not just summaries.json). Aggregate before passing to classify:

```bash
# Aggregate summaries across all hops for each topic
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from pathlib import Path
state_dir = Path('STATE_DIR')
all_summaries = []
for hop_file in sorted(state_dir.glob('summaries_hop*.json')):
    data = json.loads(hop_file.read_text())
    all_summaries.extend(data.get('items', []))
combined = {'topic': '{project_name}', 'items': all_summaries}
(state_dir / 'summaries.json').write_text(json.dumps(combined, indent=2))
"
```

Then dispatch classify as before but expecting the extended output (with `contradictions_detected`).

**Step 2: Update Stage 7 — uncertainty + contradiction callouts in writes**

Modify the write subsection (8b.v "Write the note content"):

```markdown
**Body callouts (NEW for v3):**

If `run.low_confidence == true`, prepend this callout to the note body BEFORE the H1:

```
> ⚠ **Research confidence: {run.final_confidence_score:.2f}**. Several topics in this run did not reach the standard confidence target. Verify claims before citing.
```

If any contradiction in `classification.contradictions_detected` references a source URL that overlaps with this note's `source_urls`, prepend (or merge with the prior callout) a contradiction callout:

```
> ⚠ **Source contradictions noted.** Two or more sources disagree on aspects of this topic. See `## Sources` section for details.
```

Then in the `## Sources` section, mark contradicting sources inline:

```
## Sources

- https://source-a/ (T1) — claims X
- https://source-b/ (T2) — claims Y (contradicts source-a on Z)
```

Match contradictions by URL: any source URL that appears in a `contradictions_detected[].source_a` or `source_b` gets the contradiction annotation in the Sources list.
```

Also update the frontmatter block in 8b.v:

```yaml
---
title: "{note title}"
tags: [{tags}]
source: [{source URLs}]
created: {today}
write_model: {sonnet or opus}
research_run: {RUN_ID}
confidence: {topic.confidence_history[-1] or 1.0 if single-hop}
contradictions_noted: {true if this note's sources appear in contradictions_detected else false}
primary_sources: {count of sources where is_primary == true}
hop_genealogy: [{list of pattern(from) strings for multi-hop runs, omitted for single-hop}]
---
```

**Step 3: Commit**

```bash
git commit -am "feat(skill): Stages 6-7 with contradiction callouts and confidence frontmatter"
```

### Task 8.7 — Stage 10: Telemetry + hop genealogy summary

**Important sequencing:** `complete_run()` archives the state file (moves it under `history/{run_id}/`), so any `load_run()` call AFTER `complete_run()` returns `None`. Stage 10's telemetry, hop genealogy print, and case-record write must all use the dict returned BY `complete_run()` — not call `load_run()` after the fact.

Task 2.9 modified `complete_run()` to return the final run dict (with `completed_at`) before archiving, exactly so Stage 10 can use it.

**Step 1: Update Stage 10**

Replace the "Stage 10a (Complete the run)" and "Stage 10b (Print summary)" subsections so the orchestrator captures `complete_run`'s return value first, then uses it for telemetry, then writes the case record from the same dict:

```markdown
### Stage 10a. Complete the run (capture final state)

```bash
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from state import complete_run
from pathlib import Path
final = complete_run(Path('STATE_DIR'))
print(json.dumps(final))
"
```

Parse the printed JSON. This is the FINAL run dict (with `completed_at` set). The state file has been moved to history at this point — do NOT call `load_run` again.

### Stage 10b. Print summary

Using the `final` dict from 10a:

Then format and print:

```
Research complete: {project}

Created ({count} notes):
{for each:}
  - {path} (confidence {confidence})
{end}

Updated:
{for each updated note/MOC:}
  - {path}
{end}

Hop genealogy:
{for each topic:}
  Topic: {topic} ({hop_count} hops, confidence {confidence}{", " + status if status != "complete"})
  {for each hop in genealogy:}
    Hop {n} ({pattern or "initial"}): {sources_kept} sources kept
  {end}
{end}

Model usage:
  Haiku:   {haiku.calls} calls,  {haiku.in_tokens:,} in / {haiku.out_tokens:,} out
  Sonnet:  {sonnet.calls} calls, {sonnet.in_tokens:,} in / {sonnet.out_tokens:,} out
  Opus:    {opus.calls} call(s), {opus.in_tokens:,} in / {opus.out_tokens:,} out
  Ollama: {ollama.calls} calls (local — no token cost)

Estimated cost: ${estimated_cost:.2f}

{if low_confidence:}
⚠ Low confidence run (score {final_confidence_score}). Notes marked with low-confidence callouts.
{end}

{if threads approved:}
Threads queued for follow-up:
  - {topic} (priority: {priority})
  Run /research again to execute these.
{end}

Tier: {TIER} | Sources fetched: {total} | Notes written: {count} | Replans: {replan_count}
```

Cost estimation (rough):
- Haiku: $0.25/M input + $1.25/M output
- Sonnet: $3/M input + $15/M output
- Opus: $15/M input + $75/M output

Sum across models for the estimate.

### Stage 10c. Write case record

Using the same `final` dict from 10a (do NOT re-read state — it's archived already):

```bash
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from state import write_case_record
from pathlib import Path
cases_dir = Path('CASES_DIR')

# 'final' was captured from complete_run() in stage 10a; pass it via stdin or a temp file
import json as _json
final = _json.loads(open('FINAL_JSON_TEMP_FILE').read())

case = {
    'case_id': final['run_id'],
    'version': 1,
    'query': 'PROJECT_NAME',
    'domain_tags': DERIVED_TAGS,
    'strategy_used': final.get('strategy', 'unified'),
    'depths_used': {d: sum(1 for t in final['topics'] if t.get('depth') == d)
                    for d in ['quick','standard','deep','exhaustive']},
    'hops_executed': sum(len(t.get('hop_genealogy', [])) for t in final['topics']),
    'confidence_per_topic': {t['topic']: (t['confidence_history'][-1] if t.get('confidence_history') else None)
                             for t in final['topics']},
    'contradiction_rate': max((t.get('contradiction_rate', 0.0) for t in final['topics']), default=0.0),
    'patterns_that_worked': PATTERNS_WORKED,
    'patterns_that_failed': PATTERNS_FAILED,
    'outcomes': {
        'sources_processed': SOURCES_COUNT,
        'notes_created': CREATED_COUNT,
        'notes_updated': UPDATED_COUNT,
        'user_decisions': final.get('user_decisions', []),
    },
}
write_case_record(cases_dir, case)
"
```

The orchestrator writes `final` to a temp JSON file between 10a and 10c (typical pattern: write the captured JSON to `STATE_DIR/../tmp/final_run.json` for the duration of 10b/10c, then delete). DERIVED_TAGS comes from the most common tags across written notes. PATTERNS_WORKED / PATTERNS_FAILED come from per-hop telemetry (patterns that produced novel notes vs. dead ends).
```

**Step 2: Commit**

```bash
git commit -am "feat(skill): Stage 10 telemetry + hop genealogy summary + case record"
```

### Task 8.8 — Renumber and clean up

**Step 1: Verify all stage numbers are correct**

Read the full SKILL.md and confirm:
- Stage 0: Load Config + Detect Tier
- Stage 1: Active Run Check
- Stage 2: Triage
- Stage 3: Resolve
- Stage 4: Hop Loop
- Stage 5: Quality Gate
- Stage 6: Classify
- Stage 7: Write Notes
- Stage 8: Wikilink Scan
- Stage 9: Discover Threads
- Stage 10: Complete

If wikilink scan was previously Stage 8d, promote it to Stage 8.

**Step 2: Update state.update_stage() calls throughout**

The state stage names should match: `triage`, `resolve`, `hop_loop`, `quality_gate`, `classify`, `write`, `wikilink_scan`, `discover`, `complete`.

**Step 3: Run a syntactic check**

Make sure the SKILL.md still parses as a valid plugin skill (frontmatter valid YAML, body well-formed Markdown).

```bash
python -c "
import yaml
content = open('skills/research/SKILL.md').read()
parts = content.split('---', 2)
fm = yaml.safe_load(parts[1])
assert fm['name'] == 'research'
print('OK')
"
```

**Step 4: Commit**

```bash
git commit -am "chore(skill): renumber stages and verify structure"
```

---

## Phase 9 — CSS snippet + research-setup integration

### Task 9.1 — Create the CSS snippet

**Files:**
- Create: `assets/research-metadata-hide.css`

**Step 1: Write the snippet**

```css
/* research-metadata-hide.css
 *
 * Hides diagnostic frontmatter fields written by research-workflow v3
 * in Obsidian's Properties panel. Fields remain in the file and stay
 * fully searchable and indexable.
 *
 * Install: copy this file to your vault's .obsidian/snippets/ directory
 * and enable it in Obsidian → Settings → Appearance → CSS snippets.
 */

.metadata-property[data-property-key="hop_genealogy"],
.metadata-property[data-property-key="research_run"],
.metadata-property[data-property-key="write_model"] {
    display: none;
}
```

**Step 2: Commit**

```bash
git add assets/research-metadata-hide.css
git commit -m "feat(assets): CSS snippet to hide diagnostic frontmatter fields"
```

### Task 9.2 — Offer the snippet during research-setup

**Files:**
- Modify: `skills/research-setup/SKILL.md`

**Step 1: Read the current setup wizard**

Identify the section where the wizard finalizes setup (writes config, builds index).

**Step 2: Add an optional snippet-installation step**

After the index-build step, add:

```markdown
### Step N: Optional — install metadata-hide CSS snippet

Ask the user:

```
Want to hide the diagnostic frontmatter fields (hop_genealogy, research_run, write_model)
in Obsidian's Properties panel? They'll still be searchable, just not displayed.

Install CSS snippet? [yes / no]
```

If `yes`:

```bash
mkdir -p "{VAULT}/.obsidian/snippets"
cp "{REPO}/assets/research-metadata-hide.css" "{VAULT}/.obsidian/snippets/research-metadata-hide.css"
```

Then tell the user:

```
Snippet copied. Enable it in Obsidian → Settings → Appearance → CSS snippets → toggle "research-metadata-hide".
```

If `no`, skip silently.
```

**Step 3: Commit**

```bash
git add skills/research-setup/SKILL.md
git commit -m "feat(research-setup): offer to install metadata-hide CSS snippet"
```

---

## Phase 10 — Integration test

### Task 10.1 — Create fixture directory

**Files:**
- Create: `tests/fixtures/research_integration/` (empty dir + .gitkeep)

```bash
mkdir -p tests/fixtures/research_integration
touch tests/fixtures/research_integration/.gitkeep
```

### Task 10.2 — Build minimal fixtures

**Files:**
- Create: `tests/fixtures/research_integration/topic_resolver_response.json`
- Create: `tests/fixtures/research_integration/search_hop1_topic0.json`
- Create: `tests/fixtures/research_integration/jina_fetch_results.json`
- Create: `tests/fixtures/research_integration/summaries_hop1.json`
- Create: `tests/fixtures/research_integration/hop_planner_topic0_hop1.json`
- Create: `tests/fixtures/research_integration/classify_response.json`

Each fixture is a small JSON file matching the agent contract for that step. Use a minimal single-topic case with `depth=quick` (so hop loop runs once and stops).

Example `topic_resolver_response.json`:

```json
{
  "project": "Test research",
  "strategy": "planning_only",
  "shared_context_files": [],
  "topics": [
    {
      "topic": "Test topic about Flock Safety",
      "mode": "web_research",
      "depth": "quick",
      "existing_urls": [],
      "related_vault_notes": []
    }
  ],
  "local_sources": [],
  "thread_pulls": [],
  "execution_order": "parallel",
  "estimated_usage": {
    "search_agents": 1,
    "summarize_calls": 5,
    "classify_agents": 1,
    "write_messages": "1 Sonnet",
    "local_extractions": 0,
    "total_claude_messages": "~5"
  }
}
```

Create similarly-shaped fixtures for the other files. Keep them minimal — just enough to exercise the orchestrator's parse/dispatch paths.

**Commit each fixture as a single commit:**

```bash
git add tests/fixtures/research_integration/
git commit -m "test: add fixture data for research pipeline integration test"
```

### Task 10.3 — Write the state-mechanics test

Honest naming. The skill is invoked by Claude Code's slash-command machinery, which is not a Python-executable harness. Without a fake Claude-Code runtime, we can't drive `skills/research/SKILL.md` from a pytest suite. So this test exercises the **Python state machinery** that the SKILL.md depends on — `state.py`, `confidence.py`, the JSON parsing helpers — using the fixture responses as if a real run had produced them.

End-to-end orchestrator testing happens via manual `/research` smoke runs (covered in Phase 11), not pytest. That's documented; the fixtures are still useful (they pin the JSON contract per agent).

**Files:**
- Create: `tests/test_research_state_mechanics.py`

```python
"""State-mechanics test for the multi-hop research pipeline.

This is NOT a full orchestrator integration test — the orchestrator (SKILL.md)
runs inside Claude Code's slash-command machinery, which has no Python harness.
Instead, this test drives the Python state helpers (state.py, confidence.py)
through the same sequence the orchestrator would, using fixture JSON for the
agent responses to validate the JSON contracts.
"""
import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "research_integration"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


def test_fixtures_parse_into_expected_shapes():
    """Each agent fixture parses and has the keys the orchestrator depends on."""
    resolver = load_fixture("topic_resolver_response.json")
    assert resolver["strategy"] in {"planning_only", "intent_planning", "unified"}
    assert all(t["depth"] in {"quick", "standard", "deep", "exhaustive"}
               for t in resolver["topics"])

    search = load_fixture("search_hop1_topic0.json")
    for url in search["selected_urls"]:
        assert url["tier"] in {"T1", "T2", "T3", "T4"}
        assert 0.0 <= url["credibility_score"] <= 1.0
        assert isinstance(url["is_primary"], bool)

    planner = load_fixture("hop_planner_topic0_hop1.json")
    assert planner["decision"] in {"continue", "stop", "replan"}

    classify = load_fixture("classify_response.json")
    assert "contradictions_detected" in classify


def test_quick_depth_run_via_state_helpers(tmp_path):
    """Drives state.py the way Stage 4 would for a quick-depth single-topic run."""
    from state import (
        create_run, init_topic, save_state, record_hop, append_confidence,
        mark_topic_status, load_run,
    )
    from confidence import compute_confidence

    state_dir = tmp_path / "state"
    state_dir.mkdir()

    run = create_run(state_dir, run_id="test-quick-run", tier="full")
    topic = init_topic("Test topic", mode="web_research", depth="quick")
    run["topics"] = [topic]
    save_state(state_dir, run)

    # Compute confidence from a fixture-like source set (mid-quality)
    sources = [
        {"tier": "T1", "is_primary": True},
        {"tier": "T2", "is_primary": False},
        {"tier": "T2", "is_primary": False},
    ]
    score = compute_confidence(sources, depth="quick")
    assert score > 0.0

    # Record the hop with that score, mark complete
    hop_data = {
        "hop": 1, "pattern": None, "queries": ["q"],
        "sources_found": 3, "sources_kept": 3,
        "ended_at": "2026-05-26T15:00:00Z",
    }
    record_hop(state_dir, topic_name="Test topic", hop_data=hop_data)
    append_confidence(state_dir, topic_name="Test topic", score=score)
    mark_topic_status(state_dir, topic_name="Test topic", status="complete")

    final = load_run(state_dir)
    assert final["topics"][0]["status"] == "complete"
    assert final["topics"][0]["current_hop"] == 1
    assert final["topics"][0]["confidence_history"] == [score]
    assert len(final["topics"][0]["hop_genealogy"]) == 1


def test_replan_increments_count(tmp_path):
    from state import create_run, init_topic, save_state, increment_replan, load_run

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    run = create_run(state_dir, run_id="test-replan-run", tier="full")
    run["topics"] = [init_topic("T", mode="web_research", depth="standard")]
    save_state(state_dir, run)

    increment_replan(state_dir)
    increment_replan(state_dir)

    final = load_run(state_dir)
    assert final["replan_count"] == 2


def test_low_confidence_marks_run(tmp_path):
    from state import create_run, save_state, record_user_decision, load_run

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    run = create_run(state_dir, run_id="test-lowconf-run", tier="full")
    save_state(state_dir, run)

    record_user_decision(state_dir, decision="continue_anyway", confidence=0.52)
    run = load_run(state_dir)
    run["low_confidence"] = True
    run["final_confidence_score"] = 0.52
    save_state(state_dir, run)

    final = load_run(state_dir)
    assert final["low_confidence"] is True
    assert final["final_confidence_score"] == 0.52
    assert final["user_decisions"][0]["decision"] == "continue_anyway"
```

**Step 1: Run the test**

```bash
pytest tests/test_research_state_mechanics.py -v
```

Expected: PASS.

**Step 2: Run full suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

**Step 3: Commit**

```bash
git add tests/test_research_state_mechanics.py
git commit -m "test: state-mechanics test for multi-hop pipeline (with fixture-shape pinning)"
```

---

## Phase 11 — Final polish

### Task 11.1 — Update plugin.json to v3.0.0

**Files:**
- Modify: `.claude-plugin/plugin.json`

**Step 1: Bump version**

```diff
- "version": "2.0.0",
+ "version": "3.0.0",
```

(Adjust path if the manifest is elsewhere; recent commits mention `4b3200e Move plugin manifest to .claude-plugin/`.)

**Step 2: Commit**

```bash
git add .claude-plugin/plugin.json
git commit -m "chore: bump version to 3.0.0"
```

### Task 11.2 — Update MANIFEST.md

**Files:**
- Modify: `MANIFEST.md`

**Step 1: Reflect the new architecture**

Update the Structure section to include:
- `agents/hop-planner.md` (new)
- `scripts/confidence.py` (new)
- `scripts/fetch_playwright.py` (new)
- `assets/research-metadata-hide.css` (new)

Remove:
- `scripts/config.py` (deleted)
- `scripts/utils.py` (deleted)

Update the Stack line to mention Playwright as optional full-tier dependency.

Update Key Relationships to reflect:
- `confidence.py` is consumed by `hop-planner` agent and `state.py`
- `hop-planner` runs between hops in the loop
- v3 schema in `state.py` with hop genealogy

**Step 2: Commit**

```bash
git add MANIFEST.md
git commit -m "docs(MANIFEST): reflect v3 architecture"
```

### Task 11.3 — Update CLAUDE.md description of architecture

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update the architecture section**

Replace:

```
A Claude Code plugin for deep research into Obsidian vaults. The `/research` skill is the main entry point — it orchestrates an 8-stage pipeline: resolve, search, fetch, media, summarize, classify, write, discover. Three modes: single topic, batch, and thread-pull.
```

with:

```
A Claude Code plugin for deep research into Obsidian vaults. The `/research` skill is the main entry point — it orchestrates a multi-hop pipeline with depth profiles, confidence-based replanning, and source credibility tiering. Stages: triage, resolve, hop loop (search/fetch/media/summarize/hop-planner per hop), quality gate, classify, write, wikilink scan, discover threads, complete. Three modes: single topic, batch, and thread-pull. Three planning strategies: planning_only (clear queries), intent_planning (ambiguous), unified (batch / full plan presentation).
```

Update the Architecture bullet list to mention `hop-planner` and `confidence.py`.

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(CLAUDE.md): reflect v3 architecture"
```

### Task 11.4 — Update MEMORY.md hint

**Files:**
- Modify: `C:\Users\tim\.claude\projects\C--Users-tim-OneDrive-Documents-Projects-research-workflow\memory\MEMORY.md`

(This file is outside the repo. Update it only after the PR is merged — note in the PR description that MEMORY.md should be updated post-merge.)

**Step 1: Skip during plan execution; flag for the PR description.**

### Task 11.5 — Full test suite + lint check

**Step 1: Run the full suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

**Step 2: Manual smoke check**

If possible, run `/research-setup` in a test vault and verify the wizard runs without errors. Then run `/research "test topic"` with a minimal scope and verify the pipeline initializes correctly.

**Step 3: No commit needed if everything passes.**

### Task 11.6 — Push the branch

```bash
git push -u origin feat/v3-superclaude-methodology
```

---

## Execution notes for the implementer

- **Bite-sized commits.** Every task above produces one or more commits. Push at the end of each phase. Don't batch — small commits make review feasible.
- **TDD discipline.** Where tests are defined in a task, write them first, watch them fail, then implement. Skip the test-first dance for documentation-only tasks (agent prompts, SKILL.md prose).
- **Don't gold-plate.** When you encounter an existing function that could be cleaner, leave it. Refactor scope is bounded by this plan.
- **Reference the design.** When unsure about a design call (e.g., why this formula? why this schema field?), consult [the design doc](2026-05-26-superclaude-methodology-rework-design.md) — it has the rationale.
- **Tests stay offline.** No API keys, no network calls, no external services. Every test uses pre-recorded fixtures or pure Python helpers.

---

## What gets shipped in v3.0.0

- 11 phases of bite-sized tasks
- ~250+ lines of new state.py logic
- ~200 lines of new confidence.py
- New `agents/hop-planner.md` (~200 lines)
- New `scripts/fetch_playwright.py` (~30 lines)
- SKILL.md rewrite (~1000+ lines)
- ~150 new test cases
- Plugin version 2.0.0 → 3.0.0

## What's deferred to v3.1.0 (Stage B)

- Pattern learning / case-based reasoning (read path)
- Resolver consults `.research-workflow/cases/` at triage
- Adaptive query formulations from learned patterns
- Evolutionary scoring of patterns over time

Stage B has its own design doc and plan, landing as a follow-up release.
