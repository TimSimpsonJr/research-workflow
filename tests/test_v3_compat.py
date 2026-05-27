"""Backward-compat tests — empty/missing v3.1.0 state should behave like v3.0.0."""

import json
from pathlib import Path


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
