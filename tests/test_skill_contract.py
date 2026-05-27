# tests/test_skill_contract.py
"""Contract tests for skills/research/SKILL.md.

SKILL.md is interpreted by the orchestrator at runtime as instructions for
how to assemble bash snippets and gate stage transitions. The Python code in
this repo cannot exercise that markdown directly, so we pin the load-bearing
shape with text-level assertions. A future edit that silently drops one of
these fields will fail the contract test.

These tests are regressions for the codex impl-review findings on v3.1.0
case-based pattern learning:
- score-loop cluster: Stage 10c case dict must include `applied_patterns`
- graduation-write-path cluster: Stage 10d/10e must defend against
  accumulator_* warnings in addition to learned_patterns_* warnings.
"""

from pathlib import Path


_SKILL_MD = Path(__file__).parent.parent / "skills" / "research" / "SKILL.md"


def test_skill_md_stage_10c_includes_applied_patterns_in_case_dict():
    """SKILL.md Stage 10c case-dict assembly must include 'applied_patterns' field.

    Without it, the score/demotion loop in Stage 10d's analyzer is a no-op in
    production (case.get('applied_patterns', []) returns []). Regression for
    codex-impl-review finding score-loop cluster.
    """
    text = _SKILL_MD.read_text(encoding="utf-8")
    # Find the Stage 10c block — anchor on the write_case_record reference
    assert "write_case_record" in text, "Stage 10c must reference write_case_record"
    # The case dict assembly must include applied_patterns sourced from final
    assert "'applied_patterns':" in text, \
        "Stage 10c case dict must include 'applied_patterns' field"


def test_skill_md_stage_10d_gates_on_accumulator_warnings():
    """Stage 10d must skip Stage 10e on accumulator_* warnings, not just
    learned_patterns_* warnings. Regression for codex-impl-review finding
    graduation-write-path cluster.
    """
    text = _SKILL_MD.read_text(encoding="utf-8")
    # The Stage 10e gating condition must reference both warning families
    # Find the gating sentence (heuristic: search for "skip Stage 10e")
    gating_idx = text.find("skip Stage 10e")
    assert gating_idx > 0, "Stage 10e gating instruction not found"
    # Look at the surrounding ~500 chars for both keywords
    context = text[max(0, gating_idx - 250):gating_idx + 250]
    assert "learned_patterns_" in context, "gate must mention learned_patterns_* warnings"
    assert "accumulator_" in context, "gate must mention accumulator_* warnings"


def test_skill_md_stage_10e_all_branches_check_acc_warnings():
    """All three Stage 10e branches (Promote, Reject, Hold) must check
    acc_warnings before saving the accumulator. Without this defense-in-depth,
    a corrupt accumulator could be overwritten with empty content.
    """
    text = _SKILL_MD.read_text(encoding="utf-8")
    # Each branch has its own ```bash block; each block must mention acc_warnings handling
    # Heuristic: count "BRANCH_ABORTED" occurrences — should be >= 3 (one per branch)
    aborted_count = text.count("BRANCH_ABORTED")
    assert aborted_count >= 3, \
        f"expected acc_warnings check in all 3 Stage 10e branches, found {aborted_count} BRANCH_ABORTED markers"
