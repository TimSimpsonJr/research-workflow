import json
from pathlib import Path


def test_detect_source_tier_dominance_civic_alpr():
    """When civic+alpr cases consistently show T1-dominant patterns_that_worked,
    detect_source_tier_dominance produces a candidate observation."""
    from pattern_detection import detect_source_tier_dominance
    cases = json.loads(Path("tests/fixtures/case_learning/civic_alpr_cases.json").read_text())
    candidates = detect_source_tier_dominance(cases, min_dominance=0.5, min_cases=3)
    civic_alpr = [c for c in candidates if set(c["domain_tags"]) == {"civic", "alpr"}]
    assert len(civic_alpr) == 1
    c = civic_alpr[0]
    assert c["category"] == "source-tier-bias"
    assert c["target_stage"] == "search"
    assert "T1" in c["name"] or "T1" in c["proposed_promotion_body"]


def test_detect_source_tier_dominance_sparse_returns_empty():
    """Sparse fixture (1-2 cases) doesn't produce candidates."""
    from pattern_detection import detect_source_tier_dominance
    cases = json.loads(Path("tests/fixtures/case_learning/sparse_domain.json").read_text())
    candidates = detect_source_tier_dominance(cases, min_dominance=0.5, min_cases=3)
    assert candidates == []
