# scripts/confidence.py
"""confidence.py — research quality scoring.

Pure functions for computing confidence and contradiction signals from
hop summaries. No I/O, no API calls — fully testable offline.
"""

DEPTH_PROFILES = {
    "quick":      {"max_hops": 1, "target_sources": 10, "confidence_target": 0.6},
    "standard":   {"max_hops": 3, "target_sources": 20, "confidence_target": 0.7},
    "deep":       {"max_hops": 4, "target_sources": 40, "confidence_target": 0.8},
    "exhaustive": {"max_hops": 5, "target_sources": 50, "confidence_target": 0.9},
}


def get_depth_profile(name: str) -> dict:
    """Return the depth profile for the given name. Raises KeyError if unknown."""
    return DEPTH_PROFILES[name]
