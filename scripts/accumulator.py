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
    """Reserved for a future strict-load companion to ``load_accumulator``.

    Not currently raised — ``load_accumulator`` always degrades gracefully
    by returning an empty Accumulator plus warnings. Defined here so a
    future ``load_accumulator_strict`` (which would raise instead) has a
    stable exception type to import.
    """


def load_accumulator(path: Path) -> tuple[Accumulator, list[str]]:
    """Graceful load: returns (Accumulator, warnings). Never raises.

    On parse error, schema-version mismatch, non-dict root, invalid UTF-8,
    or entry-shape mismatch: logs to warnings, returns an empty Accumulator.
    The analyzer propagates these warnings into AnalyzerResult.warnings; the
    analyzer ALSO refuses to write back to a file that loaded with warnings
    (see analyze()'s persist step). This keeps user-recoverable corrupt
    state on disk so the user can inspect or manually delete it to reset.
    """
    warnings: list[str] = []
    if not path.exists():
        return Accumulator(), warnings
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        warnings.append(f"accumulator_corrupted: {path} could not be read or parsed ({e})")
        return Accumulator(), warnings
    if not isinstance(data, dict):
        warnings.append(
            f"accumulator_corrupted: {path} root is {type(data).__name__}, expected dict. "
            f"Treating as empty."
        )
        return Accumulator(), warnings
    file_version = data.get("version")
    if file_version != ACCUMULATOR_SCHEMA_VERSION:
        warnings.append(
            f"accumulator_schema_mismatch: {path} is version {file_version!r}, "
            f"code expects {ACCUMULATOR_SCHEMA_VERSION}. Treating as empty."
        )
        return Accumulator(), warnings
    try:
        entries = [AccumulatorEntry(**e) for e in data.get("entries", [])]
    except (TypeError, ValueError) as e:
        # Schema-shape mismatch (e.g., entry missing required field after a
        # forward-incompatible edit, or non-mapping entry). Treat the whole
        # file as corrupt.
        warnings.append(
            f"accumulator_corrupted: entry shape unexpected in {path} "
            f"({type(e).__name__}: {e})"
        )
        return Accumulator(), warnings
    return Accumulator(version=file_version, entries=entries), warnings


def save_accumulator(path: Path, acc: Accumulator) -> None:
    """Save accumulator to JSON file via atomic write."""
    payload = {
        "version": acc.version,
        "entries": [asdict(e) for e in acc.entries],
    }
    write_shared_state_atomically(path, payload)
