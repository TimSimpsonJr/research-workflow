import json
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
    target = tmp_path / "accumulator.json"
    target.write_text(json.dumps({"version": 99, "entries": []}))
    acc, warnings = load_accumulator(target)
    assert acc.entries == []
    assert len(warnings) == 1
    assert "accumulator_schema_mismatch" in warnings[0]


def test_load_non_dict_root_returns_empty_with_warning(tmp_path):
    """JSON root that's not a dict (e.g., a list) returns empty + corrupted warning."""
    target = tmp_path / "accumulator.json"
    target.write_text("[]")
    acc, warnings = load_accumulator(target)
    assert acc.entries == []
    assert len(warnings) == 1
    assert "accumulator_corrupted" in warnings[0]


def test_load_invalid_utf8_returns_empty_with_warning(tmp_path):
    """Invalid UTF-8 returns empty + corrupted warning instead of crashing."""
    target = tmp_path / "accumulator.json"
    target.write_bytes(b"\xff\xfe invalid utf-8")
    acc, warnings = load_accumulator(target)
    assert acc.entries == []
    assert len(warnings) == 1
    assert "accumulator_corrupted" in warnings[0]


def test_record_observation_new_pattern():
    """A pattern_id not in the accumulator gets added with sessions_seen=1."""
    from accumulator import Accumulator, record_observation
    acc = Accumulator()
    record_observation(
        acc,
        pattern_id="p1",
        name="P1",
        category="cat",
        target_stage="search",
        domain_tags=["civic"],
        evidence_row={"case_id": "c1", "signal": "..."},
        proposed_promotion_body="body",
    )
    assert len(acc.entries) == 1
    e = acc.entries[0]
    assert e.sessions_seen == 1
    assert e.sessions_since_last_seen == 0
    assert e.status == "hold"


def test_record_observation_existing_increments_seen():
    """Recording the same pattern again increments sessions_seen and resets stale."""
    from accumulator import Accumulator, AccumulatorEntry, record_observation
    acc = Accumulator(entries=[AccumulatorEntry(
        pattern_id="p1", name="P1", category="cat", target_stage="search",
        domain_tags=["civic"], sessions_seen=2, sessions_since_last_seen=3,
        status="hold", raised_bar=False, promotion_pending=False, demotion_count=0,
        evidence=[{"case_id": "c0", "signal": "..."}],
        proposed_promotion_body="body",
        created_at="2026-05-20T00:00:00Z",
        last_updated_at="2026-05-22T00:00:00Z",
    )])
    record_observation(
        acc, pattern_id="p1", name="P1", category="cat", target_stage="search",
        domain_tags=["civic"],
        evidence_row={"case_id": "c1", "signal": "new"},
        proposed_promotion_body="body",
    )
    assert acc.entries[0].sessions_seen == 3
    assert acc.entries[0].sessions_since_last_seen == 0
    assert len(acc.entries[0].evidence) == 2


def test_tick_staleness_increments_unobserved():
    """tick_staleness increments sessions_since_last_seen for entries not in the
    seen_set, leaves others alone."""
    from accumulator import Accumulator, AccumulatorEntry, tick_staleness
    e1 = AccumulatorEntry(pattern_id="p1", name="", category="", target_stage="",
                          domain_tags=[], sessions_seen=1, sessions_since_last_seen=0,
                          status="hold", raised_bar=False, promotion_pending=False,
                          demotion_count=0, evidence=[], proposed_promotion_body="",
                          created_at="", last_updated_at="")
    e2 = AccumulatorEntry(pattern_id="p2", name="", category="", target_stage="",
                          domain_tags=[], sessions_seen=1, sessions_since_last_seen=2,
                          status="hold", raised_bar=False, promotion_pending=False,
                          demotion_count=0, evidence=[], proposed_promotion_body="",
                          created_at="", last_updated_at="")
    acc = Accumulator(entries=[e1, e2])
    tick_staleness(acc, seen_pattern_ids={"p1"})
    assert acc.entries[0].sessions_since_last_seen == 0  # p1 observed
    assert acc.entries[1].sessions_since_last_seen == 3  # p2 not observed


def test_record_observation_skips_rejected_entries():
    """record_observation is a no-op for entries with status=rejected."""
    from accumulator import Accumulator, AccumulatorEntry, record_observation
    rejected = AccumulatorEntry(
        pattern_id="p1", name="", category="", target_stage="",
        domain_tags=[], sessions_seen=10, sessions_since_last_seen=0,
        status="rejected", raised_bar=False, promotion_pending=False,
        demotion_count=0, evidence=[],
        proposed_promotion_body="",
        created_at="", last_updated_at="",
    )
    acc = Accumulator(entries=[rejected])
    record_observation(
        acc, pattern_id="p1", name="", category="", target_stage="",
        domain_tags=[], evidence_row={"case_id": "c", "signal": "x"},
        proposed_promotion_body="",
    )
    # sessions_seen unchanged, no new evidence row
    assert acc.entries[0].sessions_seen == 10
    assert acc.entries[0].evidence == []


def test_mark_rejected_sets_status():
    """mark_rejected sets status=rejected, clears promotion_pending."""
    from accumulator import Accumulator, AccumulatorEntry, mark_rejected
    e = AccumulatorEntry(
        pattern_id="p1", name="", category="", target_stage="",
        domain_tags=[], sessions_seen=3, sessions_since_last_seen=0,
        status="promotion_pending", raised_bar=False, promotion_pending=True,
        demotion_count=0, evidence=[],
        proposed_promotion_body="",
        created_at="", last_updated_at="",
    )
    acc = Accumulator(entries=[e])
    mark_rejected(acc, pattern_id="p1")
    assert acc.entries[0].status == "rejected"
    assert acc.entries[0].promotion_pending is False


def test_mark_promotion_pending():
    from accumulator import Accumulator, AccumulatorEntry, mark_promotion_pending
    e = AccumulatorEntry(
        pattern_id="p1", name="", category="", target_stage="",
        domain_tags=[], sessions_seen=3, sessions_since_last_seen=0,
        status="hold", raised_bar=False, promotion_pending=False,
        demotion_count=0, evidence=[], proposed_promotion_body="",
        created_at="", last_updated_at="",
    )
    acc = Accumulator(entries=[e])
    mark_promotion_pending(acc, "p1")
    assert acc.entries[0].promotion_pending is True
    assert acc.entries[0].status == "promotion_pending"


def test_clear_promotion_pending_returns_to_hold():
    """clear_promotion_pending sets status back to hold without deciding."""
    from accumulator import Accumulator, AccumulatorEntry, clear_promotion_pending
    e = AccumulatorEntry(
        pattern_id="p1", name="", category="", target_stage="",
        domain_tags=[], sessions_seen=3, sessions_since_last_seen=0,
        status="promotion_pending", raised_bar=False, promotion_pending=True,
        demotion_count=0, evidence=[], proposed_promotion_body="",
        created_at="", last_updated_at="",
    )
    acc = Accumulator(entries=[e])
    clear_promotion_pending(acc, "p1")
    assert acc.entries[0].status == "hold"
    assert acc.entries[0].promotion_pending is False


def test_remove_entry_for_graduation():
    """After successful promotion to learned_patterns.md, entry is removed."""
    from accumulator import Accumulator, AccumulatorEntry, remove_entry
    e = AccumulatorEntry(
        pattern_id="p1", name="", category="", target_stage="",
        domain_tags=[], sessions_seen=3, sessions_since_last_seen=0,
        status="promotion_pending", raised_bar=False, promotion_pending=True,
        demotion_count=0, evidence=[], proposed_promotion_body="",
        created_at="", last_updated_at="",
    )
    acc = Accumulator(entries=[e])
    remove_entry(acc, "p1")
    assert len(acc.entries) == 0


def test_demote_first_time_returns_to_hold_with_raised_bar():
    """First demotion: status=hold, raised_bar=True, demotion_count=1."""
    from accumulator import Accumulator, AccumulatorEntry, demote
    e = AccumulatorEntry(
        pattern_id="p1", name="", category="", target_stage="",
        domain_tags=[], sessions_seen=3, sessions_since_last_seen=0,
        status="hold", raised_bar=False, promotion_pending=False,
        demotion_count=0, evidence=[], proposed_promotion_body="",
        created_at="", last_updated_at="",
    )
    acc = Accumulator(entries=[e])
    demote(acc, "p1")
    assert acc.entries[0].status == "hold"
    assert acc.entries[0].raised_bar is True
    assert acc.entries[0].demotion_count == 1
    assert acc.entries[0].sessions_seen == 0  # reset for re-graduation count


def test_demote_second_time_marks_rejected():
    """Second demotion: status=rejected (permanent)."""
    from accumulator import Accumulator, AccumulatorEntry, demote
    e = AccumulatorEntry(
        pattern_id="p1", name="", category="", target_stage="",
        domain_tags=[], sessions_seen=5, sessions_since_last_seen=0,
        status="hold", raised_bar=True, promotion_pending=False,
        demotion_count=1, evidence=[], proposed_promotion_body="",
        created_at="", last_updated_at="",
    )
    acc = Accumulator(entries=[e])
    demote(acc, "p1")
    assert acc.entries[0].status == "rejected"
    assert acc.entries[0].demotion_count == 2
