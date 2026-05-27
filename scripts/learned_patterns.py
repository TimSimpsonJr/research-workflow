"""learned_patterns.md — graduated patterns the orchestrator injects into
subagent user prompts. Grouped by domain -> target_stage.

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
    - missing file -> empty file, no warning
    - read error -> empty file, warning
    - schema version mismatch -> empty file, warning
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
