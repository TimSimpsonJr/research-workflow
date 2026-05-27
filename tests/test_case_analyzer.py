import json
from pathlib import Path
import pytest


def test_analyze_empty_state_returns_empty_result(tmp_path):
    """Empty accumulator + empty learned_patterns + no cases: zero candidates."""
    from case_analyzer import analyze
    case_path = tmp_path / "case.json"
    case_path.write_text(json.dumps({
        "case_id": "c1",
        "domain_tags": ["civic"],
        "applied_patterns": [],
        "confidence_per_topic": {"t": 0.8},
        "contradiction_rate": 0.1,
        "outcomes": {"user_decisions": []},
        "patterns_that_worked": {"source_tiers": {"T1": 5}, "hop_chain": ["entity_expansion"]},
    }))
    result = analyze(
        case_path=case_path,
        accumulator_path=tmp_path / "accumulator.json",
        learned_patterns_path=tmp_path / "learned_patterns.md",
        cases_dir=tmp_path,
        cases_window=20,
    )
    assert result.promotion_candidates == []
    assert result.warnings == []


def test_analyze_civic_alpr_cases_produces_promotion_candidates(tmp_path):
    """With civic_alpr cases, expect at least one promotion candidate to surface
    after enough runs to cross promotion_threshold (default 3)."""
    from case_analyzer import analyze

    fixture_path = Path("tests/fixtures/case_learning/civic_alpr_cases.json")
    cases = json.loads(fixture_path.read_text())
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    for c in cases:
        (cases_dir / f"{c['case_id']}.json").write_text(json.dumps(c))

    # Drive 3 runs through the analyzer to build sessions_seen
    result = None
    for i in range(3):
        result = analyze(
            case_path=cases_dir / f"{cases[i]['case_id']}.json",
            accumulator_path=tmp_path / "accumulator.json",
            learned_patterns_path=tmp_path / "learned_patterns.md",
            cases_dir=cases_dir,
            cases_window=20,
        )

    # After 3 runs, at least one civic-alpr candidate should be eligible
    assert len(result.promotion_candidates) >= 1
    civic = [c for c in result.promotion_candidates if "civic" in c.domain_tags]
    assert len(civic) >= 1


def test_semantic_merge_uses_existing_pattern_id_on_haiku_match(tmp_path):
    """When a heuristic candidate has the same (domain, category) as an
    existing accumulator entry but a different stable_key, and the Haiku
    semantic-compare returns is_same=True, the analyzer reuses the existing
    pattern_id so sessions_seen accumulates on the right entry."""
    from case_analyzer import analyze
    from accumulator import Accumulator, AccumulatorEntry, save_accumulator
    from datetime import datetime, timezone

    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    acc_path = tmp_path / "accumulator.json"
    lp_path = tmp_path / "learned_patterns.md"

    # Seed accumulator with a pre-existing entry in the civic-alpr / source-tier-bias
    # bucket under pattern_id "existing-pid"
    now = datetime.now(timezone.utc).isoformat()
    save_accumulator(acc_path, Accumulator(entries=[
        AccumulatorEntry(
            pattern_id="existing-pid", name="Existing T1 pattern", category="source-tier-bias",
            target_stage="search", domain_tags=["civic", "alpr"],
            sessions_seen=1, sessions_since_last_seen=0, status="hold",
            raised_bar=False, promotion_pending=False, demotion_count=0,
            evidence=[{"case_id": "c0", "signal": "T1=5/8"}],
            proposed_promotion_body="T1 dominance for civic ALPR", created_at=now,
            last_updated_at=now,
        ),
    ]))

    # Synthesize a case that will produce a "T1 dominant for civic/alpr" candidate
    # under a different generated pattern_id. The heuristic needs >= min_cases=3
    # cases to fire, so we write 3 case files.
    case_template = {
        "domain_tags": ["civic", "alpr"], "applied_patterns": [],
        "confidence_per_topic": {"t": 0.82}, "contradiction_rate": 0.1,
        "outcomes": {"user_decisions": []},
        "patterns_that_worked": {
            "source_tiers": {"T1": 8, "T2": 1}, "hop_chain": ["entity_expansion"],
            "queries": [],
        },
    }
    for i in range(3):
        case = {**case_template, "case_id": f"c{i}"}
        (cases_dir / f"c{i}.json").write_text(json.dumps(case))
    case_path = cases_dir / "c0.json"

    # Haiku mock returns is_same=True for any compare
    def fake_haiku(*, candidate_body, existing_body):
        return {"is_same": True, "reason": "mock match"}

    result = analyze(
        case_path=case_path,
        accumulator_path=acc_path,
        learned_patterns_path=lp_path,
        cases_dir=cases_dir,
        haiku_dispatch=fake_haiku,
    )

    # Reload accumulator and verify the new evidence merged onto "existing-pid",
    # not a fresh pattern_id
    from accumulator import load_accumulator
    acc, _ = load_accumulator(acc_path)
    existing = next(e for e in acc.entries if e.pattern_id == "existing-pid")
    assert existing.sessions_seen >= 2, "existing-pid should have accumulated"


def test_semantic_merge_disabled_when_haiku_none(tmp_path):
    """When haiku_dispatch is None, no semantic merge occurs — heuristic
    candidates always use their own pattern_id (conservative default)."""
    from case_analyzer import analyze
    from accumulator import Accumulator, AccumulatorEntry, save_accumulator, load_accumulator
    from datetime import datetime, timezone

    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    acc_path = tmp_path / "accumulator.json"
    lp_path = tmp_path / "learned_patterns.md"

    # Same scaffolding as the haiku-match test
    now = datetime.now(timezone.utc).isoformat()
    save_accumulator(acc_path, Accumulator(entries=[
        AccumulatorEntry(
            pattern_id="existing-pid", name="Existing T1 pattern", category="source-tier-bias",
            target_stage="search", domain_tags=["civic", "alpr"],
            sessions_seen=1, sessions_since_last_seen=0, status="hold",
            raised_bar=False, promotion_pending=False, demotion_count=0,
            evidence=[{"case_id": "c0", "signal": "T1=5/8"}],
            proposed_promotion_body="T1 dominance for civic ALPR", created_at=now,
            last_updated_at=now,
        ),
    ]))

    case_template = {
        "domain_tags": ["civic", "alpr"], "applied_patterns": [],
        "confidence_per_topic": {"t": 0.82}, "contradiction_rate": 0.1,
        "outcomes": {"user_decisions": []},
        "patterns_that_worked": {
            "source_tiers": {"T1": 8, "T2": 1}, "hop_chain": ["entity_expansion"],
            "queries": [],
        },
    }
    for i in range(3):
        case = {**case_template, "case_id": f"c{i}"}
        (cases_dir / f"c{i}.json").write_text(json.dumps(case))

    result = analyze(
        case_path=cases_dir / "c0.json",
        accumulator_path=acc_path,
        learned_patterns_path=lp_path,
        cases_dir=cases_dir,
        haiku_dispatch=None,  # explicit None — no semantic merge
    )

    # Verify the heuristic-generated pattern_id is DIFFERENT from existing-pid
    # — meaning the analyzer created a separate accumulator entry
    acc, _ = load_accumulator(acc_path)
    pids = {e.pattern_id for e in acc.entries}
    assert "existing-pid" in pids
    assert len(pids) >= 2, "should have created a fresh entry alongside existing-pid"


def test_contradiction_flagged_at_promotion_time(tmp_path):
    """When an accumulator entry becomes promotion-eligible and the same
    (domain, target_stage) bucket already has a graduated pattern in
    learned_patterns.md, the analyzer flags it in result.contradictions."""
    from case_analyzer import analyze
    from accumulator import Accumulator, AccumulatorEntry, save_accumulator
    from learned_patterns import LearnedPatternsFile, LearnedPattern, save_learned_patterns
    from datetime import datetime, timezone

    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    acc_path = tmp_path / "accumulator.json"
    lp_path = tmp_path / "learned_patterns.md"
    now = datetime.now(timezone.utc).isoformat()

    # Seed a graduated pattern in learned_patterns.md
    save_learned_patterns(lp_path, LearnedPatternsFile(patterns=[
        LearnedPattern(
            id="graduated-pid", name="Use broad queries for tech",
            body="Broad queries outperform narrow.", domain_tags=["tech"],
            target_stage="search", category="query-template",
            wins=8, losses=1, promoted_at="2026-04-01", demotion_count=0,
        ),
    ]))

    # Seed an accumulator entry already at promotion threshold for the same bucket
    save_accumulator(acc_path, Accumulator(entries=[
        AccumulatorEntry(
            pattern_id="candidate-pid", name="Use narrow queries for tech",
            category="query-template", target_stage="search",
            domain_tags=["tech"], sessions_seen=3, sessions_since_last_seen=0,
            status="hold", raised_bar=False, promotion_pending=False, demotion_count=0,
            evidence=[{"case_id": "c0", "signal": "narrow=5/6"}],
            proposed_promotion_body="Narrow queries outperform broad.",
            created_at=now, last_updated_at=now,
        ),
    ]))

    # Drive analyze() — does NOT need to produce new candidates; we just need
    # the existing accumulator entry to hit the promotion-eligibility check.
    case = {
        "case_id": "c1", "domain_tags": ["tech"], "applied_patterns": [],
        "confidence_per_topic": {"t": 0.8}, "contradiction_rate": 0.1,
        "outcomes": {"user_decisions": []},
        "patterns_that_worked": {"source_tiers": {}, "hop_chain": [], "queries": []},
    }
    (cases_dir / "c1.json").write_text(json.dumps(case))
    result = analyze(
        case_path=cases_dir / "c1.json",
        accumulator_path=acc_path,
        learned_patterns_path=lp_path,
        cases_dir=cases_dir,
    )

    assert len(result.promotion_candidates) == 1
    assert result.promotion_candidates[0].pattern_id == "candidate-pid"
    assert len(result.contradictions) == 1
    contradiction = result.contradictions[0]
    assert contradiction["candidate_pattern_id"] == "candidate-pid"
    assert "graduated-pid" in contradiction["conflicting_graduated_ids"]


def test_demote_syncs_count_when_existing_entry_is_fresh(tmp_path):
    """When learned_pattern.demotion_count exceeds existing accumulator
    entry's demotion_count (e.g., because record_observation recreated the
    entry after re-graduation), demote() must still honor the higher count
    so the 2nd-demotion -> rejected rule fires.

    Regression for the latent bug surfaced in Phase 9's Task 9.2 trajectory test.
    """
    from case_analyzer import analyze
    from accumulator import Accumulator, AccumulatorEntry, save_accumulator, load_accumulator
    from learned_patterns import LearnedPatternsFile, LearnedPattern, save_learned_patterns
    from datetime import datetime, timezone

    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    acc_path = tmp_path / "accumulator.json"
    lp_path = tmp_path / "learned_patterns.md"
    now = datetime.now(timezone.utc).isoformat()
    pid = "test-pattern-id"

    # Seed learned_patterns: pattern P with demotion_count=1 (previously demoted, re-graduated)
    # AND scored badly (low W/L ratio, will trigger demotion sweep)
    save_learned_patterns(lp_path, LearnedPatternsFile(patterns=[
        LearnedPattern(
            id=pid, name="Test pattern", body="body",
            domain_tags=["mixed"], target_stage="search", category="source-tier-bias",
            wins=1, losses=10,  # ratio 1/11 = 0.09 < 0.4 -> demote
            promoted_at="2026-05-01", demotion_count=1,
        ),
    ]))

    # Seed accumulator: P entry has demotion_count=0 (fresh — record_observation
    # recreated it after re-graduation)
    save_accumulator(acc_path, Accumulator(entries=[
        AccumulatorEntry(
            pattern_id=pid, name="Test pattern", category="source-tier-bias",
            target_stage="search", domain_tags=["mixed"],
            sessions_seen=1, sessions_since_last_seen=0, status="hold",
            raised_bar=False, promotion_pending=False, demotion_count=0,
            evidence=[], proposed_promotion_body="body",
            created_at=now, last_updated_at=now,
        ),
    ]))

    # Drive analyzer with a minimal case
    case = {
        "case_id": "c1", "domain_tags": ["other"], "applied_patterns": [],
        "confidence_per_topic": {"t": 0.8}, "contradiction_rate": 0.1,
        "outcomes": {"user_decisions": []},
        "patterns_that_worked": {"source_tiers": {}, "hop_chain": [], "queries": []},
    }
    import json
    (cases_dir / "c1.json").write_text(json.dumps(case))
    result = analyze(
        case_path=cases_dir / "c1.json",
        accumulator_path=acc_path, learned_patterns_path=lp_path,
        cases_dir=cases_dir,
    )

    # Should have demoted exactly once
    assert result.demotions_applied == 1
    # And the accumulator entry should now be at status="rejected"
    # (1 + 1 = 2 -> permanent retirement)
    acc, _ = load_accumulator(acc_path)
    entry = next(e for e in acc.entries if e.pattern_id == pid)
    assert entry.status == "rejected", \
        f"expected status='rejected' (demotion_count synced from 0 to 1, then demote() -> 2), got {entry.status!r}"
    assert entry.demotion_count == 2
