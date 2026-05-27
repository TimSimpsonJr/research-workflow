"""
state.py — Pipeline state management with crash recovery.

Tracks pipeline progress via JSON checkpoints. Supports resume,
restart, and abandon flows. State lives in the vault at
{vault}/.research-workflow/state/.
"""

import json
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from confidence import get_depth_profile

CURRENT_RUN_FILE = "current_run.json"
STATE_VERSION = 3


def _atomic_write(path: Path, data: dict) -> None:
    """Write JSON atomically via temp file + rename."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def save_state(state_dir: Path, run: dict) -> None:
    """Save the active run state atomically. Public wrapper around _atomic_write."""
    _atomic_write(state_dir / CURRENT_RUN_FILE, run)


def init_topic(topic: str, mode: str, depth: str) -> dict:
    """Create a fresh topic state entry for the run.

    The 12 fields cover identity (topic/mode/depth), hop-loop budget
    (max_hops/current_hop), lifecycle (status), audit trail (hop_genealogy),
    quality signals (confidence_history/contradiction_rate), dedup (seen_urls),
    and forward routing (next_hop for "continue", replan_hint for "replan").
    next_hop and replan_hint are mutually exclusive in practice.
    """
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


def create_run(state_dir: Path, run_id: str, tier: str) -> dict:
    """Create a new run. Archives any completed previous run automatically.

    Raises FileExistsError only if an *incomplete* run is still active.
    Completed runs are archived to history/ and a fresh run starts.
    """
    run_file = state_dir / CURRENT_RUN_FILE
    if run_file.exists():
        existing = json.loads(run_file.read_text(encoding="utf-8"))
        if existing.get("completed_at"):
            # Previous run finished — archive it and continue
            _archive_run(state_dir)
        else:
            raise FileExistsError(
                f"Active incomplete run exists: {existing.get('run_id', 'unknown')}. "
                f"Resume, restart, or abandon it first."
            )
    state_dir.mkdir(parents=True, exist_ok=True)
    run = {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "stage": "triage",
        "version": STATE_VERSION,
        "stage_progress": {},
        "tier_detected": tier,
        "plan_approved": False,
    }
    _atomic_write(run_file, run)
    return run


def load_run(state_dir: Path) -> dict | None:
    """Load current run, or None if no active run.

    If the on-disk schema version does not match STATE_VERSION, archive the
    stale file in-place and return None. We archive directly here (without
    calling abandon_run -> _archive_run -> load_run) to avoid infinite
    recursion on schema-mismatch files.
    """
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
        # Archive in-place WITHOUT recursing through abandon_run -> _archive_run -> load_run
        old_id = data.get("run_id", "unparseable")
        history_dir = state_dir / "history" / f"{old_id}-stale-v{data.get('version', 'unknown')}"
        history_dir.mkdir(parents=True, exist_ok=True)
        for f in state_dir.glob("*.json"):
            shutil.move(str(f), str(history_dir / f.name))
        return None
    return data


def update_stage(state_dir: Path, stage: str, progress: dict | None = None) -> None:
    """Update the current run's stage and optional progress."""
    run = load_run(state_dir)
    if run is None:
        raise RuntimeError("No active run")
    run["stage"] = stage
    if progress is not None:
        run["stage_progress"] = progress
    _atomic_write(state_dir / CURRENT_RUN_FILE, run)


def save_stage_output(state_dir: Path, name: str, data: dict) -> None:
    """Save a stage's output file atomically."""
    _atomic_write(state_dir / f"{name}.json", data)


def load_stage_output(state_dir: Path, name: str) -> dict | None:
    """Load a stage's output file, or None if missing."""
    path = state_dir / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def append_written_note(state_dir: Path, topic: str, path: str, model: str) -> None:
    """Append a completed note to written_notes.json."""
    written = load_stage_output(state_dir, "written_notes") or {"completed": []}
    written["completed"].append({
        "topic": topic,
        "path": path,
        "model": model,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })
    save_stage_output(state_dir, "written_notes", written)


def _archive_run(state_dir: Path) -> None:
    """Move all state files to history/{run_id}/."""
    run = load_run(state_dir)
    if run is None:
        return
    history_dir = state_dir / "history" / run["run_id"]
    history_dir.mkdir(parents=True, exist_ok=True)
    for f in state_dir.glob("*.json"):
        shutil.move(str(f), str(history_dir / f.name))


def abandon_run(state_dir: Path) -> None:
    """Archive incomplete run to history."""
    _archive_run(state_dir)


def complete_run(state_dir: Path) -> None:
    """Archive completed run to history."""
    run = load_run(state_dir)
    if run:
        run["completed_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_write(state_dir / CURRENT_RUN_FILE, run)
    _archive_run(state_dir)


def is_stale_run(state_dir: Path, max_age_hours: int = 24) -> bool:
    """Check if the current run is older than max_age_hours."""
    run = load_run(state_dir)
    if run is None:
        return False
    started = datetime.fromisoformat(run["started_at"])
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - started > timedelta(hours=max_age_hours)
