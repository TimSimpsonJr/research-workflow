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


def test_analyze_civic_alpr_cases_produces_promotion_candidates(tmp_path):
    """With civic_alpr cases, expect at least one promotion candidate to surface
    after enough runs to cross promotion_threshold (default 3)."""
    from case_analyzer import analyze

    fixture_path = Path("tests/fixtures/case_learning/civic_alpr_cases.json")
    cases = json.loads(fixture_path.read_text())
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    for c in cases:
        (cases_dir / f"{c['case_id']}.json").write_text(json.dumps(c))

    # Drive 3 runs through the analyzer to build sessions_seen
    result = None
    for i in range(3):
        result = analyze(
            case_path=cases_dir / f"{cases[i]['case_id']}.json",
            accumulator_path=tmp_path / "accumulator.json",
            learned_patterns_path=tmp_path / "learned_patterns.md",
            cases_dir=cases_dir,
            cases_window=20,
        )

    # After 3 runs, at least one civic-alpr candidate should be eligible
    assert len(result.promotion_candidates) >= 1
    civic = [c for c in result.promotion_candidates if "civic" in c.domain_tags]
    assert len(civic) >= 1
