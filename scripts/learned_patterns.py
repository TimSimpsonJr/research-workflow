"""learned_patterns.md — graduated patterns the orchestrator injects into
subagent user prompts. Grouped by domain -> target_stage.

See docs/plans/2026-05-27-v3-1-case-learning-design.md Section 5.3 for schema.
"""

from __future__ import annotations

import re
import sys
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
    except (OSError, UnicodeDecodeError) as e:
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
                f"(missing id or score): {pending.get('name', '?')}",
                file=sys.stderr,
            )
            pending = None
            return
        # Parse score
        m = _SCORE_LINE.match(pending["score"])
        if not m:
            print(
                f"[learned_patterns] skipping malformed entry "
                f"(bad score: {pending['score']!r}): {pending.get('name', '?')}",
                file=sys.stderr,
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


def filter_by_topic_text(
    file: LearnedPatternsFile,
    *,
    topics: list[str],
) -> list[LearnedPattern]:
    """Return patterns whose domain_tags appear as case-insensitive substrings
    in the joined topic text. Used at Stage 2 when formal domain_tags don't
    exist yet (v3.0.0 derives domain_tags only at case-write time from
    written-note tags). Plain substring match — no token boundaries, no
    stemming, no fuzzy matching."""
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
    Used at Stage 10d when the case has its derived domain_tags available."""
    run_set = set(run_domain_tags)
    return [p for p in file.patterns if run_set & set(p.domain_tags)]


def group_by_stage(patterns: list[LearnedPattern]) -> dict[str, list[LearnedPattern]]:
    """Group patterns into a dict keyed by target_stage.
    All three known stages are present in the returned dict (empty lists if no patterns)."""
    out: dict[str, list[LearnedPattern]] = {"search": [], "hop_planner": [], "classify": []}
    for p in patterns:
        out.setdefault(p.target_stage, []).append(p)
    return out
