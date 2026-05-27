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


def test_detect_hop_pattern_confidence_delta_tech():
    """When tech-domain cases consistently show conceptual_deepening
    delivers the biggest confidence lift at a given hop position,
    detect_hop_pattern_lift produces a candidate."""
    from pattern_detection import detect_hop_pattern_lift
    cases = json.loads(Path("tests/fixtures/case_learning/tech_cases.json").read_text())
    candidates = detect_hop_pattern_lift(cases, min_lift=0.1, min_cases=3)
    tech_candidates = [c for c in candidates if "tech" in c["domain_tags"]]
    assert len(tech_candidates) >= 1
    c = tech_candidates[0]
    assert c["category"] == "hop-pattern-bias"
    assert c["target_stage"] == "hop_planner"


def test_detect_query_template_recurrence():
    """When the same query template (e.g., '[city] ALPR [year]') recurs across
    cases as a high-success query, detect_query_template_recurrence flags it."""
    from pattern_detection import detect_query_template_recurrence
    cases = json.loads(Path("tests/fixtures/case_learning/civic_alpr_cases.json").read_text())
    candidates = detect_query_template_recurrence(cases, min_recurrence=3)
    assert any(c["category"] == "query-template" for c in candidates)
