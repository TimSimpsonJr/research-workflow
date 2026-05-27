from learned_patterns import (
    LearnedPattern,
    LearnedPatternsFile,
    LEARNED_PATTERNS_SCHEMA_VERSION,
    load_learned_patterns,
    save_learned_patterns,
)


def test_load_missing_returns_empty(tmp_path):
    """Missing file returns empty LearnedPatternsFile with no warnings."""
    loaded, warnings = load_learned_patterns(tmp_path / "missing.md")
    assert loaded.version == LEARNED_PATTERNS_SCHEMA_VERSION
    assert loaded.patterns == []
    assert warnings == []
