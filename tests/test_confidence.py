# tests/test_confidence.py
from confidence import (
    DEPTH_PROFILES,
    compute_confidence,
    contradiction_rate,
    get_depth_profile,
    primary_source_presence,
    source_count_adequacy,
    tier_diversity_weight,
    topic_coverage,
)


def test_depth_profiles_have_required_fields():
    for name in ["quick", "standard", "deep", "exhaustive"]:
        profile = DEPTH_PROFILES[name]
        assert "max_hops" in profile
        assert "target_sources" in profile
        assert "confidence_target" in profile


def test_get_depth_profile_returns_dict():
    profile = get_depth_profile("standard")
    assert profile["max_hops"] == 3
    assert profile["target_sources"] == 20
    assert profile["confidence_target"] == 0.7


def test_get_depth_profile_invalid_raises():
    import pytest
    with pytest.raises(KeyError):
        get_depth_profile("nonsense")


def test_tier_diversity_all_t1():
    sources = [{"tier": "T1"} for _ in range(3)]
    assert tier_diversity_weight(sources) == 1.0


def test_tier_diversity_all_t4():
    sources = [{"tier": "T4"} for _ in range(3)]
    assert tier_diversity_weight(sources) == 0.25


def test_tier_diversity_mixed():
    sources = [{"tier": "T1"}, {"tier": "T2"}, {"tier": "T3"}, {"tier": "T4"}]
    expected = (1.0 + 0.75 + 0.5 + 0.25) / 4
    assert tier_diversity_weight(sources) == expected


def test_tier_diversity_empty():
    assert tier_diversity_weight([]) == 0.0


def test_topic_coverage_three_t2_sources():
    sources = [{"tier": "T2"}, {"tier": "T2"}, {"tier": "T2"}]
    assert topic_coverage(sources) == 1.0


def test_topic_coverage_two_t1_sources():
    sources = [{"tier": "T1"}, {"tier": "T1"}]
    assert topic_coverage(sources) == 2 / 3


def test_topic_coverage_low_tier_excluded():
    sources = [{"tier": "T3"}, {"tier": "T4"}, {"tier": "T3"}]
    assert topic_coverage(sources) == 0.0


def test_topic_coverage_mixed():
    sources = [{"tier": "T1"}, {"tier": "T3"}, {"tier": "T2"}, {"tier": "T4"}]
    assert topic_coverage(sources) == 2 / 3


def test_primary_source_presence_zero():
    sources = [{"is_primary": False}, {"is_primary": False}]
    assert primary_source_presence(sources) == 0.0


def test_primary_source_presence_one():
    sources = [{"is_primary": True}, {"is_primary": False}]
    assert primary_source_presence(sources) == 0.5


def test_primary_source_presence_two():
    sources = [{"is_primary": True}, {"is_primary": True}]
    assert primary_source_presence(sources) == 1.0


def test_primary_source_presence_caps_at_two():
    sources = [{"is_primary": True}] * 5
    assert primary_source_presence(sources) == 1.0


def test_source_count_adequacy_below_target():
    assert source_count_adequacy(sources_count=10, target=20) == 0.5


def test_source_count_adequacy_at_target():
    assert source_count_adequacy(sources_count=20, target=20) == 1.0


def test_source_count_adequacy_above_target():
    assert source_count_adequacy(sources_count=30, target=20) == 1.0


def test_source_count_adequacy_zero():
    assert source_count_adequacy(sources_count=0, target=20) == 0.0


def test_compute_confidence_strong_topic():
    sources = [
        {"tier": "T1", "is_primary": True},
        {"tier": "T1", "is_primary": False},
        {"tier": "T2", "is_primary": True},
        {"tier": "T2", "is_primary": False},
    ]
    score = compute_confidence(sources, depth="standard")
    # tier_diversity ~0.875, coverage 1.0, primary 1.0, adequacy 4/20=0.2
    # 0.4*0.875 + 0.3*1.0 + 0.2*1.0 + 0.1*0.2 = 0.87
    assert 0.86 <= score <= 0.88


def test_compute_confidence_weak_topic():
    sources = [{"tier": "T4", "is_primary": False}]
    score = compute_confidence(sources, depth="standard")
    # tier 0.25, coverage 0.0, primary 0.0, adequacy 1/20=0.05 = 0.105
    assert 0.10 <= score <= 0.11


def test_compute_confidence_empty():
    assert compute_confidence([], depth="standard") == 0.0


def test_contradiction_rate_none():
    sources = [{"url": "a"}, {"url": "b"}, {"url": "c"}]
    contradictions = []
    assert contradiction_rate(sources, contradictions) == 0.0


def test_contradiction_rate_single_pair():
    sources = [{"url": "a"}, {"url": "b"}, {"url": "c"}]
    contradictions = [{"source_a": "a", "source_b": "b"}]
    # 1 / (3 * 0.3) = 1.11 → capped 1.0
    assert contradiction_rate(sources, contradictions) == 1.0


def test_contradiction_rate_proportional():
    sources = [{"url": f"s{i}"} for i in range(10)]
    contradictions = [{"source_a": "s0", "source_b": "s1"}]
    # 1 / (10 * 0.3) ≈ 0.333
    assert 0.33 <= contradiction_rate(sources, contradictions) <= 0.34


def test_contradiction_rate_too_few_sources():
    sources = [{"url": "a"}]
    contradictions = []
    assert contradiction_rate(sources, contradictions) == 0.0
