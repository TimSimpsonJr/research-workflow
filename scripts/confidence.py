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


TIER_WEIGHTS = {"T1": 1.0, "T2": 0.75, "T3": 0.5, "T4": 0.25}


def tier_diversity_weight(sources: list[dict]) -> float:
    """Average tier weight across sources. Empty list returns 0.0."""
    if not sources:
        return 0.0
    return sum(TIER_WEIGHTS.get(s["tier"], 0.25) for s in sources) / len(sources)


def topic_coverage(sources: list[dict]) -> float:
    """Fraction of T2+ sources up to a count of 3. Caps at 1.0."""
    t2plus = sum(1 for s in sources if s["tier"] in {"T1", "T2"})
    return min(1.0, t2plus / 3)


def primary_source_presence(sources: list[dict]) -> float:
    """Capped at 1.0 when 2+ primary sources present."""
    primary_count = sum(1 for s in sources if s.get("is_primary"))
    return min(1.0, primary_count / 2)


def source_count_adequacy(sources_count: int, target: int) -> float:
    """Linear up to target, then capped at 1.0."""
    if target <= 0:
        return 0.0
    return min(1.0, sources_count / target)


def compute_confidence(sources: list[dict], depth: str) -> float:
    """Composite confidence score for a topic's sources.

    Weights: 0.4 tier_diversity + 0.3 topic_coverage + 0.2 primary_source_presence
    + 0.1 source_count_adequacy.
    """
    if not sources:
        return 0.0
    target = get_depth_profile(depth)["target_sources"]
    return (
        0.4 * tier_diversity_weight(sources) +
        0.3 * topic_coverage(sources) +
        0.2 * primary_source_presence(sources) +
        0.1 * source_count_adequacy(len(sources), target)
    )


def contradiction_rate(sources: list[dict], contradictions: list[dict]) -> float:
    """Normalize contradictions by (source_count * 0.3). Caps at 1.0."""
    if len(sources) < 2:
        return 0.0
    if not contradictions:
        return 0.0
    return min(1.0, len(contradictions) / (len(sources) * 0.3))
