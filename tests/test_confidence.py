# tests/test_confidence.py
from confidence import (
    DEPTH_PROFILES,
    get_depth_profile,
    primary_source_presence,
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
