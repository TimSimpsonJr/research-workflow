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
    """Overwrite the topic's contradiction_rate with the latest measurement.

    Setter rather than history-tracker — the rate is recomputed from all hops'
    summaries each pass, so only the latest value is meaningful.
    """
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
    """Increase the topic's hop budget.

    Used by Stage 5b auto-replan to give a topic another hop after it exhausts
    its initial budget; without this, the Stage 4 admission check
    (current_hop < max_hops) would silently filter the topic out.
    """
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


def increment_replan(state_dir: Path) -> None:
    """Increment the run's replan counter. Silently no-ops if no active run."""
    run = load_run(state_dir)
    if run is None:
        return
    run["replan_count"] += 1
    save_state(state_dir, run)


_RESERVED_DECISION_KEYS = {"decision", "at"}


def record_user_decision(state_dir: Path, decision: str, **details) -> None:
    """Append a user-decision entry to the run's user_decisions log.

    Extra details (e.g., confidence, reason) are merged into the entry alongside
    the decision label and timestamp. Silently no-ops if no active run.

    Raises TypeError if `details` contains reserved keys ("decision", "at") —
    those would silently override the canonical fields via dict-spread order.
    """
    reserved = _RESERVED_DECISION_KEYS & details.keys()
    if reserved:
        raise TypeError(
            f"record_user_decision: details cannot contain reserved keys: {sorted(reserved)}"
        )
    run = load_run(state_dir)
    if run is None:
        return
    run["user_decisions"].append({
        "decision": decision,
        "at": datetime.now(timezone.utc).isoformat(),
        **details,
    })
    save_state(state_dir, run)


_KNOWN_USAGE_MODELS = {"haiku", "sonnet", "opus", "ollama"}


def add_usage(state_dir: Path, model: str, in_tokens: int, out_tokens: int, stage: str) -> None:
    """Increment per-model usage counters for the active run.

    Safe against missing keys on the ollama bucket (which lacks token fields by
    design — local inference has no token cost). Uses dict.get(key, 0) + rather
    than += to keep ollama incrementing safely. Silently no-ops if there is no
    active run (telemetry shouldn't block the pipeline).

    Raises ValueError on unknown model names — prevents typos like "haku" from
    silently creating ghost buckets that would distort cost estimates.

    `stage` is currently unused but kept in the signature for future
    per-stage breakdown.
    """
    if model not in _KNOWN_USAGE_MODELS:
        raise ValueError(
            f"add_usage: unknown model {model!r}; expected one of {sorted(_KNOWN_USAGE_MODELS)}"
        )
    run = load_run(state_dir)
    if run is None:
        return
    bucket = run["usage"].setdefault(model, {"calls": 0})
    bucket["calls"] = bucket.get("calls", 0) + 1
    if model != "ollama":
        bucket["in_tokens"] = bucket.get("in_tokens", 0) + in_tokens
        bucket["out_tokens"] = bucket.get("out_tokens", 0) + out_tokens
    save_state(state_dir, run)


def apply_hop_decision(
    state_dir: Path,
    topic_name: str,
    hop_data: dict,
    decision: str,
    confidence_score: float,
    contradiction_rate: float,
    next_hop: dict | None = None,
    replan_hint: dict | None = None,
) -> None:
    """Atomically apply the full state transition for one hop-planner decision.

    Combines record_hop + set_next_hop + set_replan_hint + mark_topic_status
    + append_confidence + set_contradiction_rate into a single
    load -> mutate -> save cycle. On disk, the transition is all-or-nothing
    (the single save_state at the end writes atomically via temp+rename).
    A crash mid-function — before save_state runs — discards the entire
    transition; resume re-runs the hop from its prior on-disk state.

    `decision` is one of: "continue", "stop", "early_terminated", "replan".

    Stage 4e of the orchestrator should always call this rather than the
    per-field setters when applying a hop-planner response. The quality
    signals (confidence_score, contradiction_rate) come directly from the
    hop-planner JSON and are required arguments.
    """
    run = load_run(state_dir)
    if run is None:
        raise RuntimeError("No active run")
    for t in run["topics"]:
        if t["topic"] == topic_name:
            # Always: record the hop, advance current_hop, persist quality signals
            t["hop_genealogy"].append(hop_data)
            t["current_hop"] += 1
            t["confidence_history"].append(confidence_score)
            t["contradiction_rate"] = contradiction_rate
            # Decision-specific transitions
            if decision == "continue":
                t["next_hop"] = next_hop
                t["replan_hint"] = None   # clear any stale replan_hint
                # status stays "active"
            elif decision == "stop":
                t["next_hop"] = None
                t["status"] = "complete"
            elif decision == "early_terminated":
                t["next_hop"] = None
                t["status"] = "early_terminated"
            elif decision == "replan":
                t["next_hop"] = None
                t["replan_hint"] = replan_hint
                t["status"] = "replan_pending"
            else:
                raise ValueError(f"Unknown decision: {decision!r}")
            break
    else:
        raise KeyError(f"Topic not found: {topic_name}")
    save_state(state_dir, run)


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
        "usage": {
            "haiku":  {"calls": 0, "in_tokens": 0, "out_tokens": 0},
            "sonnet": {"calls": 0, "in_tokens": 0, "out_tokens": 0},
            "opus":   {"calls": 0, "in_tokens": 0, "out_tokens": 0},
            "ollama": {"calls": 0},
        },
        "replan_count": 0,
        "user_decisions": [],
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


def complete_run(state_dir: Path) -> dict | None:
    """Archive completed run to history. Returns the final run dict (with
    completed_at) before archiving so Stage 10 callers can read telemetry,
    hop genealogy, and case-record data from the in-memory snapshot without
    having to re-load from history/."""
    run = load_run(state_dir)
    if run:
        run["completed_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_write(state_dir / CURRENT_RUN_FILE, run)
    _archive_run(state_dir)
    return run


def is_stale_run(state_dir: Path, max_age_hours: int = 24) -> bool:
    """Check if the current run is older than max_age_hours."""
    run = load_run(state_dir)
    if run is None:
        return False
    started = datetime.fromisoformat(run["started_at"])
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - started > timedelta(hours=max_age_hours)


def write_case_record(cases_dir: Path, case_data: dict) -> None:
    """Write a case record JSON to cases_dir/{case_id}.json.

    Stage A (case prep) writes case records at completion. Stage B will read
    them later for retrospective analysis; nothing reads them yet. Creates
    the cases directory if it doesn't exist.
    """
    cases_dir.mkdir(parents=True, exist_ok=True)
    case_id = case_data["case_id"]
    case_file = cases_dir / f"{case_id}.json"
    case_file.write_text(json.dumps(case_data, indent=2), encoding="utf-8", newline="\n")
