# tests/test_confidence.py
from confidence import DEPTH_PROFILES, get_depth_profile


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
