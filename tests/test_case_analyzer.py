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
