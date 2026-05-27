# v3.1.0 Case-Based Pattern Learning Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the read path for case-based pattern learning so the research pipeline accumulates observations across runs, promotes them to durable rules under user approval, and surfaces them to subagents at run time — without editing any agent definition files.

**Architecture:** Three pieces of new persistent state (`cases/{run_id}.json` extended, `accumulator.json` new, `learned_patterns.md` new) plus a new analyzer that runs at Stage 10b. Heuristic Python aggregation does the bulk; a Haiku subagent handles semantic comparison only. Orchestrator injects filtered learned patterns into subagent user prompts at Stage 4a / 4e / 6. v3.1.0 is purely additive — empty state means the pipeline behaves identically to v3.0.0.

**Tech Stack:** Python 3.10+ (pure-Python helpers, JSON + markdown I/O, `_atomic_write` pattern), pytest + pytest-mock (offline tests, no API keys), Claude Code Haiku subagent (semantic compare only, via Task tool from orchestrator), `scripts/state.py` v3 schema (already in master).

**Workflow:**
- Per-phase: implementer → spec reviewer → code quality reviewer (subagent-driven-development)
- After plan is committed: codex-plan-review (capped at 4-5 rounds, Tim's preference)
- After impl complete: codex-impl-review (capped at 4-5 rounds)
- Atomic state discipline (load → mutate → save) — matches v3.0.0's `apply_hop_decision` pattern
- No anthropic SDK, no `claude -p` — all AI via Claude Code subagents or Ollama
- TDD per task: failing test → verify failure → minimal impl → verify pass → commit

**Design reference:** [2026-05-27-v3-1-case-learning-design.md](2026-05-27-v3-1-case-learning-design.md)

**Branch:** `feat/v3-1-case-learning` (already created, design doc committed at `0cc1ebe`)

**Test runner:** `pytest tests/ -v` from repo root. All offline.

---

## Phase Overview

| Phase | Component | Tasks |
|-------|-----------|-------|
| 1 | State extensions (`applied_patterns`, atomic writes for new files, lock helper) | 5 |
| 2 | Accumulator module | 6 |
| 3 | `learned_patterns.md` parser/writer | 4 |
| 4 | Heuristic candidate detection | 5 |
| 5 | Score updates + demotion sweep | 4 |
| 6 | Case analyzer wiring + Haiku semantic-merge / contradiction wiring | 5 |
| 7 | Haiku semantic-compare subagent + contract test | 2 |
| 8 | Orchestrator extensions in SKILL.md (Stage 2d / 4a / 4e / 6 / 10d / 10e) | 5 |
| 9 | Multi-run trajectory integration test | 2 |
| 10 | Backward-compat + final verification | 3 |

41 tasks total. Each phase ends with a per-phase code review (subagent-driven). After all phases complete, codex-impl-review (capped 4-5 rounds) gates the PR.

---

## Phase 1: State Extensions

**Goal:** Extend `scripts/state.py` with the helpers v3.1.0 needs — `applied_patterns` tracking on the current run, atomic writes for `accumulator.json` and `learned_patterns.md`, and a concurrency lock around shared-state writes.

**Files touched:** `scripts/state.py`, `tests/test_state.py`.

---

### Task 1.1: Add `applied_patterns` field to run state schema

**Files:**
- Modify: `scripts/state.py` (the `create_run` function — this is the actual run-creation entry point in v3.0.0; there is no `init_run`)
- Test: `tests/test_state.py`

**Step 1: Write the failing test**

Add to `tests/test_state.py`:

```python
def test_create_run_has_empty_applied_patterns(tmp_path):
    """v3.1.0 runs initialize with an empty applied_patterns list."""
    from state import create_run, load_run
    run = create_run(tmp_path, run_id="test-v31-applied", tier="base")
    assert "applied_patterns" in run
    assert run["applied_patterns"] == []
    # Round-trip via load_run too
    persisted = load_run(tmp_path)
    assert persisted["applied_patterns"] == []
```

**Step 2: Run test to verify it fails**

```
pytest tests/test_state.py::test_create_run_has_empty_applied_patterns -v
```
Expected: FAIL with `KeyError: 'applied_patterns'` or `assert 'applied_patterns' in {...}`.

**Step 3: Add the field to `create_run`**

In `scripts/state.py`, find the `create_run()` function (look for `def create_run(state_dir: Path, run_id: str, tier: str) -> dict:` — around line 362 in the v3.0.0 codebase) and add `"applied_patterns": [],` to the run dict it builds. Place it near `"usage"` and the per-run telemetry fields for consistency. The function persists the dict via `_atomic_write` already; no additional save call needed.

**Step 4: Run test to verify pass**

```
pytest tests/test_state.py::test_create_run_has_empty_applied_patterns -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/state.py tests/test_state.py
git commit -m "feat(state): add applied_patterns field to create_run dict"
```

---

### Task 1.2: Helper to append `pattern_id` to current run's `applied_patterns`

**Files:**
- Modify: `scripts/state.py`
- Test: `tests/test_state.py`

**Step 1: Write the failing test**

```python
def test_record_applied_pattern_appends_unique(tmp_path):
    """record_applied_pattern adds a pattern_id; duplicates are no-ops."""
    from state import create_run, record_applied_pattern, load_run
    create_run(tmp_path, run_id="t", tier="base")
    record_applied_pattern(tmp_path, "civic-alpr-t1-dominance-3f7a")
    record_applied_pattern(tmp_path, "tech-entity-h2-9c2b")
    record_applied_pattern(tmp_path, "civic-alpr-t1-dominance-3f7a")  # dup
    run = load_run(tmp_path)
    assert run["applied_patterns"] == [
        "civic-alpr-t1-dominance-3f7a",
        "tech-entity-h2-9c2b",
    ]
```

**Step 2: Verify failure**

```
pytest tests/test_state.py::test_record_applied_pattern_appends_unique -v
```
Expected: FAIL (`ImportError` or `AttributeError`).

**Step 3: Implement `record_applied_pattern`**

In `scripts/state.py`:

```python
def record_applied_pattern(state_dir: Path, pattern_id: str) -> None:
    """Append a pattern_id to the current run's applied_patterns list.
    Idempotent: duplicate pattern_ids are not re-added. Used by the
    orchestrator at each subagent dispatch to record which learned patterns
    were injected into a prompt during the run.
    """
    run = load_run(state_dir)
    if run is None:
        return
    applied = run.setdefault("applied_patterns", [])
    if pattern_id not in applied:
        applied.append(pattern_id)
        _atomic_write(state_dir / CURRENT_RUN_FILE, run)
```

**Step 4: Verify pass**

```
pytest tests/test_state.py::test_record_applied_pattern_appends_unique -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/state.py tests/test_state.py
git commit -m "feat(state): add record_applied_pattern helper for run-level pattern tracking"
```

---

### Task 1.3: Atomic write helpers for accumulator + learned_patterns

**Files:**
- Modify: `scripts/state.py`
- Test: `tests/test_state.py`

The existing `_atomic_write()` in state.py is private and takes a Path + dict. We need a generalized version that works for any vault-level shared state file (accumulator.json, learned_patterns.md), accepts dict OR string content, and is publicly callable from `case_analyzer.py`.

**Step 1: Write the failing test**

```python
def test_write_shared_state_atomically_dict(tmp_path):
    """write_shared_state_atomically writes a dict as JSON via temp-rename."""
    from state import write_shared_state_atomically
    target = tmp_path / "accumulator.json"
    write_shared_state_atomically(target, {"version": 1, "entries": []})
    assert target.exists()
    import json
    data = json.loads(target.read_text())
    assert data == {"version": 1, "entries": []}

def test_write_shared_state_atomically_str(tmp_path):
    """write_shared_state_atomically writes a string verbatim."""
    from state import write_shared_state_atomically
    target = tmp_path / "learned_patterns.md"
    body = "---\nversion: 1\n---\n\n## civic / alpr\n"
    write_shared_state_atomically(target, body)
    assert target.read_text() == body

def test_write_shared_state_atomically_creates_parent(tmp_path):
    """write_shared_state_atomically creates parent dir if missing."""
    from state import write_shared_state_atomically
    target = tmp_path / "nested" / "deeper" / "file.json"
    write_shared_state_atomically(target, {"x": 1})
    assert target.exists()
```

**Step 2: Verify failure**

```
pytest tests/test_state.py::test_write_shared_state_atomically_dict tests/test_state.py::test_write_shared_state_atomically_str tests/test_state.py::test_write_shared_state_atomically_creates_parent -v
```
Expected: FAIL (function doesn't exist).

**Step 3: Implement `write_shared_state_atomically`**

In `scripts/state.py`:

```python
def write_shared_state_atomically(target: Path, content: dict | str) -> None:
    """Write content to target via temp-file-then-rename. Creates parent dir.

    Accepts dict (serialized as JSON with indent=2) or str (written verbatim).
    Reuses _atomic_write's discipline: no partial writes survive a crash.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, dict):
        body = json.dumps(content, indent=2)
    elif isinstance(content, str):
        body = content
    else:
        raise TypeError(f"content must be dict or str, got {type(content).__name__}")
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8", newline="\n")
    tmp.replace(target)
```

**Step 4: Verify pass**

```
pytest tests/test_state.py::test_write_shared_state_atomically_dict tests/test_state.py::test_write_shared_state_atomically_str tests/test_state.py::test_write_shared_state_atomically_creates_parent -v
```
Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git add scripts/state.py tests/test_state.py
git commit -m "feat(state): add write_shared_state_atomically for vault-level shared state files"
```

---

### Task 1.4: Lock acquisition helper around shared-state writes

**Files:**
- Modify: `scripts/state.py`
- Test: `tests/test_state.py`

**Step 1: Write the failing tests**

```python
def test_acquire_state_lock_succeeds_when_unheld(tmp_path):
    """acquire_state_lock returns a context manager that holds the lock."""
    from state import acquire_state_lock
    with acquire_state_lock(tmp_path, timeout_s=1):
        assert (tmp_path / ".lock").exists()
    assert not (tmp_path / ".lock").exists()

def test_acquire_state_lock_times_out_when_held(tmp_path):
    """acquire_state_lock raises TimeoutError when another process holds it."""
    from state import acquire_state_lock, LockTimeoutError
    import pytest
    # Simulate another holder: write a lock file with current PID + fresh timestamp
    import os
    from datetime import datetime, timezone
    (tmp_path / ".lock").write_text(f"{os.getpid() + 99999}\n{datetime.now(timezone.utc).isoformat()}\n")
    with pytest.raises(LockTimeoutError):
        with acquire_state_lock(tmp_path, timeout_s=0.5):
            pass

def test_acquire_state_lock_breaks_stale_lock(tmp_path):
    """Stale locks (timestamp >1hr old) are forcibly cleared."""
    from state import acquire_state_lock
    import os
    from datetime import datetime, timezone, timedelta
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    (tmp_path / ".lock").write_text(f"{os.getpid() + 99999}\n{stale_ts}\n")
    with acquire_state_lock(tmp_path, timeout_s=1):
        pass  # should succeed, lock was stale
```

**Step 2: Verify failure**

```
pytest tests/test_state.py -k acquire_state_lock -v
```
Expected: FAIL (function and exception type don't exist).

**Step 3: Implement the lock helper**

In `scripts/state.py`:

```python
class LockTimeoutError(Exception):
    """Raised when state lock can't be acquired within the timeout."""


@contextmanager
def acquire_state_lock(state_root: Path, timeout_s: float = 5.0,
                       stale_after_hours: int = 1):
    """Acquire an exclusive lock for shared-state writes (accumulator,
    learned_patterns). Returns a context manager.

    Lock file at {state_root}/.lock contains: {pid}\n{iso_timestamp}\n

    Stale locks (timestamp older than stale_after_hours) are forcibly cleared.
    Otherwise, waits up to timeout_s for the lock to free up.
    Raises LockTimeoutError on timeout.
    """
    import time
    state_root.mkdir(parents=True, exist_ok=True)
    lock_file = state_root / ".lock"
    deadline = time.monotonic() + timeout_s

    while True:
        # Check for stale lock
        if lock_file.exists():
            try:
                content = lock_file.read_text().strip().split("\n")
                if len(content) == 2:
                    _, ts_str = content
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    age = datetime.now(timezone.utc) - ts
                    if age > timedelta(hours=stale_after_hours):
                        lock_file.unlink()  # break stale lock
            except (ValueError, OSError):
                # malformed lock file — treat as stale
                try:
                    lock_file.unlink()
                except OSError:
                    pass

        # Try to acquire
        try:
            # Atomic create with O_EXCL semantics via exclusive write
            with open(lock_file, "x") as f:
                f.write(f"{os.getpid()}\n{datetime.now(timezone.utc).isoformat()}\n")
            try:
                yield
            finally:
                try:
                    lock_file.unlink()
                except OSError:
                    pass
            return
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise LockTimeoutError(
                    f"Could not acquire state lock at {lock_file} within "
                    f"{timeout_s}s — another /research run may be in progress."
                )
            time.sleep(0.1)
```

Add `from contextlib import contextmanager` and `import os` to the top imports if not already present.

**Step 4: Verify pass**

```
pytest tests/test_state.py -k acquire_state_lock -v
```
Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git add scripts/state.py tests/test_state.py
git commit -m "feat(state): add acquire_state_lock helper for shared-state write safety"
```

---

### Task 1.5: Phase 1 review

Dispatch the spec reviewer and code quality reviewer subagents to review Phase 1's three commits (1.1 / 1.2 / 1.3 / 1.4).

**Spec review prompt:**
"Review state.py changes in the last 4 commits on this branch against design doc Section 6.3 (State extensions). Confirm: `applied_patterns` field added to run schema; `record_applied_pattern` helper present and idempotent; `write_shared_state_atomically` accepts dict or str; lock helper with stale detection. Flag any spec gaps."

**Code quality reviewer prompt:**
"Review state.py changes in the last 4 commits for code quality. Check: error handling around file I/O, lock acquisition race conditions on Windows, thread safety, naming consistency with rest of state.py, docstring quality. Flag concerns."

Address findings via new commits before moving to Phase 2.

---

## Phase 2: Accumulator Module

**Goal:** Implement the JSON accumulator that holds candidate patterns observed across runs. Reader, writer, sessions_seen / sessions_since_last_seen increment logic, rejected-set persistence, demotion counter.

**Files touched:** `scripts/accumulator.py` (new), `tests/test_accumulator.py` (new), `tests/fixtures/case_learning/` (new dir).

---

### Task 2.1: Accumulator schema + load/save round-trip

**Files:**
- Create: `scripts/accumulator.py`
- Test: `tests/test_accumulator.py`

**Step 1: Write the failing test**

Create `tests/test_accumulator.py`:

```python
import json
from pathlib import Path
from accumulator import (
    load_accumulator,
    save_accumulator,
    Accumulator,
    AccumulatorEntry,
    ACCUMULATOR_SCHEMA_VERSION,
)


def test_load_missing_returns_empty(tmp_path):
    """Missing accumulator.json returns an empty Accumulator with no warnings."""
    acc, warnings = load_accumulator(tmp_path / "missing.json")
    assert acc.version == ACCUMULATOR_SCHEMA_VERSION
    assert acc.entries == []
    assert warnings == []


def test_save_then_load_roundtrip(tmp_path):
    """Round-trip preserves all fields; no warnings on clean load."""
    target = tmp_path / "accumulator.json"
    entry = AccumulatorEntry(
        pattern_id="civic-alpr-t1-dominance-3f7a",
        name="T1 sources dominate",
        category="source-tier-bias",
        target_stage="search",
        domain_tags=["civic", "alpr"],
        sessions_seen=3,
        sessions_since_last_seen=0,
        status="hold",
        raised_bar=False,
        promotion_pending=False,
        demotion_count=0,
        evidence=[{"case_id": "c1", "signal": "T1=8/12"}],
        proposed_promotion_body="T1 sources dominate...",
        created_at="2026-05-22T10:14:00Z",
        last_updated_at="2026-05-27T15:30:00Z",
    )
    acc = Accumulator(version=ACCUMULATOR_SCHEMA_VERSION, entries=[entry])
    save_accumulator(target, acc)
    loaded, warnings = load_accumulator(target)
    assert loaded == acc
    assert warnings == []


def test_save_writes_atomic_via_state(tmp_path):
    """save_accumulator uses write_shared_state_atomically."""
    target = tmp_path / "accumulator.json"
    acc = Accumulator(version=ACCUMULATOR_SCHEMA_VERSION, entries=[])
    save_accumulator(target, acc)
    assert target.exists()
    # No leftover .tmp file
    assert not target.with_suffix(".json.tmp").exists()


def test_load_corrupt_returns_empty_with_warning(tmp_path):
    """Malformed JSON returns empty Accumulator + corrupted warning."""
    target = tmp_path / "accumulator.json"
    target.write_text("{not valid json")
    acc, warnings = load_accumulator(target)
    assert acc.entries == []
    assert len(warnings) == 1
    assert "accumulator_corrupted" in warnings[0]


def test_load_version_mismatch_returns_empty_with_warning(tmp_path):
    """Schema version mismatch returns empty Accumulator + schema_mismatch warning."""
    import json as _j
    target = tmp_path / "accumulator.json"
    target.write_text(_j.dumps({"version": 99, "entries": []}))
    acc, warnings = load_accumulator(target)
    assert acc.entries == []
    assert len(warnings) == 1
    assert "accumulator_schema_mismatch" in warnings[0]
```

**Step 2: Verify failure**

```
pytest tests/test_accumulator.py -v
```
Expected: FAIL (module doesn't exist).

**Step 3: Implement `accumulator.py`**

Create `scripts/accumulator.py`:

```python
"""Accumulator — JSON store of candidate patterns observed across runs.

Loaded by the case analyzer at end-of-run. Promoted entries move to
learned_patterns.md; rejected entries remain in the accumulator with
status="rejected" so they are never re-proposed.

See docs/plans/2026-05-27-v3-1-case-learning-design.md Section 5.2 for schema.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from state import write_shared_state_atomically


ACCUMULATOR_SCHEMA_VERSION = 1


@dataclass
class AccumulatorEntry:
    pattern_id: str
    name: str
    category: str
    target_stage: str
    domain_tags: list[str]
    sessions_seen: int
    sessions_since_last_seen: int
    status: str  # "hold" | "rejected" | "promotion_pending"
    raised_bar: bool
    promotion_pending: bool
    demotion_count: int
    evidence: list[dict]
    proposed_promotion_body: str
    created_at: str
    last_updated_at: str


@dataclass
class Accumulator:
    version: int = ACCUMULATOR_SCHEMA_VERSION
    entries: list[AccumulatorEntry] = field(default_factory=list)


class AccumulatorLoadError(Exception):
    """Raised by load_accumulator_strict when the file is corrupt or
    schema-incompatible. Callers that want graceful degradation should use
    load_accumulator (which catches and returns an empty Accumulator + warning)."""


def load_accumulator(path: Path) -> tuple[Accumulator, list[str]]:
    """Graceful load: returns (Accumulator, warnings). Never raises.

    On parse error or schema-version mismatch: logs to warnings, returns an
    empty Accumulator. The analyzer propagates these warnings into
    AnalyzerResult.warnings; the analyzer ALSO refuses to write back to a
    file that loaded with warnings (see analyze()'s persist step). This keeps
    user-recoverable corrupt state on disk so the user can inspect or
    manually delete it to reset.
    """
    warnings: list[str] = []
    if not path.exists():
        return Accumulator(), warnings
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError) as e:
        warnings.append(f"accumulator_corrupted: {path} could not be read or parsed ({e})")
        return Accumulator(), warnings
    file_version = data.get("version")
    if file_version != ACCUMULATOR_SCHEMA_VERSION:
        warnings.append(
            f"accumulator_schema_mismatch: file is version {file_version!r}, "
            f"code expects {ACCUMULATOR_SCHEMA_VERSION}. Treating as empty."
        )
        return Accumulator(), warnings
    try:
        entries = [AccumulatorEntry(**e) for e in data.get("entries", [])]
    except TypeError as e:
        # Schema-shape mismatch (e.g., entry missing required field after a
        # forward-incompatible edit). Treat the whole file as corrupt.
        warnings.append(f"accumulator_corrupted: entry shape unexpected ({e})")
        return Accumulator(), warnings
    return Accumulator(version=file_version, entries=entries), warnings


def save_accumulator(path: Path, acc: Accumulator) -> None:
    """Save accumulator to JSON file via atomic write."""
    payload = {
        "version": acc.version,
        "entries": [asdict(e) for e in acc.entries],
    }
    write_shared_state_atomically(path, payload)
```

**Step 4: Verify pass**

```
pytest tests/test_accumulator.py -v
```
Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git add scripts/accumulator.py tests/test_accumulator.py
git commit -m "feat(accumulator): schema + load/save round-trip"
```

---

### Task 2.2: sessions_seen / sessions_since_last_seen increment logic

**Files:**
- Modify: `scripts/accumulator.py`
- Test: `tests/test_accumulator.py`

**Step 1: Write the failing tests**

Add to `tests/test_accumulator.py`:

```python
def test_record_observation_new_pattern():
    """A pattern_id not in the accumulator gets added with sessions_seen=1."""
    from accumulator import Accumulator, record_observation
    acc = Accumulator()
    record_observation(
        acc,
        pattern_id="p1",
        name="P1",
        category="cat",
        target_stage="search",
        domain_tags=["civic"],
        evidence_row={"case_id": "c1", "signal": "..."},
        proposed_promotion_body="body",
    )
    assert len(acc.entries) == 1
    e = acc.entries[0]
    assert e.sessions_seen == 1
    assert e.sessions_since_last_seen == 0
    assert e.status == "hold"


def test_record_observation_existing_increments_seen():
    """Recording the same pattern again increments sessions_seen and resets stale."""
    from accumulator import Accumulator, AccumulatorEntry, record_observation
    acc = Accumulator(entries=[AccumulatorEntry(
        pattern_id="p1", name="P1", category="cat", target_stage="search",
        domain_tags=["civic"], sessions_seen=2, sessions_since_last_seen=3,
        status="hold", raised_bar=False, promotion_pending=False, demotion_count=0,
        evidence=[{"case_id": "c0", "signal": "..."}],
        proposed_promotion_body="body",
        created_at="2026-05-20T00:00:00Z",
        last_updated_at="2026-05-22T00:00:00Z",
    )])
    record_observation(
        acc, pattern_id="p1", name="P1", category="cat", target_stage="search",
        domain_tags=["civic"],
        evidence_row={"case_id": "c1", "signal": "new"},
        proposed_promotion_body="body",
    )
    assert acc.entries[0].sessions_seen == 3
    assert acc.entries[0].sessions_since_last_seen == 0
    assert len(acc.entries[0].evidence) == 2


def test_tick_staleness_increments_unobserved():
    """tick_staleness increments sessions_since_last_seen for entries not in the
    seen_set, leaves others alone."""
    from accumulator import Accumulator, AccumulatorEntry, tick_staleness
    e1 = AccumulatorEntry(pattern_id="p1", name="", category="", target_stage="",
                          domain_tags=[], sessions_seen=1, sessions_since_last_seen=0,
                          status="hold", raised_bar=False, promotion_pending=False,
                          demotion_count=0, evidence=[], proposed_promotion_body="",
                          created_at="", last_updated_at="")
    e2 = AccumulatorEntry(pattern_id="p2", name="", category="", target_stage="",
                          domain_tags=[], sessions_seen=1, sessions_since_last_seen=2,
                          status="hold", raised_bar=False, promotion_pending=False,
                          demotion_count=0, evidence=[], proposed_promotion_body="",
                          created_at="", last_updated_at="")
    acc = Accumulator(entries=[e1, e2])
    tick_staleness(acc, seen_pattern_ids={"p1"})
    assert acc.entries[0].sessions_since_last_seen == 0  # p1 observed
    assert acc.entries[1].sessions_since_last_seen == 3  # p2 not observed
```

**Step 2: Verify failure**

```
pytest tests/test_accumulator.py -k "record_observation or tick_staleness" -v
```
Expected: FAIL.

**Step 3: Implement**

Add to `scripts/accumulator.py`:

```python
from datetime import datetime, timezone


def record_observation(
    acc: Accumulator,
    *,
    pattern_id: str,
    name: str,
    category: str,
    target_stage: str,
    domain_tags: list[str],
    evidence_row: dict,
    proposed_promotion_body: str,
) -> AccumulatorEntry:
    """Record one observation. If the pattern_id exists, increment sessions_seen
    and append evidence. If new, add a fresh entry with sessions_seen=1, status=hold.
    Returns the entry (existing or new)."""
    now = datetime.now(timezone.utc).isoformat()
    for entry in acc.entries:
        if entry.pattern_id == pattern_id:
            if entry.status == "rejected":
                return entry  # never re-touch rejected entries
            entry.sessions_seen += 1
            entry.sessions_since_last_seen = 0
            entry.evidence.append(evidence_row)
            entry.last_updated_at = now
            return entry
    new_entry = AccumulatorEntry(
        pattern_id=pattern_id,
        name=name,
        category=category,
        target_stage=target_stage,
        domain_tags=list(domain_tags),
        sessions_seen=1,
        sessions_since_last_seen=0,
        status="hold",
        raised_bar=False,
        promotion_pending=False,
        demotion_count=0,
        evidence=[evidence_row],
        proposed_promotion_body=proposed_promotion_body,
        created_at=now,
        last_updated_at=now,
    )
    acc.entries.append(new_entry)
    return new_entry


def tick_staleness(acc: Accumulator, seen_pattern_ids: set[str]) -> None:
    """Increment sessions_since_last_seen for entries not in seen_pattern_ids.
    Called once per analyzer run after all observations are recorded."""
    for entry in acc.entries:
        if entry.pattern_id not in seen_pattern_ids and entry.status == "hold":
            entry.sessions_since_last_seen += 1
```

**Step 4: Verify pass**

```
pytest tests/test_accumulator.py -k "record_observation or tick_staleness" -v
```
Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git add scripts/accumulator.py tests/test_accumulator.py
git commit -m "feat(accumulator): record_observation + tick_staleness helpers"
```

---

### Task 2.3: Rejected-set persistence

**Files:**
- Modify: `scripts/accumulator.py`
- Test: `tests/test_accumulator.py`

**Step 1: Write failing test**

```python
def test_record_observation_skips_rejected_entries():
    """record_observation is a no-op for entries with status=rejected."""
    from accumulator import Accumulator, AccumulatorEntry, record_observation
    rejected = AccumulatorEntry(
        pattern_id="p1", name="", category="", target_stage="",
        domain_tags=[], sessions_seen=10, sessions_since_last_seen=0,
        status="rejected", raised_bar=False, promotion_pending=False,
        demotion_count=0, evidence=[],
        proposed_promotion_body="",
        created_at="", last_updated_at="",
    )
    acc = Accumulator(entries=[rejected])
    record_observation(
        acc, pattern_id="p1", name="", category="", target_stage="",
        domain_tags=[], evidence_row={"case_id": "c", "signal": "x"},
        proposed_promotion_body="",
    )
    # sessions_seen unchanged, no new evidence row
    assert acc.entries[0].sessions_seen == 10
    assert acc.entries[0].evidence == []


def test_mark_rejected_sets_status():
    """mark_rejected sets status=rejected, clears promotion_pending."""
    from accumulator import Accumulator, AccumulatorEntry, mark_rejected
    e = AccumulatorEntry(
        pattern_id="p1", name="", category="", target_stage="",
        domain_tags=[], sessions_seen=3, sessions_since_last_seen=0,
        status="promotion_pending", raised_bar=False, promotion_pending=True,
        demotion_count=0, evidence=[],
        proposed_promotion_body="",
        created_at="", last_updated_at="",
    )
    acc = Accumulator(entries=[e])
    mark_rejected(acc, pattern_id="p1")
    assert acc.entries[0].status == "rejected"
    assert acc.entries[0].promotion_pending is False
```

**Step 2: Verify failure**

```
pytest tests/test_accumulator.py -k "rejected" -v
```
Expected: FAIL.

**Step 3: Implement**

Confirm that the `record_observation` early-return for `status == "rejected"` is in place from task 2.2 (it is). Add:

```python
def mark_rejected(acc: Accumulator, pattern_id: str) -> None:
    """Mark an entry as permanently rejected. Clears promotion_pending."""
    for entry in acc.entries:
        if entry.pattern_id == pattern_id:
            entry.status = "rejected"
            entry.promotion_pending = False
            entry.last_updated_at = datetime.now(timezone.utc).isoformat()
            return
```

**Step 4: Verify pass**

```
pytest tests/test_accumulator.py -k "rejected" -v
```
Expected: PASS (2 tests).

**Step 5: Commit**

```bash
git add scripts/accumulator.py tests/test_accumulator.py
git commit -m "feat(accumulator): mark_rejected helper + record_observation skips rejected"
```

---

### Task 2.4: Promotion-pending flag handling

**Files:**
- Modify: `scripts/accumulator.py`
- Test: `tests/test_accumulator.py`

**Step 1: Write failing tests**

```python
def test_mark_promotion_pending():
    from accumulator import Accumulator, AccumulatorEntry, mark_promotion_pending
    e = AccumulatorEntry(
        pattern_id="p1", name="", category="", target_stage="",
        domain_tags=[], sessions_seen=3, sessions_since_last_seen=0,
        status="hold", raised_bar=False, promotion_pending=False,
        demotion_count=0, evidence=[], proposed_promotion_body="",
        created_at="", last_updated_at="",
    )
    acc = Accumulator(entries=[e])
    mark_promotion_pending(acc, "p1")
    assert acc.entries[0].promotion_pending is True
    assert acc.entries[0].status == "promotion_pending"


def test_clear_promotion_pending_returns_to_hold():
    """clear_promotion_pending sets status back to hold without deciding."""
    from accumulator import Accumulator, AccumulatorEntry, clear_promotion_pending
    e = AccumulatorEntry(
        pattern_id="p1", name="", category="", target_stage="",
        domain_tags=[], sessions_seen=3, sessions_since_last_seen=0,
        status="promotion_pending", raised_bar=False, promotion_pending=True,
        demotion_count=0, evidence=[], proposed_promotion_body="",
        created_at="", last_updated_at="",
    )
    acc = Accumulator(entries=[e])
    clear_promotion_pending(acc, "p1")
    assert acc.entries[0].status == "hold"
    assert acc.entries[0].promotion_pending is False


def test_remove_entry_for_graduation():
    """After successful promotion to learned_patterns.md, entry is removed."""
    from accumulator import Accumulator, AccumulatorEntry, remove_entry
    e = AccumulatorEntry(
        pattern_id="p1", name="", category="", target_stage="",
        domain_tags=[], sessions_seen=3, sessions_since_last_seen=0,
        status="promotion_pending", raised_bar=False, promotion_pending=True,
        demotion_count=0, evidence=[], proposed_promotion_body="",
        created_at="", last_updated_at="",
    )
    acc = Accumulator(entries=[e])
    remove_entry(acc, "p1")
    assert len(acc.entries) == 0
```

**Step 2: Verify failure**

```
pytest tests/test_accumulator.py -k "promotion_pending or remove_entry" -v
```
Expected: FAIL.

**Step 3: Implement**

Add to `scripts/accumulator.py`:

```python
def mark_promotion_pending(acc: Accumulator, pattern_id: str) -> None:
    """Flag an entry as eligible for promotion; status -> promotion_pending."""
    for entry in acc.entries:
        if entry.pattern_id == pattern_id:
            entry.promotion_pending = True
            entry.status = "promotion_pending"
            entry.last_updated_at = datetime.now(timezone.utc).isoformat()
            return


def clear_promotion_pending(acc: Accumulator, pattern_id: str) -> None:
    """Clear promotion_pending flag; status -> hold (user picked 'hold')."""
    for entry in acc.entries:
        if entry.pattern_id == pattern_id:
            entry.promotion_pending = False
            entry.status = "hold"
            entry.last_updated_at = datetime.now(timezone.utc).isoformat()
            return


def remove_entry(acc: Accumulator, pattern_id: str) -> None:
    """Remove entry by pattern_id (used after successful graduation)."""
    acc.entries = [e for e in acc.entries if e.pattern_id != pattern_id]
```

**Step 4: Verify pass**

```
pytest tests/test_accumulator.py -k "promotion_pending or remove_entry" -v
```
Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git add scripts/accumulator.py tests/test_accumulator.py
git commit -m "feat(accumulator): promotion_pending lifecycle + remove_entry helpers"
```

---

### Task 2.5: Demotion counter + permanent retirement after 2nd demotion

**Files:**
- Modify: `scripts/accumulator.py`
- Test: `tests/test_accumulator.py`

**Step 1: Write failing test**

```python
def test_demote_first_time_returns_to_hold_with_raised_bar():
    """First demotion: status=hold, raised_bar=True, demotion_count=1."""
    from accumulator import Accumulator, AccumulatorEntry, demote
    e = AccumulatorEntry(
        pattern_id="p1", name="", category="", target_stage="",
        domain_tags=[], sessions_seen=3, sessions_since_last_seen=0,
        status="hold", raised_bar=False, promotion_pending=False,
        demotion_count=0, evidence=[], proposed_promotion_body="",
        created_at="", last_updated_at="",
    )
    acc = Accumulator(entries=[e])
    demote(acc, "p1")
    assert acc.entries[0].status == "hold"
    assert acc.entries[0].raised_bar is True
    assert acc.entries[0].demotion_count == 1
    assert acc.entries[0].sessions_seen == 0  # reset for re-graduation count


def test_demote_second_time_marks_rejected():
    """Second demotion: status=rejected (permanent)."""
    from accumulator import Accumulator, AccumulatorEntry, demote
    e = AccumulatorEntry(
        pattern_id="p1", name="", category="", target_stage="",
        domain_tags=[], sessions_seen=5, sessions_since_last_seen=0,
        status="hold", raised_bar=True, promotion_pending=False,
        demotion_count=1, evidence=[], proposed_promotion_body="",
        created_at="", last_updated_at="",
    )
    acc = Accumulator(entries=[e])
    demote(acc, "p1")
    assert acc.entries[0].status == "rejected"
    assert acc.entries[0].demotion_count == 2
```

**Step 2: Verify failure**

```
pytest tests/test_accumulator.py -k "demote" -v
```
Expected: FAIL.

**Step 3: Implement**

```python
def demote(acc: Accumulator, pattern_id: str) -> None:
    """Demote a previously graduated pattern back into the accumulator.
    First demotion: status=hold, raised_bar=True, sessions_seen reset to 0.
    Second demotion: status=rejected (permanent).
    """
    now = datetime.now(timezone.utc).isoformat()
    for entry in acc.entries:
        if entry.pattern_id == pattern_id:
            entry.demotion_count += 1
            if entry.demotion_count >= 2:
                entry.status = "rejected"
            else:
                entry.status = "hold"
                entry.raised_bar = True
                entry.sessions_seen = 0  # earn it back from scratch under raised bar
                entry.sessions_since_last_seen = 0
                entry.promotion_pending = False
            entry.last_updated_at = now
            return
```

**Step 4: Verify pass**

```
pytest tests/test_accumulator.py -k "demote" -v
```
Expected: PASS (2 tests).

**Step 5: Commit**

```bash
git add scripts/accumulator.py tests/test_accumulator.py
git commit -m "feat(accumulator): demote helper with permanent-retirement on 2nd demotion"
```

---

### Task 2.6: Phase 2 review

Dispatch spec reviewer + code quality reviewer over Phase 2's 5 commits.

**Spec review prompt:**
"Review accumulator.py vs design Section 5.2 (accumulator.json schema). Confirm: AccumulatorEntry fields match design exactly; record_observation idempotent on rejected; mark_rejected / mark_promotion_pending / clear_promotion_pending / remove_entry / demote all implemented per Section 4 data flow. Flag schema or naming gaps."

**Code quality reviewer prompt:**
"Review accumulator.py code quality. Check: dataclass mutability, edge cases (empty acc, missing pattern_id), datetime handling (timezone-aware throughout), consistency of last_updated_at updates, lack of test for corrupt-file detection. Flag concerns."

Address findings before Phase 3.

---

## Phase 3: learned_patterns.md Parser/Writer

**Goal:** Implement the markdown parser and writer for `learned_patterns.md`. Tolerant on read (skip malformed entries, log them); strict on write. Round-trip stable.

**Files touched:** `scripts/learned_patterns.py` (new), `tests/test_learned_patterns_parser.py` (new).

---

### Task 3.1: Schema dataclass + write round-trip

**Files:**
- Create: `scripts/learned_patterns.py`
- Test: `tests/test_learned_patterns_parser.py`

**Step 1: Write failing test**

```python
import pytest
from pathlib import Path
from learned_patterns import (
    LearnedPattern,
    LearnedPatternsFile,
    LEARNED_PATTERNS_SCHEMA_VERSION,
    load_learned_patterns,
    save_learned_patterns,
)


def test_save_then_load_roundtrip(tmp_path):
    """Round-trip preserves all fields and grouping; no warnings on clean load."""
    target = tmp_path / "learned_patterns.md"
    file = LearnedPatternsFile(
        version=LEARNED_PATTERNS_SCHEMA_VERSION,
        patterns=[
            LearnedPattern(
                id="civic-alpr-t1-dominance-3f7a",
                name="T1 sources dominate",
                body="T1 sources dominate: government sites, fusion center reports, ACLU policy memos.",
                domain_tags=["civic", "alpr"],
                target_stage="search",
                category="source-tier-bias",
                wins=12, losses=1,
                promoted_at="2026-04-15",
                demotion_count=0,
            ),
            LearnedPattern(
                id="civic-alpr-entity-h2-9c2b",
                name="entity_expansion at hop 2",
                body="typically lifts confidence 0.5→0.75 for SC topics.",
                domain_tags=["civic", "alpr"],
                target_stage="hop_planner",
                category="hop-pattern-bias",
                wins=5, losses=1,
                promoted_at="2026-05-02",
                demotion_count=0,
            ),
        ],
    )
    save_learned_patterns(target, file)
    loaded, warnings = load_learned_patterns(target)
    assert loaded == file
    assert warnings == []


def test_load_missing_returns_empty(tmp_path):
    """Missing file returns empty LearnedPatternsFile with no warnings."""
    loaded, warnings = load_learned_patterns(tmp_path / "missing.md")
    assert loaded.version == LEARNED_PATTERNS_SCHEMA_VERSION
    assert loaded.patterns == []
    assert warnings == []


def test_load_version_mismatch_returns_empty_with_warning(tmp_path):
    """Schema version mismatch returns empty file + warning."""
    target = tmp_path / "learned_patterns.md"
    target.write_text("---\nversion: 99\n---\n\n## civic\n\n### Search patterns\n\n- **X** — body.\n  - id: `x`\n  - score: 1W / 0L (1 uses)\n  - promoted: 2026-04-15\n  - demotions: 0\n")
    loaded, warnings = load_learned_patterns(target)
    assert loaded.patterns == []
    assert len(warnings) == 1
    assert "learned_patterns_schema_mismatch" in warnings[0]
```

**Step 2: Verify failure**

```
pytest tests/test_learned_patterns_parser.py -v
```
Expected: FAIL (module missing).

**Step 3: Implement**

Create `scripts/learned_patterns.py`:

```python
"""learned_patterns.md — graduated patterns the orchestrator injects into
subagent user prompts. Grouped by domain → target_stage.

See docs/plans/2026-05-27-v3-1-case-learning-design.md Section 5.3 for schema.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from state import write_shared_state_atomically


LEARNED_PATTERNS_SCHEMA_VERSION = 1


@dataclass
class LearnedPattern:
    id: str
    name: str
    body: str
    domain_tags: list[str]
    target_stage: str  # "search" | "hop_planner" | "classify"
    category: str = ""  # source-tier-bias | hop-pattern-bias | query-template — preserved from accumulator entry on promotion so demotion can restore it
    wins: int = 0
    losses: int = 0
    promoted_at: str = ""
    demotion_count: int = 0


@dataclass
class LearnedPatternsFile:
    version: int = LEARNED_PATTERNS_SCHEMA_VERSION
    patterns: list[LearnedPattern] = field(default_factory=list)


_STAGE_LABELS = {
    "search": "Search patterns",
    "hop_planner": "Hop planning patterns",
    "classify": "Classify patterns",
}
_LABEL_TO_STAGE = {v: k for k, v in _STAGE_LABELS.items()}


def save_learned_patterns(path: Path, file: LearnedPatternsFile) -> None:
    """Render LearnedPatternsFile to markdown and atomic-write."""
    lines = ["---", f"version: {file.version}", "---", ""]
    grouped: dict[tuple, list[LearnedPattern]] = {}
    for p in file.patterns:
        key = tuple(p.domain_tags)
        grouped.setdefault(key, []).append(p)
    for domain_tags in sorted(grouped.keys()):
        lines.append(f"## {' / '.join(domain_tags)}")
        lines.append("")
        by_stage: dict[str, list[LearnedPattern]] = {}
        for p in grouped[domain_tags]:
            by_stage.setdefault(p.target_stage, []).append(p)
        for stage in ("search", "hop_planner", "classify"):
            if stage not in by_stage:
                continue
            lines.append(f"### {_STAGE_LABELS[stage]}")
            lines.append("")
            for p in by_stage[stage]:
                total = p.wins + p.losses
                lines.append(f"- **{p.name}** — {p.body}")
                lines.append(f"  - id: `{p.id}`")
                lines.append(f"  - category: {p.category}")
                lines.append(f"  - score: {p.wins}W / {p.losses}L ({total} uses)")
                lines.append(f"  - promoted: {p.promoted_at}")
                lines.append(f"  - demotions: {p.demotion_count}")
                lines.append("")
    write_shared_state_atomically(path, "\n".join(lines).rstrip() + "\n")


def load_learned_patterns(path: Path) -> tuple[LearnedPatternsFile, list[str]]:
    """Graceful load: returns (LearnedPatternsFile, warnings). Never raises.

    Tolerant per-entry parsing happens inside _parse_learned_patterns (malformed
    individual entries are skipped). Top-level concerns surfaced here:
    - missing file → empty file, no warning
    - read error → empty file, warning
    - schema version mismatch → empty file, warning
    """
    warnings: list[str] = []
    if not path.exists():
        return LearnedPatternsFile(), warnings
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        warnings.append(f"learned_patterns_corrupted: {path} could not be read ({e})")
        return LearnedPatternsFile(), warnings
    parsed = _parse_learned_patterns(text)
    if parsed.version != LEARNED_PATTERNS_SCHEMA_VERSION:
        warnings.append(
            f"learned_patterns_schema_mismatch: file is version {parsed.version!r}, "
            f"code expects {LEARNED_PATTERNS_SCHEMA_VERSION}. Treating as empty."
        )
        return LearnedPatternsFile(), warnings
    return parsed, warnings


def _parse_learned_patterns(text: str) -> LearnedPatternsFile:
    # Stub for now — implemented in next task.
    raise NotImplementedError("Parser comes in task 3.2")
```

**Step 4: Verify pass**

Half-pass: `test_save_then_load_roundtrip` will fail because parser isn't implemented yet; `test_load_missing_returns_empty` should PASS.

```
pytest tests/test_learned_patterns_parser.py::test_load_missing_returns_empty -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/learned_patterns.py tests/test_learned_patterns_parser.py
git commit -m "feat(learned_patterns): schema dataclass + writer (parser stub)"
```

---

### Task 3.2: Tolerant parser implementation

**Files:**
- Modify: `scripts/learned_patterns.py`
- Test: `tests/test_learned_patterns_parser.py`

**Step 1: Write failing tests**

Add to `tests/test_learned_patterns_parser.py`:

```python
def test_parse_skips_malformed_entry_missing_id(tmp_path, capsys):
    """Entry missing `id:` line is skipped; valid entries still parsed."""
    body = """---
version: 1
---

## civic / alpr

### Search patterns

- **Good entry** — has all fields.
  - id: `good-1`
  - score: 5W / 0L (5 uses)
  - promoted: 2026-04-15
  - demotions: 0

- **Bad entry** — missing id.
  - score: 1W / 0L (1 uses)
  - promoted: 2026-05-01
  - demotions: 0
"""
    target = tmp_path / "learned_patterns.md"
    target.write_text(body)
    loaded, _warnings = load_learned_patterns(target)
    assert len(loaded.patterns) == 1
    assert loaded.patterns[0].id == "good-1"


def test_parse_recovers_score_line():
    """Score line `score: 12W / 1L (13 uses)` parses to wins=12, losses=1."""
    body = """---
version: 1
---

## civic / alpr

### Search patterns

- **Entry** — body text.
  - id: `e1`
  - score: 12W / 1L (13 uses)
  - promoted: 2026-04-15
  - demotions: 2
"""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "lp.md"
        p.write_text(body)
        loaded, _warnings = load_learned_patterns(p)
    assert len(loaded.patterns) == 1
    p0 = loaded.patterns[0]
    assert p0.wins == 12
    assert p0.losses == 1
    assert p0.demotion_count == 2
```

**Step 2: Verify failure**

```
pytest tests/test_learned_patterns_parser.py -v
```
Expected: FAIL with `NotImplementedError`.

**Step 3: Implement the parser**

Replace `_parse_learned_patterns` in `scripts/learned_patterns.py`:

```python
_DOMAIN_HEADING = re.compile(r"^##\s+(.+)$")
_STAGE_HEADING = re.compile(r"^###\s+(.+)$")
_PATTERN_HEADER = re.compile(r"^-\s+\*\*(.+?)\*\*\s+—\s+(.+)$")
_FIELD_LINE = re.compile(r"^\s+-\s+(\w+):\s*(.+)$")
_SCORE_LINE = re.compile(r"^(\d+)W\s*/\s*(\d+)L")


def _parse_learned_patterns(text: str) -> LearnedPatternsFile:
    lines = text.splitlines()
    version = LEARNED_PATTERNS_SCHEMA_VERSION

    # Strip YAML frontmatter if present
    i = 0
    if i < len(lines) and lines[i].strip() == "---":
        i += 1
        while i < len(lines) and lines[i].strip() != "---":
            if lines[i].startswith("version:"):
                try:
                    version = int(lines[i].split(":", 1)[1].strip())
                except ValueError:
                    pass
            i += 1
        i += 1  # past closing ---

    patterns: list[LearnedPattern] = []
    current_domain: list[str] = []
    current_stage: str | None = None
    pending: dict | None = None

    def _flush():
        nonlocal pending
        if pending is None:
            return
        # Validate required fields
        if "id" not in pending or "score" not in pending:
            print(
                f"[learned_patterns] skipping malformed entry "
                f"(missing id or score): {pending.get('name', '?')}"
            )
            pending = None
            return
        # Parse score
        m = _SCORE_LINE.match(pending["score"])
        if not m:
            print(
                f"[learned_patterns] skipping malformed entry "
                f"(bad score: {pending['score']!r}): {pending.get('name', '?')}"
            )
            pending = None
            return
        wins, losses = int(m.group(1)), int(m.group(2))
        try:
            demotion_count = int(pending.get("demotions", "0"))
        except ValueError:
            demotion_count = 0
        patterns.append(LearnedPattern(
            id=pending["id"].strip("`"),
            name=pending["name"],
            body=pending["body"],
            domain_tags=list(current_domain),
            target_stage=current_stage or "search",
            category=pending.get("category", ""),
            wins=wins,
            losses=losses,
            promoted_at=pending.get("promoted", ""),
            demotion_count=demotion_count,
        ))
        pending = None

    while i < len(lines):
        line = lines[i]
        domain_match = _DOMAIN_HEADING.match(line)
        stage_match = _STAGE_HEADING.match(line)
        header_match = _PATTERN_HEADER.match(line)
        field_match = _FIELD_LINE.match(line)

        if domain_match:
            _flush()
            current_domain = [t.strip() for t in domain_match.group(1).split("/")]
            current_stage = None
        elif stage_match:
            _flush()
            label = stage_match.group(1).strip()
            current_stage = _LABEL_TO_STAGE.get(label, "search")
        elif header_match:
            _flush()
            pending = {
                "name": header_match.group(1).strip(),
                "body": header_match.group(2).strip(),
            }
        elif field_match and pending is not None:
            key = field_match.group(1).lower()
            value = field_match.group(2).strip()
            pending[key] = value

        i += 1

    _flush()
    return LearnedPatternsFile(version=version, patterns=patterns)
```

**Step 4: Verify pass**

```
pytest tests/test_learned_patterns_parser.py -v
```
Expected: PASS (all 4 tests now).

**Step 5: Commit**

```bash
git add scripts/learned_patterns.py tests/test_learned_patterns_parser.py
git commit -m "feat(learned_patterns): tolerant markdown parser with skip-on-malformed"
```

---

### Task 3.3: Filter helpers (by topic text / by domain_tags / by target_stage)

**Files:**
- Modify: `scripts/learned_patterns.py`
- Test: `tests/test_learned_patterns_parser.py`

The orchestrator needs two filter modes:

- **`filter_by_topic_text`** — used at Stage 2 BEFORE `domain_tags` exist. The current v3.0.0 pipeline derives `domain_tags` only at case-write time (Stage 10, from the most common tags across written notes — see `skills/research/SKILL.md:1250` and surrounding context). At Stage 2 the orchestrator only has topic strings from the resolver output. This helper does case-insensitive substring / token-overlap matching of each pattern's `domain_tags` against the joined topic text. Patterns whose tags appear anywhere in the topic text are considered relevant.
- **`filter_relevant`** — used at Stage 10b when a case's `domain_tags` ARE available (derived from written notes). Same overlap-with-tags shape, but exact tag matching rather than fuzzy text.
- **`group_by_stage`** — partitions a list of patterns by `target_stage`.

**Step 1: Write failing tests**

```python
def test_filter_by_topic_text_substring_match():
    """filter_by_topic_text matches patterns whose domain_tags appear as
    case-insensitive substrings in the joined topic text. Used at Stage 2
    where formal domain_tags don't yet exist."""
    from learned_patterns import LearnedPatternsFile, LearnedPattern, filter_by_topic_text
    f = LearnedPatternsFile(patterns=[
        LearnedPattern(id="a", name="A", body="", domain_tags=["civic", "alpr"],
                       target_stage="search"),
        LearnedPattern(id="b", name="B", body="", domain_tags=["tech"],
                       target_stage="search"),
        LearnedPattern(id="c", name="C", body="", domain_tags=["civic"],
                       target_stage="hop_planner"),
    ])
    # "civic" appears in topic text → matches a (tagged civic/alpr) and c (tagged civic).
    # b (tagged only "tech") does NOT match — "tech" not in topic text.
    relevant = filter_by_topic_text(f, topics=["civic ALPR programs in Greenville"])
    assert {p.id for p in relevant} == {"a", "c"}


def test_filter_by_topic_text_case_insensitive():
    from learned_patterns import LearnedPatternsFile, LearnedPattern, filter_by_topic_text
    f = LearnedPatternsFile(patterns=[
        LearnedPattern(id="a", name="A", body="", domain_tags=["Civic"],
                       target_stage="search"),
    ])
    relevant = filter_by_topic_text(f, topics=["alpr in CIVIC contexts"])
    assert len(relevant) == 1


def test_filter_by_domain_overlap():
    """filter_relevant matches by exact domain_tags overlap. Used at Stage 10b
    when the case has its derived domain_tags available."""
    from learned_patterns import LearnedPatternsFile, LearnedPattern, filter_relevant
    f = LearnedPatternsFile(patterns=[
        LearnedPattern(id="a", name="A", body="", domain_tags=["civic", "alpr"],
                       target_stage="search"),
        LearnedPattern(id="b", name="B", body="", domain_tags=["tech"],
                       target_stage="search"),
        LearnedPattern(id="c", name="C", body="", domain_tags=["civic"],
                       target_stage="hop_planner"),
    ])
    relevant = filter_relevant(f, run_domain_tags=["civic"])
    assert {p.id for p in relevant} == {"a", "c"}


def test_group_by_target_stage():
    """group_by_stage returns dict[stage -> list[LearnedPattern]]."""
    from learned_patterns import LearnedPattern, group_by_stage
    patterns = [
        LearnedPattern(id="a", name="A", body="", domain_tags=["x"], target_stage="search"),
        LearnedPattern(id="b", name="B", body="", domain_tags=["x"], target_stage="hop_planner"),
        LearnedPattern(id="c", name="C", body="", domain_tags=["x"], target_stage="search"),
    ]
    grouped = group_by_stage(patterns)
    assert {p.id for p in grouped["search"]} == {"a", "c"}
    assert {p.id for p in grouped["hop_planner"]} == {"b"}
    assert grouped.get("classify", []) == []
```

**Step 2: Verify failure**

```
pytest tests/test_learned_patterns_parser.py -k "filter_by_topic_text or filter_relevant or group_by_stage" -v
```
Expected: FAIL.

**Step 3: Implement**

Add to `scripts/learned_patterns.py`:

```python
def filter_by_topic_text(
    file: LearnedPatternsFile,
    *,
    topics: list[str],
) -> list[LearnedPattern]:
    """Return patterns whose domain_tags appear as case-insensitive substrings
    in the joined topic text. Used at Stage 2 when formal domain_tags don't
    exist yet (v3.0.0 derives domain_tags only at case-write time from
    written-note tags). Conservative on false positives — token-substring
    only; no stemming or fuzzy matching."""
    if not topics:
        return []
    joined = " ".join(topics).lower()
    return [
        p for p in file.patterns
        if any(tag.lower() in joined for tag in p.domain_tags)
    ]


def filter_relevant(
    file: LearnedPatternsFile,
    *,
    run_domain_tags: list[str],
) -> list[LearnedPattern]:
    """Return patterns whose domain_tags overlap with run_domain_tags.
    Used at Stage 10b when the case has its derived domain_tags available."""
    run_set = set(run_domain_tags)
    return [p for p in file.patterns if run_set & set(p.domain_tags)]


def group_by_stage(patterns: list[LearnedPattern]) -> dict[str, list[LearnedPattern]]:
    """Group patterns into a dict keyed by target_stage.
    All three known stages are present in the returned dict (empty lists if no patterns)."""
    out: dict[str, list[LearnedPattern]] = {"search": [], "hop_planner": [], "classify": []}
    for p in patterns:
        out.setdefault(p.target_stage, []).append(p)
    return out
```

**Step 4: Verify pass**

```
pytest tests/test_learned_patterns_parser.py -k "filter_by_topic_text or filter_relevant or group_by_stage" -v
```
Expected: PASS (4 tests).

**Step 5: Commit**

```bash
git add scripts/learned_patterns.py tests/test_learned_patterns_parser.py
git commit -m "feat(learned_patterns): filter_by_topic_text + filter_relevant + group_by_stage"
```

---

### Task 3.4: Phase 3 review

Spec + code-quality review over Phase 3's 3 commits.

**Spec review prompt:**
"Review learned_patterns.py vs design Section 5.3. Confirm: schema dataclass matches; round-trip preserves all fields; tolerant parser skips malformed entries with a warning; filter_relevant uses domain_tags overlap; group_by_stage covers all three stages."

**Code quality:**
"Review the markdown parser for regex robustness, Unicode handling (em-dash, arrow), parser edge cases (empty file, frontmatter-only, no patterns under a section heading), and printing-instead-of-logging tradeoff."

---

## Phase 4: Heuristic Candidate Detection

**Goal:** Implement the pure-Python heuristic aggregations that scan recent cases and produce candidate observations.

**Files touched:** `scripts/pattern_detection.py` (new), `tests/test_pattern_detection.py` (new), `tests/fixtures/case_learning/`.

---

### Task 4.1: Create fixture case set

**Files:**
- Create: `tests/fixtures/case_learning/civic_alpr_cases.json`
- Create: `tests/fixtures/case_learning/tech_cases.json`
- Create: `tests/fixtures/case_learning/sparse_domain.json`
- Create: `tests/fixtures/case_learning/contradictory_outcomes.json`

**Step 1: Write each fixture**

Each fixture is a JSON file containing a list of case dicts conforming to the v3.1.0 case schema (Section 5.1 of design). Minimum 6 cases per fixture for the dense ones; 1-2 for sparse.

`civic_alpr_cases.json` — 8 cases with consistent T1 dominance (source_tiers.T1 dominant in `patterns_that_worked`), entity_expansion at hop 2 lifting confidence.

`tech_cases.json` — 8 cases with conceptual_deepening as the hop pattern that lifts confidence; mixed T1/T2 source distribution.

`sparse_domain.json` — 1-2 cases in a "niche" domain — analyzer should produce zero candidates from this.

`contradictory_outcomes.json` — cases where the SAME observation appears with conflicting outcomes (e.g., entity_expansion lifts confidence in 3 cases, drops it in 4 cases). Tests that the heuristic doesn't propose a clear candidate.

**Step 2: Sanity-check fixtures load as JSON**

```
python -c "import json; [json.load(open(f)) for f in ['tests/fixtures/case_learning/civic_alpr_cases.json', 'tests/fixtures/case_learning/tech_cases.json', 'tests/fixtures/case_learning/sparse_domain.json', 'tests/fixtures/case_learning/contradictory_outcomes.json']]"
```
Expected: no output (success).

**Step 3: Commit**

```bash
git add tests/fixtures/case_learning/
git commit -m "test: add case_learning fixture set for v3.1.0 analyzer tests"
```

---

### Task 4.2: Source-tier dominance detection

**Files:**
- Create: `scripts/pattern_detection.py`
- Test: `tests/test_pattern_detection.py`

**Step 1: Write failing test**

```python
import json
from pathlib import Path
import pytest


def test_detect_source_tier_dominance_civic_alpr():
    """When civic+alpr cases consistently show T1-dominant patterns_that_worked,
    detect_source_tier_dominance produces a candidate observation."""
    from pattern_detection import detect_source_tier_dominance
    cases = json.loads(Path("tests/fixtures/case_learning/civic_alpr_cases.json").read_text())
    candidates = detect_source_tier_dominance(cases, min_dominance=0.5, min_cases=3)
    civic_alpr = [c for c in candidates if set(c["domain_tags"]) == {"civic", "alpr"}]
    assert len(civic_alpr) == 1
    c = civic_alpr[0]
    assert c["category"] == "source-tier-bias"
    assert c["target_stage"] == "search"
    assert "T1" in c["name"] or "T1" in c["proposed_promotion_body"]


def test_detect_source_tier_dominance_sparse_returns_empty():
    """Sparse fixture (1-2 cases) doesn't produce candidates."""
    from pattern_detection import detect_source_tier_dominance
    cases = json.loads(Path("tests/fixtures/case_learning/sparse_domain.json").read_text())
    candidates = detect_source_tier_dominance(cases, min_dominance=0.5, min_cases=3)
    assert candidates == []
```

**Step 2: Verify failure**

```
pytest tests/test_pattern_detection.py -k source_tier -v
```
Expected: FAIL.

**Step 3: Implement**

Create `scripts/pattern_detection.py`:

```python
"""Heuristic candidate detection over case records.

Pure Python; no LLM calls. Produces candidate observations for the accumulator.

See docs/plans/2026-05-27-v3-1-case-learning-design.md Section 6.1.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any


def _short_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:4]


def _make_pattern_id(domain_slug: str, category: str, stable_key: str) -> str:
    """Deterministic pattern_id. `stable_key` MUST be the same string for the
    same underlying observation across runs (e.g., the dominant tier name,
    the winning hop pattern name, the templatized query). Do NOT pass
    timestamps or other per-run values — those break sessions_seen accumulation.
    """
    safe_domain = domain_slug.replace("/", "-").replace(" ", "-").lower()
    safe_cat = category.replace("_", "-").lower()
    return f"{safe_domain}-{safe_cat}-{_short_hash(stable_key)}"


def detect_source_tier_dominance(
    cases: list[dict],
    *,
    min_dominance: float = 0.5,
    min_cases: int = 3,
) -> list[dict]:
    """Detect domains where one source tier (T1 / T2 / T3 / T4) consistently
    dominates patterns_that_worked.source_tiers across cases.

    Returns a list of candidate dicts ready for accumulator.record_observation().
    """
    by_domain: dict[tuple, list[dict]] = defaultdict(list)
    for case in cases:
        key = tuple(sorted(case.get("domain_tags", [])))
        if not key:
            continue
        by_domain[key].append(case)

    candidates = []

    for domain_tags, domain_cases in by_domain.items():
        if len(domain_cases) < min_cases:
            continue
        # Aggregate source tier distribution across cases
        tier_totals = {"T1": 0, "T2": 0, "T3": 0, "T4": 0}
        for c in domain_cases:
            tiers = (c.get("patterns_that_worked", {}) or {}).get("source_tiers", {}) or {}
            for k, v in tiers.items():
                if k in tier_totals:
                    tier_totals[k] += v
        total = sum(tier_totals.values())
        if total == 0:
            continue
        dominant_tier = max(tier_totals, key=lambda k: tier_totals[k])
        share = tier_totals[dominant_tier] / total
        if share < min_dominance:
            continue

        domain_slug = "-".join(domain_tags)
        name = f"{dominant_tier} sources dominate for {' / '.join(domain_tags)} queries"
        body = (
            f"{dominant_tier} sources tend to score highest for queries in this domain. "
            f"Observed share: {share:.0%} across {len(domain_cases)} cases."
        )
        evidence = [
            {
                "case_id": c.get("case_id"),
                "signal": f"{dominant_tier}={(c.get('patterns_that_worked', {}) or {}).get('source_tiers', {}).get(dominant_tier, 0)}, "
                          f"conf_avg={_avg_confidence(c):.2f}",
            }
            for c in domain_cases
        ]
        # stable_key is the dominant tier name — recurs identically across runs
        pid = _make_pattern_id(domain_slug, "source-tier-bias", dominant_tier)
        candidates.append({
            "pattern_id": pid,
            "name": name,
            "category": "source-tier-bias",
            "target_stage": "search",
            "domain_tags": list(domain_tags),
            "proposed_promotion_body": body,
            "evidence_rows": evidence,
        })
    return candidates


def _avg_confidence(case: dict) -> float:
    cpt = case.get("confidence_per_topic", {})
    if not cpt:
        return 0.0
    vals = [v for v in cpt.values() if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else 0.0
```

**Step 4: Verify pass**

```
pytest tests/test_pattern_detection.py -k source_tier -v
```
Expected: PASS (2 tests).

**Step 5: Commit**

```bash
git add scripts/pattern_detection.py tests/test_pattern_detection.py
git commit -m "feat(pattern_detection): source-tier dominance heuristic"
```

---

### Task 4.3: Hop-pattern confidence-delta detection

**Files:**
- Modify: `scripts/pattern_detection.py`
- Test: `tests/test_pattern_detection.py`

**Step 1: Write failing test**

```python
def test_detect_hop_pattern_confidence_delta_tech():
    """When tech-domain cases consistently show conceptual_deepening
    delivers the biggest confidence lift at a given hop position,
    detect_hop_pattern_lift produces a candidate."""
    from pattern_detection import detect_hop_pattern_lift
    cases = json.loads(Path("tests/fixtures/case_learning/tech_cases.json").read_text())
    candidates = detect_hop_pattern_lift(cases, min_lift=0.1, min_cases=3)
    tech_candidates = [c for c in candidates if "tech" in c["domain_tags"]]
    assert len(tech_candidates) >= 1
    c = tech_candidates[0]
    assert c["category"] == "hop-pattern-bias"
    assert c["target_stage"] == "hop_planner"
```

**Step 2: Verify failure**

```
pytest tests/test_pattern_detection.py -k hop_pattern -v
```
Expected: FAIL.

**Step 3: Implement**

Add to `scripts/pattern_detection.py`:

```python
def detect_hop_pattern_lift(
    cases: list[dict],
    *,
    min_lift: float = 0.1,
    min_cases: int = 3,
) -> list[dict]:
    """Detect domains where one hop pattern (entity_expansion / temporal_progression
    / conceptual_deepening / causal_chain) consistently lifts confidence the most
    when applied at a given hop position.

    Cases must include patterns_that_worked.hop_chain and confidence_per_topic.
    """
    by_domain: dict[tuple, list[dict]] = defaultdict(list)
    for case in cases:
        key = tuple(sorted(case.get("domain_tags", [])))
        if not key:
            continue
        by_domain[key].append(case)

    candidates = []

    for domain_tags, domain_cases in by_domain.items():
        if len(domain_cases) < min_cases:
            continue
        # Count hop pattern occurrences in patterns_that_worked
        pattern_counts: dict[str, int] = defaultdict(int)
        for c in domain_cases:
            chain = (c.get("patterns_that_worked", {}) or {}).get("hop_chain", []) or []
            for p in chain:
                pattern_counts[p] += 1
        if not pattern_counts:
            continue
        # Pick the most frequent
        winning_pattern = max(pattern_counts, key=lambda k: pattern_counts[k])
        share = pattern_counts[winning_pattern] / sum(pattern_counts.values())
        if share < (1 - min_lift):  # winner needs strong dominance
            continue

        domain_slug = "-".join(domain_tags)
        name = f"{winning_pattern} preferred for {' / '.join(domain_tags)} topics"
        body = (
            f"The {winning_pattern} hop pattern appears in patterns_that_worked "
            f"across {pattern_counts[winning_pattern]}/{sum(pattern_counts.values())} "
            f"hop transitions in this domain."
        )
        evidence = [
            {
                "case_id": c.get("case_id"),
                "signal": f"hop_chain={(c.get('patterns_that_worked', {}) or {}).get('hop_chain', [])}, "
                          f"conf_avg={_avg_confidence(c):.2f}",
            }
            for c in domain_cases
        ]
        # stable_key is the winning hop-pattern name — recurs identically across runs
        pid = _make_pattern_id(domain_slug, "hop-pattern-bias", winning_pattern)
        candidates.append({
            "pattern_id": pid,
            "name": name,
            "category": "hop-pattern-bias",
            "target_stage": "hop_planner",
            "domain_tags": list(domain_tags),
            "proposed_promotion_body": body,
            "evidence_rows": evidence,
        })
    return candidates
```

**Step 4: Verify pass**

```
pytest tests/test_pattern_detection.py -k hop_pattern -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/pattern_detection.py tests/test_pattern_detection.py
git commit -m "feat(pattern_detection): hop-pattern confidence-lift heuristic"
```

---

### Task 4.4: Query-template recurrence detection

**Files:**
- Modify: `scripts/pattern_detection.py`
- Test: `tests/test_pattern_detection.py`

**Step 1: Write failing test**

```python
def test_detect_query_template_recurrence():
    """When the same query template (e.g., '[city] ALPR [year]') recurs across
    cases as a high-success query, detect_query_template_recurrence flags it."""
    from pattern_detection import detect_query_template_recurrence
    cases = json.loads(Path("tests/fixtures/case_learning/civic_alpr_cases.json").read_text())
    candidates = detect_query_template_recurrence(cases, min_recurrence=3)
    assert any(c["category"] == "query-template" for c in candidates)
```

**Step 2: Verify failure**

```
pytest tests/test_pattern_detection.py -k query_template -v
```
Expected: FAIL.

**Step 3: Implement**

Add a simple template-extraction approach. Replace tokens that look like proper nouns / years with placeholders, then count recurrence:

```python
import re


_YEAR_PATTERN = re.compile(r"\b(19|20|21)\d{2}\b")
_PROPER_NOUN = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")


def _templatize(query: str) -> str:
    """Replace likely proper-noun spans and years with placeholders."""
    t = _YEAR_PATTERN.sub("[year]", query)
    t = _PROPER_NOUN.sub("[entity]", t)
    return t.strip().lower()


def detect_query_template_recurrence(
    cases: list[dict],
    *,
    min_recurrence: int = 3,
) -> list[dict]:
    """Detect query templates that recur across cases as queries that worked."""
    by_domain_template: dict[tuple, list[dict]] = defaultdict(list)
    for case in cases:
        domain = tuple(sorted(case.get("domain_tags", [])))
        if not domain:
            continue
        queries = (case.get("patterns_that_worked", {}) or {}).get("queries", []) or []
        for q in queries:
            if not isinstance(q, str):
                continue
            template = _templatize(q)
            by_domain_template[(domain, template)].append(
                {"case_id": case.get("case_id"), "raw_query": q}
            )

    candidates = []
    for (domain, template), instances in by_domain_template.items():
        if len(instances) < min_recurrence:
            continue
        domain_slug = "-".join(domain)
        name = f"Recurring query template for {' / '.join(domain)}: {template}"
        body = (
            f"Query template `{template}` recurred {len(instances)} times across "
            f"recent runs in this domain."
        )
        evidence = [
            {"case_id": inst["case_id"], "signal": f"raw_query={inst['raw_query']!r}"}
            for inst in instances
        ]
        # stable_key is the templatized query — recurs identically across runs
        pid = _make_pattern_id(domain_slug, "query-template", template)
        candidates.append({
            "pattern_id": pid,
            "name": name,
            "category": "query-template",
            "target_stage": "search",
            "domain_tags": list(domain),
            "proposed_promotion_body": body,
            "evidence_rows": evidence,
        })
    return candidates
```

**Step 4: Verify pass**

```
pytest tests/test_pattern_detection.py -k query_template -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/pattern_detection.py tests/test_pattern_detection.py
git commit -m "feat(pattern_detection): query template recurrence heuristic"
```

---

### Task 4.5: Phase 4 review

Spec + code-quality review.

**Spec review:**
"Three heuristics implemented per design Section 6.1: source-tier dominance, hop-pattern lift, query-template recurrence. Confirm each returns the expected candidate dict shape (pattern_id, name, category, target_stage, domain_tags, proposed_promotion_body, evidence_rows). Confirm sparse cases produce no candidates."

**Code quality:**
"Review pattern_detection.py for: deterministic pattern_id generation (hash-based, stable across runs), edge cases (empty cases list, missing fields in case dict), regex robustness in templatize, and the threshold-tuning knobs being parameterized correctly."

---

## Phase 5: Score Updates + Demotion Sweep

**Goal:** Implement W/L computation per case outcome, score updates on `learned_patterns.md`, demotion sweep when ratios fall below threshold.

**Files touched:** `scripts/score_updates.py` (new), `tests/test_score_updates.py` (new).

---

### Task 5.1: Run-level outcome calculation (W or L)

**Files:**
- Create: `scripts/score_updates.py`
- Test: `tests/test_score_updates.py`

**Step 1: Write failing test**

```python
import pytest


def test_compute_run_outcome_win():
    """Win: avg confidence >= target, no abandon, contradiction_rate <= 0.3."""
    from score_updates import compute_run_outcome
    case = {
        "confidence_per_topic": {"t1": 0.82, "t2": 0.78},
        "contradiction_rate": 0.15,
        "outcomes": {"user_decisions": [{"stage": "5", "choice": "accept"}]},
        "depths_used": {"standard": 2},
    }
    assert compute_run_outcome(case, confidence_target=0.75) == "W"


def test_compute_run_outcome_loss_low_confidence():
    """Loss: avg confidence below target."""
    from score_updates import compute_run_outcome
    case = {
        "confidence_per_topic": {"t1": 0.55, "t2": 0.6},
        "contradiction_rate": 0.1,
        "outcomes": {"user_decisions": []},
    }
    assert compute_run_outcome(case, confidence_target=0.75) == "L"


def test_compute_run_outcome_loss_user_abandoned():
    """Loss: user picked 'abandon' at quality gate."""
    from score_updates import compute_run_outcome
    case = {
        "confidence_per_topic": {"t1": 0.82},
        "contradiction_rate": 0.1,
        "outcomes": {"user_decisions": [{"stage": "5", "choice": "abandon"}]},
    }
    assert compute_run_outcome(case, confidence_target=0.75) == "L"


def test_compute_run_outcome_loss_contradiction_spike():
    """Loss: contradiction_rate > 0.3."""
    from score_updates import compute_run_outcome
    case = {
        "confidence_per_topic": {"t1": 0.82},
        "contradiction_rate": 0.45,
        "outcomes": {"user_decisions": []},
    }
    assert compute_run_outcome(case, confidence_target=0.75) == "L"
```

**Step 2: Verify failure**

```
pytest tests/test_score_updates.py -k compute_run_outcome -v
```
Expected: FAIL.

**Step 3: Implement**

Create `scripts/score_updates.py`:

```python
"""Run-level W/L computation + score updates on learned_patterns.md.

See docs/plans/2026-05-27-v3-1-case-learning-design.md Section 6.1.
"""

from __future__ import annotations

from learned_patterns import LearnedPattern, LearnedPatternsFile


def compute_run_outcome(case: dict, *, confidence_target: float = 0.75) -> str:
    """Compute a W or L verdict for a completed run.

    Win = avg confidence across topics >= target
        AND no user abandonment at quality gate
        AND contradiction_rate <= 0.3.
    Loss = any of those fail.
    """
    cpt = case.get("confidence_per_topic", {}) or {}
    if cpt:
        vals = [v for v in cpt.values() if isinstance(v, (int, float))]
        avg_conf = sum(vals) / len(vals) if vals else 0.0
    else:
        avg_conf = 0.0
    if avg_conf < confidence_target:
        return "L"

    contradiction = case.get("contradiction_rate", 0.0)
    if contradiction > 0.3:
        return "L"

    decisions = (case.get("outcomes", {}) or {}).get("user_decisions", []) or []
    for d in decisions:
        if d.get("choice") == "abandon":
            return "L"
    return "W"
```

**Step 4: Verify pass**

```
pytest tests/test_score_updates.py -k compute_run_outcome -v
```
Expected: PASS (4 tests).

**Step 5: Commit**

```bash
git add scripts/score_updates.py tests/test_score_updates.py
git commit -m "feat(score_updates): run-level W/L computation"
```

---

### Task 5.2: Apply score update to LearnedPattern

**Files:**
- Modify: `scripts/score_updates.py`
- Test: `tests/test_score_updates.py`

**Step 1: Write failing test**

```python
def test_apply_score_increments_wins():
    from score_updates import apply_score
    from learned_patterns import LearnedPattern
    p = LearnedPattern(id="p1", name="", body="", domain_tags=[],
                       target_stage="search", wins=2, losses=1)
    apply_score(p, "W")
    assert p.wins == 3 and p.losses == 1


def test_apply_score_increments_losses():
    from score_updates import apply_score
    from learned_patterns import LearnedPattern
    p = LearnedPattern(id="p1", name="", body="", domain_tags=[],
                       target_stage="search", wins=2, losses=1)
    apply_score(p, "L")
    assert p.wins == 2 and p.losses == 2
```

**Step 2: Verify failure**

```
pytest tests/test_score_updates.py -k apply_score -v
```
Expected: FAIL.

**Step 3: Implement**

```python
def apply_score(pattern: LearnedPattern, outcome: str) -> None:
    """Increment wins or losses on a LearnedPattern in place."""
    if outcome == "W":
        pattern.wins += 1
    elif outcome == "L":
        pattern.losses += 1
    else:
        raise ValueError(f"outcome must be 'W' or 'L', got {outcome!r}")
```

**Step 4: Verify pass**

```
pytest tests/test_score_updates.py -k apply_score -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/score_updates.py tests/test_score_updates.py
git commit -m "feat(score_updates): apply_score increments W/L on LearnedPattern"
```

---

### Task 5.3: Demotion sweep over LearnedPatternsFile

**Files:**
- Modify: `scripts/score_updates.py`
- Test: `tests/test_score_updates.py`

**Step 1: Write failing tests**

```python
def test_demotion_sweep_flags_below_ratio():
    """Pattern with W:L < 0.4 AND uses >= 5 is flagged for demotion."""
    from score_updates import find_demotion_targets
    from learned_patterns import LearnedPattern, LearnedPatternsFile
    f = LearnedPatternsFile(patterns=[
        LearnedPattern(id="bad", name="", body="", domain_tags=[],
                       target_stage="search", wins=1, losses=4),  # 1/5 = 0.2 ratio
        LearnedPattern(id="good", name="", body="", domain_tags=[],
                       target_stage="search", wins=4, losses=1),  # 4/5 = 0.8 ratio
        LearnedPattern(id="few", name="", body="", domain_tags=[],
                       target_stage="search", wins=0, losses=3),  # uses < 5
    ])
    targets = find_demotion_targets(f, min_uses=5, max_loss_ratio=0.4)
    assert {p.id for p in targets} == {"bad"}


def test_demotion_sweep_ratio_exact_threshold():
    """Pattern with W:L = 0.4 exactly is NOT demoted (must be < 0.4)."""
    from score_invariable import LearnedPattern, LearnedPatternsFile  # typo intentional - will fail
    # placeholder
```

Drop the second test stub and replace with:

```python
def test_demotion_sweep_ratio_exact_threshold():
    """Pattern with W:L = 0.4 exactly is NOT demoted (must be < 0.4)."""
    from score_updates import find_demotion_targets
    from learned_patterns import LearnedPattern, LearnedPatternsFile
    f = LearnedPatternsFile(patterns=[
        LearnedPattern(id="boundary", name="", body="", domain_tags=[],
                       target_stage="search", wins=2, losses=3),  # 2/5 = 0.4 exactly
    ])
    targets = find_demotion_targets(f, min_uses=5, max_loss_ratio=0.4)
    assert targets == []
```

**Step 2: Verify failure**

```
pytest tests/test_score_updates.py -k demotion_sweep -v
```
Expected: FAIL.

**Step 3: Implement**

```python
def find_demotion_targets(
    file: LearnedPatternsFile,
    *,
    min_uses: int = 5,
    max_loss_ratio: float = 0.4,
) -> list[LearnedPattern]:
    """Return patterns eligible for demotion: total uses >= min_uses AND
    W / (W+L) < max_loss_ratio.
    """
    targets = []
    for p in file.patterns:
        total = p.wins + p.losses
        if total < min_uses:
            continue
        ratio = p.wins / total if total > 0 else 0.0
        if ratio < max_loss_ratio:
            targets.append(p)
    return targets
```

**Step 4: Verify pass**

```
pytest tests/test_score_updates.py -k demotion_sweep -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/score_updates.py tests/test_score_updates.py
git commit -m "feat(score_updates): find_demotion_targets for end-of-run sweep"
```

---

### Task 5.4: Phase 5 review

Spec + code-quality review over score_updates.py.

**Spec review:**
"Confirm compute_run_outcome implements the design's Win definition exactly (avg confidence >= target AND no abandon AND contradiction_rate <= 0.3). Confirm apply_score increments correctly. Confirm find_demotion_targets uses W:L<0.4 AND uses>=5 with strict inequality."

**Code quality:**
"Edge cases: case dicts with missing confidence_per_topic, missing contradiction_rate, missing outcomes. Type narrowness on the outcome string ('W'|'L'). Test the ValueError path."

---

## Phase 6: Case Analyzer Wiring

**Goal:** Top-level `analyze()` function in `scripts/case_analyzer.py` that wires the heuristics + accumulator + score updates + (optional) Haiku semantic compare.

**Files touched:** `scripts/case_analyzer.py` (new), `tests/test_pattern_detection.py` (extension for analyzer integration).

---

### Task 6.1: AnalyzerResult dataclass + analyze() skeleton

**Files:**
- Create: `scripts/case_analyzer.py`
- Test: `tests/test_pattern_detection.py` (or new `tests/test_case_analyzer.py`)

**Step 1: Write failing test**

Create `tests/test_case_analyzer.py`:

```python
import json
from pathlib import Path
import pytest


def test_analyze_empty_state_returns_empty_result(tmp_path):
    """Empty accumulator + empty learned_patterns + no cases: zero candidates."""
    from case_analyzer import analyze
    case_path = tmp_path / "case.json"
    case_path.write_text(json.dumps({
        "case_id": "c1",
        "domain_tags": ["civic"],
        "applied_patterns": [],
        "confidence_per_topic": {"t": 0.8},
        "contradiction_rate": 0.1,
        "outcomes": {"user_decisions": []},
        "patterns_that_worked": {"source_tiers": {"T1": 5}, "hop_chain": ["entity_expansion"]},
    }))
    result = analyze(
        case_path=case_path,
        accumulator_path=tmp_path / "accumulator.json",
        learned_patterns_path=tmp_path / "learned_patterns.md",
        cases_dir=tmp_path,
        cases_window=20,
    )
    assert result.promotion_candidates == []
    assert result.warnings == []
```

**Step 2: Verify failure**

```
pytest tests/test_case_analyzer.py -v
```
Expected: FAIL.

**Step 3: Implement skeleton**

Create `scripts/case_analyzer.py`:

```python
"""Top-level case analyzer — wires heuristics + accumulator + scoring.

Runs at Stage 10b. See docs/plans/2026-05-27-v3-1-case-learning-design.md Section 6.1.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from accumulator import (
    Accumulator,
    AccumulatorEntry,
    load_accumulator,
    save_accumulator,
    record_observation,
    tick_staleness,
    mark_promotion_pending,
    demote,
)
from learned_patterns import (
    LearnedPatternsFile,
    load_learned_patterns,
    save_learned_patterns,
)
from pattern_detection import (
    detect_source_tier_dominance,
    detect_hop_pattern_lift,
    detect_query_template_recurrence,
)
from score_updates import (
    compute_run_outcome,
    apply_score,
    find_demotion_targets,
)


@dataclass
class AnalyzerResult:
    promotion_candidates: list[AccumulatorEntry] = field(default_factory=list)
    contradictions: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    score_updates_applied: int = 0
    demotions_applied: int = 0


def analyze(
    *,
    case_path: Path,
    accumulator_path: Path,
    learned_patterns_path: Path,
    cases_dir: Path,
    cases_window: int = 20,
    confidence_target: float = 0.75,
    promotion_threshold: int = 3,
    promotion_threshold_raised: int = 5,
    haiku_dispatch: Callable | None = None,
) -> AnalyzerResult:
    """Run the analyzer at Stage 10d.

    Returns AnalyzerResult listing promotion-eligible candidates and warnings.

    Side effects: updates accumulator.json and learned_patterns.md
    (atomic writes), BUT refuses to write either file if its load step
    produced a corruption or schema-mismatch warning. This prevents silently
    clobbering user-recoverable state with an empty file. The orchestrator
    surfaces the warning text so the user can manually delete the corrupt
    file when ready to reset that store.

    haiku_dispatch is an optional callable for semantic comparison. None means
    skip the semantic compare (conservative-distinct treatment).
    """
    result = AnalyzerResult()

    if not case_path.exists():
        result.warnings.append(f"case_path missing: {case_path}")
        return result

    case = json.loads(case_path.read_text(encoding="utf-8"))

    # Load state (both helpers return (data, warnings); warnings propagate to result)
    accumulator, acc_warnings = load_accumulator(accumulator_path)
    result.warnings.extend(acc_warnings)
    learned, lp_warnings = load_learned_patterns(learned_patterns_path)
    result.warnings.extend(lp_warnings)

    # 1. Score updates for applied_patterns
    outcome = compute_run_outcome(case, confidence_target=confidence_target)
    pattern_index = {p.id: p for p in learned.patterns}
    for pid in case.get("applied_patterns", []):
        if pid in pattern_index:
            apply_score(pattern_index[pid], outcome)
            result.score_updates_applied += 1

    # 2. Demotion sweep
    demotion_targets = find_demotion_targets(learned)
    for target in demotion_targets:
        # Reconstruction-or-update logic mirrors accumulator.demote() so the
        # 2nd-demotion → rejected rule still fires whether or not the
        # accumulator currently has an entry for this pattern_id.
        existing = next((e for e in accumulator.entries if e.pattern_id == target.id), None)
        new_demotion_count = target.demotion_count + 1
        if existing is None:
            # Pattern was promoted out and accumulator entry was removed.
            # Reconstruct it, applying the same status rules as accumulator.demote().
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            permanent = new_demotion_count >= 2
            accumulator.entries.append(AccumulatorEntry(
                pattern_id=target.id,
                name=target.name,
                category=target.category,  # preserved from LearnedPattern (added in Task 3.1)
                target_stage=target.target_stage,
                domain_tags=list(target.domain_tags),
                sessions_seen=0,
                sessions_since_last_seen=0,
                status=("rejected" if permanent else "hold"),
                raised_bar=(not permanent),  # only meaningful for re-graduation candidates
                promotion_pending=False,
                demotion_count=new_demotion_count,
                evidence=[],
                proposed_promotion_body=target.body,
                created_at=now,
                last_updated_at=now,
            ))
        else:
            # Accumulator entry exists — defer to the unified demote() helper
            # which already implements the 1st/2nd demotion rules correctly.
            demote(accumulator, target.id)
        # Remove from learned regardless of new status (rejected patterns live in accumulator)
        learned.patterns = [p for p in learned.patterns if p.id != target.id]
        result.demotions_applied += 1

    # 3. Candidate detection
    cases = _load_recent_cases(cases_dir, cases_window)
    if not cases:
        cases = [case]
    candidates = (
        detect_source_tier_dominance(cases)
        + detect_hop_pattern_lift(cases)
        + detect_query_template_recurrence(cases)
    )

    # 4. Record observations into accumulator (with optional Haiku semantic merge)
    seen_pattern_ids = set()
    for c in candidates:
        # Semantic merge: if accumulator has a similar entry (same category + same
        # domain tags) under a DIFFERENT pattern_id, dispatch Haiku to check
        # whether they describe the same underlying pattern. If so, reuse the
        # existing pattern_id so sessions_seen accumulates on the right entry
        # instead of fragmenting across near-duplicates.
        effective_pid = _match_or_create_pattern_id(c, accumulator, haiku_dispatch, result)
        for ev in c["evidence_rows"]:
            record_observation(
                accumulator,
                pattern_id=effective_pid,
                name=c["name"],
                category=c["category"],
                target_stage=c["target_stage"],
                domain_tags=c["domain_tags"],
                evidence_row=ev,
                proposed_promotion_body=c["proposed_promotion_body"],
            )
            break  # only one record_observation per candidate per run
        seen_pattern_ids.add(effective_pid)

    tick_staleness(accumulator, seen_pattern_ids)

    # 5. Promotion eligibility (+ contradiction detection)
    for entry in accumulator.entries:
        if entry.status != "hold":
            continue
        threshold = promotion_threshold_raised if entry.raised_bar else promotion_threshold
        if entry.sessions_seen >= threshold:
            # Contradiction check: any already-graduated patterns in the same
            # domain × target_stage bucket? If so, flag — the user resolves
            # at Stage 10e's graduation prompt by deciding promote/reject/hold.
            conflicts = [
                p for p in learned.patterns
                if p.target_stage == entry.target_stage
                and (set(p.domain_tags) & set(entry.domain_tags))
            ]
            if conflicts:
                result.contradictions.append({
                    "candidate_pattern_id": entry.pattern_id,
                    "candidate_name": entry.name,
                    "conflicting_graduated_ids": [p.id for p in conflicts],
                    "conflicting_names": [p.name for p in conflicts],
                })
            mark_promotion_pending(accumulator, entry.pattern_id)
            result.promotion_candidates.append(entry)

    # 6. Persist selectively — refuse to clobber files that loaded with warnings.
    #    Write order when both are written: learned_patterns FIRST, then accumulator
    #    (if the accumulator write fails after learned_patterns succeeded, the next
    #    run's analyzer dedupes via the in-learned_patterns check — no double-graduation;
    #    the reverse order would risk losing graduations).
    acc_corrupt = any(
        w.startswith("accumulator_corrupted") or w.startswith("accumulator_schema_mismatch")
        for w in result.warnings
    )
    lp_corrupt = any(
        w.startswith("learned_patterns_corrupted") or w.startswith("learned_patterns_schema_mismatch")
        for w in result.warnings
    )
    if not lp_corrupt:
        save_learned_patterns(learned_patterns_path, learned)
    if not acc_corrupt:
        save_accumulator(accumulator_path, accumulator)

    return result


def _load_recent_cases(cases_dir: Path, window: int) -> list[dict]:
    """Load up to `window` most recent case JSON files."""
    if not cases_dir.exists():
        return []
    case_files = sorted(cases_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for cf in case_files[:window]:
        try:
            out.append(json.loads(cf.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as e:
            # Tolerant — skip malformed cases
            print(f"[analyzer] skipping malformed case {cf.name}: {e}")
    return out


def _match_or_create_pattern_id(
    candidate: dict,
    accumulator: Accumulator,
    haiku_dispatch: Callable | None,
    result: "AnalyzerResult",
) -> str:
    """If an accumulator entry exists in the same (domain_tags, category)
    bucket under a different pattern_id and is not rejected, dispatch the
    Haiku semantic-compare subagent. On is_same=True, reuse the existing
    pattern_id so sessions_seen accumulates on the right entry. Otherwise
    return the candidate's own pattern_id.

    haiku_dispatch=None disables semantic merge entirely (conservative —
    fragments near-duplicates rather than risk wrong merge).
    """
    if haiku_dispatch is None:
        return candidate["pattern_id"]
    cand_tag_set = set(candidate["domain_tags"])
    for existing in accumulator.entries:
        if existing.pattern_id == candidate["pattern_id"]:
            continue  # same id is exact-match path, not semantic
        if existing.status == "rejected":
            continue  # never reuse rejected ids
        if existing.category != candidate["category"]:
            continue
        if set(existing.domain_tags) != cand_tag_set:
            continue
        try:
            verdict = haiku_dispatch(
                candidate_body=candidate["proposed_promotion_body"],
                existing_body=existing.proposed_promotion_body,
            )
        except Exception as e:
            # Conservative — on dispatch error, treat as distinct
            result.warnings.append(f"haiku_dispatch_error: {e}; treating candidate as distinct")
            continue
        if verdict.get("is_same"):
            return existing.pattern_id  # merge — use existing id
    return candidate["pattern_id"]
```

**Step 4: Verify pass**

```
pytest tests/test_case_analyzer.py::test_analyze_empty_state_returns_empty_result -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/case_analyzer.py tests/test_case_analyzer.py
git commit -m "feat(case_analyzer): top-level analyze() wiring heuristics + state"
```

---

### Task 6.2: Analyzer integration test with real fixtures

**Files:**
- Modify: `tests/test_case_analyzer.py`

**Step 1: Write failing test**

```python
def test_analyze_civic_alpr_cases_produces_promotion_candidates(tmp_path):
    """With 6+ civic_alpr cases, expect at least one promotion candidate to surface."""
    from case_analyzer import analyze
    import shutil

    fixture_path = Path("tests/fixtures/case_learning/civic_alpr_cases.json")
    cases = json.loads(fixture_path.read_text())
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    for i, c in enumerate(cases):
        (cases_dir / f"{c['case_id']}.json").write_text(json.dumps(c))

    # Drive 3 runs through the analyzer to build sessions_seen
    for i in range(3):
        result = analyze(
            case_path=cases_dir / f"{cases[i]['case_id']}.json",
            accumulator_path=tmp_path / "accumulator.json",
            learned_patterns_path=tmp_path / "learned_patterns.md",
            cases_dir=cases_dir,
            cases_window=20,
        )

    # After 3 runs, at least one civic-alpr candidate should be eligible
    assert len(result.promotion_candidates) >= 1
    civic = [c for c in result.promotion_candidates if "civic" in c.domain_tags]
    assert len(civic) >= 1
```

**Step 2: Verify failure**

```
pytest tests/test_case_analyzer.py -k civic_alpr -v
```
Expected: FAIL or PASS depending on fixture quality. Iterate fixtures until passing.

**Step 3: Tune fixture or analyzer thresholds if needed**

Adjust `civic_alpr_cases.json` so that the heuristics produce stable patterns across multiple runs. Confirm sessions_seen accumulates.

**Step 4: Verify pass**

```
pytest tests/test_case_analyzer.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_case_analyzer.py tests/fixtures/case_learning/civic_alpr_cases.json
git commit -m "test(analyzer): integration over civic_alpr fixture produces candidates"
```

---

### Task 6.2.1: Semantic-merge integration test

**Files:**
- Modify: `tests/test_case_analyzer.py`

Verifies the Haiku semantic-compare wires through analyze() correctly. Haiku is mocked at the dispatch boundary (no real subagent calls).

**Step 1: Write failing test**

```python
def test_semantic_merge_uses_existing_pattern_id_on_haiku_match(tmp_path):
    """When a heuristic candidate has the same (domain, category) as an
    existing accumulator entry but a different stable_key, and the Haiku
    semantic-compare returns is_same=True, the analyzer reuses the existing
    pattern_id so sessions_seen accumulates on the right entry."""
    from case_analyzer import analyze
    from accumulator import Accumulator, AccumulatorEntry, save_accumulator
    from datetime import datetime, timezone

    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    acc_path = tmp_path / "accumulator.json"
    lp_path = tmp_path / "learned_patterns.md"

    # Seed accumulator with a pre-existing entry in the civic-alpr / source-tier-bias
    # bucket under pattern_id "existing-pid"
    now = datetime.now(timezone.utc).isoformat()
    save_accumulator(acc_path, Accumulator(entries=[
        AccumulatorEntry(
            pattern_id="existing-pid", name="Existing T1 pattern", category="source-tier-bias",
            target_stage="search", domain_tags=["civic", "alpr"],
            sessions_seen=1, sessions_since_last_seen=0, status="hold",
            raised_bar=False, promotion_pending=False, demotion_count=0,
            evidence=[{"case_id": "c0", "signal": "T1=5/8"}],
            proposed_promotion_body="T1 dominance for civic ALPR", created_at=now,
            last_updated_at=now,
        ),
    ]))

    # Synthesize a case that will produce a "T1 dominant for civic/alpr" candidate
    # under a different generated pattern_id
    case = {
        "case_id": "c1", "domain_tags": ["civic", "alpr"], "applied_patterns": [],
        "confidence_per_topic": {"t": 0.82}, "contradiction_rate": 0.1,
        "outcomes": {"user_decisions": []},
        "patterns_that_worked": {
            "source_tiers": {"T1": 8, "T2": 1}, "hop_chain": ["entity_expansion"],
            "queries": [],
        },
    }
    case_path = cases_dir / "c1.json"
    case_path.write_text(json.dumps(case))

    # Haiku mock returns is_same=True for any compare
    def fake_haiku(*, candidate_body, existing_body):
        return {"is_same": True, "reason": "mock match"}

    result = analyze(
        case_path=case_path,
        accumulator_path=acc_path,
        learned_patterns_path=lp_path,
        cases_dir=cases_dir,
        haiku_dispatch=fake_haiku,
    )

    # Reload accumulator and verify the new evidence merged onto "existing-pid",
    # not a fresh pattern_id
    from accumulator import load_accumulator
    acc, _ = load_accumulator(acc_path)
    existing = next(e for e in acc.entries if e.pattern_id == "existing-pid")
    assert existing.sessions_seen >= 2, "existing-pid should have accumulated"


def test_semantic_merge_disabled_when_haiku_none(tmp_path):
    """When haiku_dispatch is None, no semantic merge occurs — heuristic
    candidates always use their own pattern_id (conservative default)."""
    from case_analyzer import analyze
    # ... (same scaffolding as above, but analyze() called with haiku_dispatch=None)
    # Assert: the new candidate created a separate accumulator entry, not merged.
```

**Step 2-5: verify/iterate/commit**

```bash
git add tests/test_case_analyzer.py
git commit -m "test(analyzer): semantic-merge integration (Haiku is_same → reuse pattern_id)"
```

---

### Task 6.2.2: Contradiction-detection integration test

**Files:**
- Modify: `tests/test_case_analyzer.py`

**Step 1: Write failing test**

```python
def test_contradiction_flagged_at_promotion_time(tmp_path):
    """When an accumulator entry becomes promotion-eligible and the same
    (domain, target_stage) bucket already has a graduated pattern in
    learned_patterns.md, the analyzer flags it in result.contradictions."""
    from case_analyzer import analyze
    from accumulator import Accumulator, AccumulatorEntry, save_accumulator
    from learned_patterns import LearnedPatternsFile, LearnedPattern, save_learned_patterns
    from datetime import datetime, timezone

    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    acc_path = tmp_path / "accumulator.json"
    lp_path = tmp_path / "learned_patterns.md"
    now = datetime.now(timezone.utc).isoformat()

    # Seed a graduated pattern in learned_patterns.md
    save_learned_patterns(lp_path, LearnedPatternsFile(patterns=[
        LearnedPattern(
            id="graduated-pid", name="Use broad queries for tech",
            body="Broad queries outperform narrow.", domain_tags=["tech"],
            target_stage="search", category="query-template",
            wins=8, losses=1, promoted_at="2026-04-01", demotion_count=0,
        ),
    ]))

    # Seed an accumulator entry already at promotion threshold for the same bucket
    save_accumulator(acc_path, Accumulator(entries=[
        AccumulatorEntry(
            pattern_id="candidate-pid", name="Use narrow queries for tech",
            category="query-template", target_stage="search",
            domain_tags=["tech"], sessions_seen=3, sessions_since_last_seen=0,
            status="hold", raised_bar=False, promotion_pending=False, demotion_count=0,
            evidence=[{"case_id": "c0", "signal": "narrow=5/6"}],
            proposed_promotion_body="Narrow queries outperform broad.",
            created_at=now, last_updated_at=now,
        ),
    ]))

    # Drive analyze() — does NOT need to produce new candidates; we just need
    # the existing accumulator entry to hit the promotion-eligibility check.
    case = {
        "case_id": "c1", "domain_tags": ["tech"], "applied_patterns": [],
        "confidence_per_topic": {"t": 0.8}, "contradiction_rate": 0.1,
        "outcomes": {"user_decisions": []},
        "patterns_that_worked": {"source_tiers": {}, "hop_chain": [], "queries": []},
    }
    (cases_dir / "c1.json").write_text(json.dumps(case))
    result = analyze(
        case_path=cases_dir / "c1.json",
        accumulator_path=acc_path,
        learned_patterns_path=lp_path,
        cases_dir=cases_dir,
    )

    assert len(result.promotion_candidates) == 1
    assert result.promotion_candidates[0].pattern_id == "candidate-pid"
    assert len(result.contradictions) == 1
    contradiction = result.contradictions[0]
    assert contradiction["candidate_pattern_id"] == "candidate-pid"
    assert "graduated-pid" in contradiction["conflicting_graduated_ids"]
```

**Step 2-5: verify/iterate/commit**

```bash
git add tests/test_case_analyzer.py
git commit -m "test(analyzer): contradiction detection at promotion time"
```

---

### Task 6.3: Phase 6 review

Spec + code-quality.

**Spec review:**
"Verify analyze() matches design Section 4 (Data flow) — score updates → demotion sweep → candidate detection → accumulator updates → promotion eligibility → atomic save."

**Code quality:**
"Review the wiring: any state path that doesn't get persisted on crash? Confirm the save order is learned_patterns FIRST then accumulator per design Section 7 — the task ships this order already; flag any regression."

---

## Phase 7: Haiku Semantic-Compare Subagent

**Goal:** Create `agents/case-analyzer.md` for the bounded semantic-compare role + contract test.

**Files touched:** `agents/case-analyzer.md` (new), `tests/test_case_analyzer_contract.py` (new).

---

### Task 7.1: Write `agents/case-analyzer.md`

**Files:**
- Create: `agents/case-analyzer.md`

**Step 1: Write the agent definition**

```markdown
---
name: case-analyzer
description: Compares two candidate-pattern observations and returns whether they represent the same underlying pattern. Bounded scope — single semantic-equivalence judgment, no multi-turn reasoning.
---

# Case Analyzer (Semantic Compare)

You are a bounded semantic-equivalence judge. The orchestrator gives you two pattern observation bodies and asks: are these the *same* underlying pattern, expressed slightly differently?

## Inputs

You will receive two text blocks labeled `CANDIDATE` and `EXISTING`. Each is 1-3 sentences describing an observed pattern from research-pipeline cases.

## Task

Decide: do these refer to the same underlying pattern?

- **Same** = both refer to the same domain-specific bias (same source-tier preference, same hop pattern, same query template family) even if the wording differs.
- **Distinct** = the patterns describe different observations, even if they share a domain.

## Output

Respond with valid JSON only — no prose around it:

```json
{
  "is_same": true,
  "reason": "Both describe T1 source dominance for civic ALPR queries — same domain, same tier, same direction."
}
```

or

```json
{
  "is_same": false,
  "reason": "CANDIDATE describes query-template recurrence; EXISTING describes source-tier dominance — different observation categories."
}
```

## Guardrails

- Be conservative. When in doubt, return `is_same: false`. Accidentally treating two distinct patterns as the same merges them in the accumulator, which loses signal. Treating same patterns as distinct just creates two entries — annoying but recoverable.
- No multi-turn reasoning. One JSON response per dispatch.
- Reason must be one sentence, factual.
```

**Step 2: Commit**

```bash
git add agents/case-analyzer.md
git commit -m "feat(agents): add case-analyzer for semantic pattern compare"
```

---

### Task 7.2: Contract test for case-analyzer dispatch shape

**Files:**
- Create: `tests/test_case_analyzer_contract.py`

The contract test verifies that the orchestrator's expected request → response shape is honored. Mocked at the Bash layer — no real Haiku call.

**Step 1: Write failing test**

```python
import json
import subprocess
from unittest.mock import patch


def test_haiku_dispatch_request_shape():
    """When orchestrator dispatches case-analyzer, the request payload includes
    both CANDIDATE and EXISTING blocks."""
    # This is a contract assertion against the orchestrator's prompt-assembly,
    # not against the Haiku model itself. We mock subprocess.run.
    captured_prompt = {}

    def fake_run(*args, **kwargs):
        # Capture the prompt text from the args
        if "input" in kwargs:
            captured_prompt["prompt"] = kwargs["input"]
        class R:
            returncode = 0
            stdout = json.dumps({"is_same": False, "reason": "mock"})
            stderr = ""
        return R()

    from case_analyzer import dispatch_semantic_compare
    with patch("subprocess.run", side_effect=fake_run):
        result = dispatch_semantic_compare(
            candidate_body="T1 sources dominate for civic ALPR queries.",
            existing_body="Government sites win out for civic ALPR research.",
            timeout_s=5,
        )
    assert "CANDIDATE" in captured_prompt["prompt"]
    assert "EXISTING" in captured_prompt["prompt"]
    assert result["is_same"] is False


def test_haiku_dispatch_timeout_returns_conservative_distinct():
    """On timeout, dispatch_semantic_compare returns is_same=False with a warning."""
    from case_analyzer import dispatch_semantic_compare
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=5)
    with patch("subprocess.run", side_effect=fake_run):
        result = dispatch_semantic_compare(
            candidate_body="x",
            existing_body="y",
            timeout_s=5,
        )
    assert result["is_same"] is False
    assert "timeout" in result.get("reason", "").lower()
```

**Step 2: Verify failure**

```
pytest tests/test_case_analyzer_contract.py -v
```
Expected: FAIL.

**Step 3: Add `dispatch_semantic_compare` to case_analyzer.py**

```python
import subprocess


def dispatch_semantic_compare(
    *,
    candidate_body: str,
    existing_body: str,
    timeout_s: float = 30.0,
) -> dict:
    """Dispatch the case-analyzer Haiku subagent for semantic comparison.

    Returns {"is_same": bool, "reason": str}. On timeout, returns conservative
    {"is_same": false, "reason": "timeout — treating as distinct"}.
    """
    prompt = (
        "CANDIDATE\n"
        f"{candidate_body}\n\n"
        "EXISTING\n"
        f"{existing_body}\n"
    )
    try:
        # NOTE: actual Haiku dispatch is via the orchestrator's Task tool at runtime;
        # this helper is here for contract testing. In production the orchestrator
        # constructs the Task tool dispatch directly. This subprocess.run wrapper
        # exists only so the contract test can mock it.
        proc = subprocess.run(
            ["claude", "task", "--agent", "case-analyzer"],  # illustrative; not actually run
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return json.loads(proc.stdout)
    except subprocess.TimeoutExpired:
        return {"is_same": False, "reason": "timeout — treating as distinct"}
    except (json.JSONDecodeError, FileNotFoundError) as e:
        return {"is_same": False, "reason": f"dispatch error: {e}"}
```

**Note:** in production, the orchestrator dispatches the case-analyzer agent via the Task tool from inside `SKILL.md` Stage 10b, not via this Python helper. The helper exists for contract testing. The orchestrator's actual dispatch uses Claude Code's Task tool, which is the convention for all other subagent dispatches in this plugin.

**Step 4: Verify pass**

```
pytest tests/test_case_analyzer_contract.py -v
```
Expected: PASS (2 tests).

**Step 5: Commit**

```bash
git add tests/test_case_analyzer_contract.py scripts/case_analyzer.py
git commit -m "test(case_analyzer): contract test for semantic-compare dispatch shape"
```

---

## Phase 8: Orchestrator Extensions in SKILL.md

**Goal:** Extend `skills/research/SKILL.md` with Stage 2 load, Stage 4a/4e/6 injection, Stage 10b analyzer dispatch, Stage 10c graduation prompt.

**Files touched:** `skills/research/SKILL.md`.

These changes are documentation/protocol changes (the orchestrator runs SKILL.md as its prompt). Each task is a contained edit + a test confirming the orchestrator's Bash invocations match the expected shape.

---

### Task 8.1: Stage 2 — load and filter learned_patterns

**Step 1: Add a new sub-stage Stage 2d to `skills/research/SKILL.md`**

Insert after Stage 2c (existing triage output handling). Use exact existing SKILL.md style and constants (`{{VAULT_ROOT}}`, etc.).

```markdown
### 2d. Load learned patterns (v3.1.0)

Run via Bash:
```bash
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from learned_patterns import load_learned_patterns, filter_by_topic_text, group_by_stage
from pathlib import Path
lp, _warnings = load_learned_patterns(Path('LEARNED_PATTERNS_PATH'))
relevant = filter_by_topic_text(lp, topics=TOPIC_STRINGS)
grouped = group_by_stage(relevant)
print(json.dumps({stage: [p.id for p in patterns] for stage, patterns in grouped.items()}))
"
```

Substitute `LEARNED_PATTERNS_PATH` with `{VAULT}/.research-workflow/learned_patterns.md`. Substitute `TOPIC_STRINGS` with the list of topic strings from the resolver output (Stage 3's `final['topics']` — use each topic's `topic` field).

**Why topic-text matching, not `domain_tags` matching at this stage:** v3.0.0 only derives `domain_tags` at case-write time (Stage 10), computed from tags assigned to written notes. At Stage 2 no notes exist yet. Topic strings are the strongest signal we have for relevance. Stage 10b's analyzer uses real `domain_tags` from the just-written case via `filter_relevant`.

**Known limitation of substring-only matching:** patterns tagged with high-level concepts that don't appear verbatim in topic text (e.g., a pattern tagged `["civic"]` from a prior run won't match the topic `"ALPR programs in Greenville"` because "civic" isn't in the topic string). This is intentional for v3.1.0 — broader semantic matching would require an additional classification step at Stage 2 (cost we don't want to pay yet). The user benefits less from learned patterns early in a run but gets full credit at Stage 10b scoring once `domain_tags` are derived from written notes. Revisit for v3.2.0 if real usage shows this is too lossy.

Parse the JSON output and store:
- `LEARNED_BY_STAGE` = the returned dict mapping `search` / `hop_planner` / `classify` → list of pattern IDs

If the file doesn't exist or returns empty, set `LEARNED_BY_STAGE = {"search": [], "hop_planner": [], "classify": []}`. Continue silently.
```

**Step 2: Commit**

```bash
git add skills/research/SKILL.md
git commit -m "feat(skill): Stage 2d loads learned_patterns and groups by stage"
```

---

### Task 8.2: Stage 4a — inject learned patterns into search-agent dispatch

**Step 1: Add Stage 4a learned-patterns injection**

In `skills/research/SKILL.md` at Stage 4a (search dispatch), augment the search-agent dispatch prompt assembly:

```markdown
**Build the search-agent dispatch prompt:**

(existing dispatch body)

If `LEARNED_BY_STAGE["search"]` is non-empty, ALSO load each pattern's full
record and append to the search-agent prompt:

```bash
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from learned_patterns import load_learned_patterns
from pathlib import Path
lp, _warnings = load_learned_patterns(Path('LEARNED_PATTERNS_PATH'))
ids = LEARNED_IDS_FOR_STAGE
out = [{'id': p.id, 'name': p.name, 'body': p.body} for p in lp.patterns if p.id in ids]
print(json.dumps(out))
"
```

Build a `## Learned Patterns` block from the returned records:

```markdown
## Learned Patterns (from prior runs, may or may not apply)

- **{name}** — {body}

(repeat per pattern)
```

Append this block to the search-agent's user prompt under the existing
context. Then, for each pattern surfaced, record it in run state:

```bash
python -c "
import sys; sys.path.insert(0, 'SCRIPTS')
from state import record_applied_pattern
from pathlib import Path
record_applied_pattern(Path('STATE_DIR'), 'PATTERN_ID')
"
```

(Run once per pattern id.)
```

**Step 2: Commit**

```bash
git add skills/research/SKILL.md
git commit -m "feat(skill): Stage 4a injects learned patterns into search-agent dispatch"
```

---

### Task 8.3: Stage 4e + Stage 6 injections (hop-planner + classify)

Same pattern as Task 8.2, applied to Stage 4e (hop-planner dispatch) and Stage 6 (classify dispatch). Use `LEARNED_BY_STAGE["hop_planner"]` and `LEARNED_BY_STAGE["classify"]` respectively.

**Step 1: Add the two injection blocks**

(See task 8.2 for the template; apply per stage.)

**Step 2: Commit**

```bash
git add skills/research/SKILL.md
git commit -m "feat(skill): Stage 4e + Stage 6 inject learned patterns into dispatches"
```

---

### Task 8.4: Stage 10d — dispatch analyzer

**Important: this stage runs AFTER existing Stage 10c (write_case_record).** v3.0.0 already uses Stage 10b (print summary) and 10c (write case record). The analyzer needs the case JSON to exist, so it can only run after 10c. Use stage label `10d` for the analyzer and `10e` for the graduation prompt — do NOT collide with existing 10b/10c.

**Step 1: Insert Stage 10d in SKILL.md**

After existing Stage 10c (`write_case_record`), before any final completion logging:

```markdown
### 10d. Run case analyzer (v3.1.0)

Run via Bash:
```bash
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from case_analyzer import analyze, AnalyzerResult
from pathlib import Path
from state import acquire_state_lock

with acquire_state_lock(Path('STATE_ROOT_FOR_VAULT')):
    result = analyze(
        case_path=Path('CASE_PATH'),
        accumulator_path=Path('ACCUMULATOR_PATH'),
        learned_patterns_path=Path('LEARNED_PATTERNS_PATH'),
        cases_dir=Path('CASES_DIR'),
    )
print(json.dumps({
    'promotion_candidates': [
        {'pattern_id': c.pattern_id, 'name': c.name,
         'proposed_promotion_body': c.proposed_promotion_body,
         'evidence': c.evidence}
        for c in result.promotion_candidates
    ],
    'contradictions': result.contradictions,
    'warnings': result.warnings,
    'score_updates_applied': result.score_updates_applied,
    'demotions_applied': result.demotions_applied,
}))
"
```

Parse the JSON output.

**Corruption handling (v3.1.0 policy: no automatic recovery, no rebuild UX).**

`analyze()` itself protects state files: if `accumulator.json` or `learned_patterns.md` could not be parsed (or had a schema-version mismatch), the analyzer **does not write back to that file**. So a corrupt file stays as-is on disk — the user can inspect or recover it. The trade-off is that any in-memory updates (score increments, new candidates, demotion sweep results) that would have touched the corrupted store are discarded for this run.

If `warnings` contains any of these markers:
- `accumulator_corrupted: ...`
- `accumulator_schema_mismatch: ...`
- `learned_patterns_corrupted: ...`
- `learned_patterns_schema_mismatch: ...`

Surface them to the user at Stage 10d output (these flow through to Stage 10's completion summary anyway via state telemetry), with a clear advisory:

```
⚠️  v3.1.0 pattern learning state was not updated this run:
  {warning text(s) from analyzer}

To reset the affected store, delete the file manually:
  {VAULT}/.research-workflow/accumulator.json
  {VAULT}/.research-workflow/learned_patterns.md
The next /research run will start with an empty store and rebuild from
new cases going forward. Existing case history at
{VAULT}/.research-workflow/cases/ is unaffected.
```

(There is no in-pipeline rebuild flow in v3.1.0. Corrupt-state recovery is rare; the simpler "user deletes file → fresh start" path was preferred over carrying the complexity of a rebuild-from-history mechanism. Revisit in v3.1.x if real usage shows this is too coarse.)

**Stage 10e gating.** If any `learned_patterns_*` warning is present, **skip Stage 10e entirely for this run** — even if `promotion_candidates` is non-empty. Stage 10e's promote path would otherwise be unable to write the graduated pattern (analyzer refused the write). Log: "Skipping graduation prompts — learned_patterns.md needs manual repair first."

**Normal flow after warnings handling.**

If `promotion_candidates` is non-empty AND no `learned_patterns_*` warnings, proceed to Stage 10e. Otherwise skip 10e.

If the analyzer fails entirely (script exits non-zero or LockTimeoutError raised), log to state telemetry and continue silently. The run still completes; the analyzer just didn't update state this round.
```

**Step 2: Commit**

```bash
git add skills/research/SKILL.md
git commit -m "feat(skill): Stage 10b dispatches case analyzer with state lock"
```

---

### Task 8.5: Stage 10e — graduation prompt loop

**Step 1: Insert Stage 10e**

```markdown
### 10e. Graduation prompt (v3.1.0, conditional on Stage 10d output)

For each entry in `promotion_candidates`:

Look up any matching entries in `contradictions` (where `candidate_pattern_id == entry.pattern_id`). If present, include a `⚠️ Possible contradiction` block in the prompt so the user can weigh whether the new pattern conflicts with an existing graduated one.

Show the user:

```
Learned pattern ready for promotion:

  Name: {name}
  Proposed body: {proposed_promotion_body}

  Evidence:
  {for each row in evidence:}
    - case {case_id}: {signal}
  {end}

  {if contradictions for this entry:}
  ⚠️  Possible contradiction with already-graduated patterns
      in the same domain × stage:
  {for each conflicting_name:}
    - {conflicting_name} (id: {conflicting_id})
  {end}
  Promoting both keeps them side-by-side and lets the scoring loop
  sort it out. Rejecting this new pattern preserves the existing rule.
  {end}

Promote / Reject / Hold?
```

Use the user's response:

All three branches below acquire `acquire_state_lock` around the shared-state writes. This is the same lock Stage 10d uses — without it, concurrent `/research` runs (background + foreground) could race on `accumulator.json` and `learned_patterns.md` and lose updates. `STATE_ROOT_FOR_VAULT` is `{VAULT}/.research-workflow/`.

**Precondition for the Promote branch:** Stage 10d already verified that `learned_patterns.md` is parseable (no `learned_patterns_corrupted` / `learned_patterns_schema_mismatch` warnings) BEFORE letting control reach Stage 10e. If those warnings were present, Stage 10d skipped 10e entirely. So inside the Promote branch we can assume `load_learned_patterns()` returns a usable file — but the snippet below still defends against late corruption by checking warnings before saving.

**Promote:**

```bash
python -c "
import sys; sys.path.insert(0, 'SCRIPTS')
from accumulator import load_accumulator, save_accumulator, remove_entry
from learned_patterns import (
    load_learned_patterns, save_learned_patterns, LearnedPattern
)
from datetime import datetime, timezone
from pathlib import Path
from state import acquire_state_lock

with acquire_state_lock(Path('STATE_ROOT_FOR_VAULT')):
    lp, lp_warnings = load_learned_patterns(Path('LEARNED_PATTERNS_PATH'))
    if lp_warnings:
        # Refuse to clobber a corrupt/incompatible file even if Stage 10d
        # missed the gate (defense in depth). Log and bail.
        import sys as _sys
        print(f'PROMOTE_ABORTED: refusing to save over corrupt learned_patterns.md: {lp_warnings}', file=_sys.stderr)
        _sys.exit(0)
    acc, _ = load_accumulator(Path('ACCUMULATOR_PATH'))
    entry = next(e for e in acc.entries if e.pattern_id == 'PATTERN_ID')
    # Skip if already in learned_patterns (cross-file transaction recovery —
    # prior promotion wrote learned_patterns but failed to update accumulator)
    if not any(p.id == entry.pattern_id for p in lp.patterns):
        lp.patterns.append(LearnedPattern(
            id=entry.pattern_id,
            name=entry.name,
            body=entry.proposed_promotion_body,
            domain_tags=entry.domain_tags,
            target_stage=entry.target_stage,
            category=entry.category,  # preserve for later demotion (Task 3.1 added this field)
            wins=0, losses=0,
            promoted_at=datetime.now(timezone.utc).strftime('%Y-%m-%d'),
            demotion_count=entry.demotion_count,
        ))
        # Write order: learned_patterns FIRST, then accumulator
        save_learned_patterns(Path('LEARNED_PATTERNS_PATH'), lp)
    remove_entry(acc, 'PATTERN_ID')
    save_accumulator(Path('ACCUMULATOR_PATH'), acc)
"
```

**Reject:**

```bash
python -c "
import sys; sys.path.insert(0, 'SCRIPTS')
from accumulator import load_accumulator, save_accumulator, mark_rejected
from pathlib import Path
from state import acquire_state_lock

with acquire_state_lock(Path('STATE_ROOT_FOR_VAULT')):
    acc, _warnings = load_accumulator(Path('ACCUMULATOR_PATH'))
    mark_rejected(acc, 'PATTERN_ID')
    save_accumulator(Path('ACCUMULATOR_PATH'), acc)
"
```

**Hold:**

```bash
python -c "
import sys; sys.path.insert(0, 'SCRIPTS')
from accumulator import load_accumulator, save_accumulator, clear_promotion_pending
from pathlib import Path
from state import acquire_state_lock

with acquire_state_lock(Path('STATE_ROOT_FOR_VAULT')):
    acc, _warnings = load_accumulator(Path('ACCUMULATOR_PATH'))
    clear_promotion_pending(acc, 'PATTERN_ID')
    save_accumulator(Path('ACCUMULATOR_PATH'), acc)
"
```

If the user aborts (Ctrl+C, dismisses, walks away), do nothing. The `promotion_pending` flag remains set on the accumulator entry, and next-run Stage 10c will re-prompt.
```

**Step 2: Commit**

```bash
git add skills/research/SKILL.md
git commit -m "feat(skill): Stage 10c graduation prompt loop (promote/reject/hold)"
```

---

### Task 8.6: Phase 8 review

Spec + code-quality review over Phase 8's 5 commits.

**Spec review:**
"Confirm Stage 2d / 4a / 4e / 6 / 10b / 10c match design Section 4 (Data flow) exactly. Stage 10c write order is learned_patterns first, accumulator second."

**Code quality:**
"Verify SKILL.md Bash invocations are escaping correctly (no unquoted paths with spaces). State lock is acquired around the analyzer call. Graduation prompt handles abort gracefully without corrupting state."

---

## Phase 9: Multi-Run Trajectory Integration Test

**Goal:** The high-value test — drive the analyzer through N synthesized runs and verify the full state machine lifecycle.

**Files touched:** `tests/test_pattern_evolution.py` (new), `tests/test_research_state_mechanics.py` (extension).

---

### Task 9.1: Multi-run trajectory test

**Files:**
- Create: `tests/test_pattern_evolution.py`

**Step 1: Write the test**

This is the big one. The test drives 24+ synthesized runs in sequence and asserts the expected pattern lifecycle at each milestone.

```python
"""Multi-run trajectory test for v3.1.0 case-based pattern learning.

Drives the analyzer through a sequence of synthesized cases and verifies
the full state machine: hold → promotion eligible → graduated → demoted →
re-graduated → permanently rejected.
"""

import json
from pathlib import Path
import pytest


def _make_case(case_id: str, domain_tags: list[str], **overrides) -> dict:
    """Build a synthesized case dict."""
    base = {
        "case_id": case_id,
        "version": 1,
        "domain_tags": domain_tags,
        "applied_patterns": [],
        "confidence_per_topic": {"t1": 0.82},
        "contradiction_rate": 0.1,
        "outcomes": {"user_decisions": []},
        "depths_used": {"standard": 1},
        "hops_executed": 2,
        "patterns_that_worked": {
            "source_tiers": {"T1": 8, "T2": 3, "T3": 1, "T4": 0},
            "hop_chain": ["entity_expansion", "causal_chain"],
            "queries": ["Greenville ALPR 2025", "Spartanburg ALPR 2024"],
        },
        "patterns_that_failed": {},
    }
    base.update(overrides)
    return base


def test_full_lifecycle_civic_alpr(tmp_path):
    """Drive 25+ synthesized civic-alpr runs and verify the full lifecycle."""
    from case_analyzer import analyze

    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    acc_path = tmp_path / "accumulator.json"
    lp_path = tmp_path / "learned_patterns.md"

    def run_analyzer(case: dict) -> "AnalyzerResult":
        case_path = cases_dir / f"{case['case_id']}.json"
        case_path.write_text(json.dumps(case))
        return analyze(
            case_path=case_path,
            accumulator_path=acc_path,
            learned_patterns_path=lp_path,
            cases_dir=cases_dir,
        )

    # Runs 1-2: observation accumulates, no candidates yet
    for i in range(1, 3):
        result = run_analyzer(_make_case(f"r{i}", ["civic", "alpr"]))
    # Promotion threshold is 3 — Run 3 should produce a candidate
    result = run_analyzer(_make_case("r3", ["civic", "alpr"]))
    assert len(result.promotion_candidates) >= 1, \
        "after 3 runs of consistent civic-alpr T1 dominance, a candidate should be eligible"
    civic_pid = next(c.pattern_id for c in result.promotion_candidates
                     if "civic" in c.domain_tags)

    # Simulate user promoting
    from accumulator import load_accumulator, save_accumulator, remove_entry
    from learned_patterns import (
        load_learned_patterns, save_learned_patterns, LearnedPattern
    )
    from datetime import datetime, timezone
    acc, _ = load_accumulator(acc_path)
    lp, _ = load_learned_patterns(lp_path)
    entry = next(e for e in acc.entries if e.pattern_id == civic_pid)
    lp.patterns.append(LearnedPattern(
        id=entry.pattern_id, name=entry.name, body=entry.proposed_promotion_body,
        domain_tags=entry.domain_tags, target_stage=entry.target_stage,
        category=entry.category,
        wins=0, losses=0,
        promoted_at=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        demotion_count=entry.demotion_count,
    ))
    save_learned_patterns(lp_path, lp)
    remove_entry(acc, civic_pid)
    save_accumulator(acc_path, acc)

    # Runs 4-7: pattern earns wins
    for i in range(4, 8):
        case = _make_case(f"r{i}", ["civic", "alpr"], applied_patterns=[civic_pid])
        result = run_analyzer(case)
    lp, _ = load_learned_patterns(lp_path)
    pattern = next(p for p in lp.patterns if p.id == civic_pid)
    assert pattern.wins >= 4, f"expected >=4 wins after runs 4-7, got {pattern.wins}"

    # Runs 8-12: pattern earns losses (cases with bad confidence)
    for i in range(8, 13):
        case = _make_case(f"r{i}", ["civic", "alpr"],
                          applied_patterns=[civic_pid],
                          confidence_per_topic={"t1": 0.4})
        result = run_analyzer(case)
    lp, _ = load_learned_patterns(lp_path)
    pattern_in_lp = [p for p in lp.patterns if p.id == civic_pid]
    if pattern_in_lp:
        # ratio: 4 W / (4+5) = 0.44; not yet demoted (threshold is < 0.4)
        assert pattern_in_lp[0].losses >= 5

    # Run 13: one more loss should push ratio below 0.4
    case = _make_case("r13", ["civic", "alpr"],
                      applied_patterns=[civic_pid],
                      confidence_per_topic={"t1": 0.4})
    result = run_analyzer(case)
    assert result.demotions_applied >= 1

    # Verify pattern moved back to accumulator with raised_bar=True
    acc, _ = load_accumulator(acc_path)
    pattern_in_acc = next((e for e in acc.entries if e.pattern_id == civic_pid), None)
    assert pattern_in_acc is not None, "demoted pattern should be in accumulator"
    assert pattern_in_acc.raised_bar is True
    assert pattern_in_acc.demotion_count == 1
```

**Step 2: Verify failure → iterate**

```
pytest tests/test_pattern_evolution.py -v
```
Expected: likely fails on first try due to subtle threshold issues. Iterate fixture cases / thresholds.

**Step 3: Get to GREEN**

Tune until test passes.

**Step 4: Commit**

```bash
git add tests/test_pattern_evolution.py
git commit -m "test: multi-run trajectory test for v3.1.0 pattern lifecycle"
```

---

### Task 9.2: Re-graduation + permanent retirement extension

**Step 1: Extend the trajectory test**

Add to `test_pattern_evolution.py`:

```python
def test_re_graduation_and_permanent_retirement(tmp_path):
    """After first demotion, pattern needs 5 sessions_seen (not 3) to re-graduate.
    After second demotion, status flips to rejected permanently."""
    # ... extended trajectory similar to test_full_lifecycle_civic_alpr,
    # continuing past Run 13 to Run ~25:
    # - Runs 14-18: pattern observed 5x → re-graduates under raised bar
    # - Runs 19-23: pattern earns losses
    # - Run 24: 2nd demotion → status=rejected
    # - Run 25: observation recurs, verify NOT re-proposed (rejected sticky)
```

(Full body left to the implementer — uses the same pattern as 9.1.)

**Step 2: Commit**

```bash
git add tests/test_pattern_evolution.py
git commit -m "test: re-graduation with raised bar + permanent retirement"
```

---

## Phase 10: Backward-Compat + Final Verification

---

### Task 10.1: Empty-state backward-compat test

**Files:**
- Create or extend: `tests/test_v3_compat.py`

**Step 1: Write test**

```python
def test_pipeline_with_empty_accumulator_runs_like_v3_0_0(tmp_path):
    """With no accumulator, no learned_patterns, no cases, pipeline behaves
    identically to v3.0.0 (analyzer silent, no graduation prompt)."""
    from case_analyzer import analyze
    case_path = tmp_path / "fresh-case.json"
    case_path.write_text(json.dumps({
        "case_id": "fresh",
        "domain_tags": ["civic"],
        "applied_patterns": [],
        "confidence_per_topic": {"t1": 0.82},
        "contradiction_rate": 0.1,
        "outcomes": {"user_decisions": []},
        "patterns_that_worked": {
            "source_tiers": {"T1": 1},
            "hop_chain": ["entity_expansion"],
            "queries": [],
        },
    }))
    result = analyze(
        case_path=case_path,
        accumulator_path=tmp_path / "missing-acc.json",
        learned_patterns_path=tmp_path / "missing-lp.md",
        cases_dir=tmp_path,
    )
    assert result.promotion_candidates == []
    assert result.score_updates_applied == 0
    assert result.demotions_applied == 0
```

**Step 2-5: Verify, implement only if needed, commit**

```
pytest tests/test_v3_compat.py -v
```
Expected: PASS (analyzer already handles empty state from Task 6.1).

```bash
git add tests/test_v3_compat.py
git commit -m "test: backward-compat — empty state behaves like v3.0.0"
```

---

### Task 10.2: Run full test suite + verify zero regression

```
pytest tests/ -v --tb=short
```

Expected: ALL tests pass (308 from v3.0.0 + new v3.1.0 tests). Zero regressions.

If any v3.0.0 test regresses, debug before continuing.

**Commit (if any fix commits needed):**

```bash
git add <files>
git commit -m "fix: <issue> from full-suite verification"
```

---

### Task 10.3: Update version + MANIFEST + CLAUDE.md + final review

**Step 1: Bump version**

Edit `.claude-plugin/plugin.json`:
```json
{ "version": "3.1.0", ... }
```

**Step 2: Update MANIFEST.md**

Add the new files (`scripts/accumulator.py`, `scripts/learned_patterns.py`, `scripts/pattern_detection.py`, `scripts/score_updates.py`, `scripts/case_analyzer.py`, `agents/case-analyzer.md`, `tests/fixtures/case_learning/`) to the structure section. Note the relationships in Key Relationships section.

**Step 3: Update CLAUDE.md**

In the project's `CLAUDE.md`, add a paragraph under Architecture noting that v3.1.0 introduces case-based pattern learning via the `learned_patterns.md` + accumulator pair.

**Step 4: Final spec + code-quality review**

Spec reviewer: "Verify all design sections (1-11) have implementation evidence in the branch. Confirm no design decisions were skipped."

Code quality reviewer: "Final pass over the v3.1.0 surface. Check: atomic write coverage, lock acquisition coverage, error handling consistency, test coverage on the new modules >= 90% line coverage."

**Step 5: Commit**

```bash
git add .claude-plugin/plugin.json MANIFEST.md CLAUDE.md
git commit -m "chore: bump version to 3.1.0 + update MANIFEST/CLAUDE for case learning"
```

---

## After All Phases Complete

**Codex impl-review (capped 4-5 rounds):**

Per Tim's preference, run `cross-model-review:codex-impl-review` against the full v3.1.0 diff. Capped at 4-5 rounds. Address findings via new commits on the branch.

**Open PR:**

```bash
gh pr create --title "feat: v3.1.0 case-based pattern learning" --body "$(cat <<'EOF'
## Summary
- Implements the read path for case-based pattern learning per the v3 design's Stage B preview
- New analyzer at Stage 10b: heuristic Python (bulk) + Haiku (semantic compare only)
- Accumulator + learned_patterns.md as the new state files; cases extended with applied_patterns
- Prose-craft-style graduation ceremony at Stage 10c (promote / reject / hold)
- Agent definition files unchanged — purely additive

## Test plan
- [ ] `pytest tests/ -v` shows all 308+N tests passing (no regressions)
- [ ] Multi-run trajectory test (test_pattern_evolution.py) covers full lifecycle
- [ ] Backward-compat test confirms empty state behaves like v3.0.0
- [ ] Manual: run /research on a fresh topic, verify case is written and analyzer runs silently

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Plan complete and saved to `docs/plans/2026-05-27-v3-1-case-learning-plan.md`. Two execution options:

**1. Subagent-Driven (this session)** — I dispatch fresh subagent per task, review between tasks, fast iteration.

**2. Parallel Session (separate)** — Open new session with `executing-plans`, batch execution with checkpoints.

**Which approach?**
