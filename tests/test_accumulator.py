import json
from pathlib import Path
from accumulator import (
    load_accumulator,
    save_accumulator,
    Accumulator,
    AccumulatorEntry,
    ACCUMULATOR_SCHEMA_VERSION,
)


def test_load_missing_returns_empty(tmp_path):
    """Missing accumulator.json returns an empty Accumulator with no warnings."""
    acc, warnings = load_accumulator(tmp_path / "missing.json")
    assert acc.version == ACCUMULATOR_SCHEMA_VERSION
    assert acc.entries == []
    assert warnings == []


def test_save_then_load_roundtrip(tmp_path):
    """Round-trip preserves all fields; no warnings on clean load."""
    target = tmp_path / "accumulator.json"
    entry = AccumulatorEntry(
        pattern_id="civic-alpr-t1-dominance-3f7a",
        name="T1 sources dominate",
        category="source-tier-bias",
        target_stage="search",
        domain_tags=["civic", "alpr"],
        sessions_seen=3,
        sessions_since_last_seen=0,
        status="hold",
        raised_bar=False,
        promotion_pending=False,
        demotion_count=0,
        evidence=[{"case_id": "c1", "signal": "T1=8/12"}],
        proposed_promotion_body="T1 sources dominate...",
        created_at="2026-05-22T10:14:00Z",
        last_updated_at="2026-05-27T15:30:00Z",
    )
    acc = Accumulator(version=ACCUMULATOR_SCHEMA_VERSION, entries=[entry])
    save_accumulator(target, acc)
    loaded, warnings = load_accumulator(target)
    assert loaded == acc
    assert warnings == []


def test_save_writes_atomic_via_state(tmp_path):
    """save_accumulator uses write_shared_state_atomically."""
    target = tmp_path / "accumulator.json"
    acc = Accumulator(version=ACCUMULATOR_SCHEMA_VERSION, entries=[])
    save_accumulator(target, acc)
    assert target.exists()
    # No leftover .tmp file
    assert not target.with_suffix(".json.tmp").exists()


def test_load_corrupt_returns_empty_with_warning(tmp_path):
    """Malformed JSON returns empty Accumulator + corrupted warning."""
    target = tmp_path / "accumulator.json"
    target.write_text("{not valid json")
    acc, warnings = load_accumulator(target)
    assert acc.entries == []
    assert len(warnings) == 1
    assert "accumulator_corrupted" in warnings[0]


def test_load_version_mismatch_returns_empty_with_warning(tmp_path):
    """Schema version mismatch returns empty Accumulator + schema_mismatch warning."""
    import json as _j
    target = tmp_path / "accumulator.json"
    target.write_text(_j.dumps({"version": 99, "entries": []}))
    acc, warnings = load_accumulator(target)
    assert acc.entries == []
    assert len(warnings) == 1
    assert "accumulator_schema_mismatch" in warnings[0]
