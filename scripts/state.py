"""
state.py — Pipeline state management with crash recovery.

Tracks pipeline progress via JSON checkpoints. Supports resume,
restart, and abandon flows. State lives in the vault at
{vault}/.research-workflow/state/.
"""

import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

CURRENT_RUN_FILE = "current_run.json"


def _atomic_write(path: Path, data: dict) -> None:
    """Write JSON atomically via temp file + rename."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def create_run(state_dir: Path, run_id: str, tier: str) -> dict:
    """Create a new run. Raises FileExistsError if a run is active."""
    run_file = state_dir / CURRENT_RUN_FILE
    if run_file.exists():
        raise FileExistsError(f"Active run exists: {run_file}")
    state_dir.mkdir(parents=True, exist_ok=True)
    run = {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "stage": "resolve",
        "stage_progress": {},
        "tier_detected": tier,
        "plan_approved": False,
    }
    _atomic_write(run_file, run)
    return run


def load_run(state_dir: Path) -> dict | None:
    """Load current run, or None if no active run."""
    run_file = state_dir / CURRENT_RUN_FILE
    if not run_file.exists():
        return None
    return json.loads(run_file.read_text(encoding="utf-8"))


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
