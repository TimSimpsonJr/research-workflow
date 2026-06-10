# tests/test_manifest_budget.py
"""Budget guard for MANIFEST.md (owned-repo convention).

MANIFEST.md is a one-line-per-file INDEX, not a prose mirror of the codebase.
Depth belongs in the design docs (the WHY), the docstrings (the HOW), and the
tests (the contract); the MANIFEST only indexes and points to them. These cheap
guards fail loudly if the line budget or per-line word budget is exceeded, so the
file cannot silently re-ratchet (the Magpie-218-line lesson).
"""

from pathlib import Path

_MANIFEST = Path(__file__).parent.parent / "MANIFEST.md"
MAX_LINES = 95
MAX_WORDS_PER_LINE = 55


def test_manifest_line_budget():
    lines = _MANIFEST.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= MAX_LINES, (
        f"MANIFEST.md is {len(lines)} lines (budget {MAX_LINES}). "
        "Trim to a one-line-per-file index; depth belongs in design docs / docstrings / tests."
    )


def test_manifest_no_line_exceeds_word_budget():
    lines = _MANIFEST.read_text(encoding="utf-8").splitlines()
    offenders = [
        (i + 1, len(line.split()))
        for i, line in enumerate(lines)
        if len(line.split()) > MAX_WORDS_PER_LINE
    ]
    assert not offenders, (
        f"MANIFEST.md lines exceed {MAX_WORDS_PER_LINE} words (depth leaking into an "
        f"entry — keep it to one line): {offenders}"
    )
