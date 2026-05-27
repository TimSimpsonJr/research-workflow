"""State-mechanics test for the multi-hop research pipeline.

This is NOT a full orchestrator integration test - the orchestrator (SKILL.md)
runs inside Claude Code's slash-command machinery, which has no Python harness.
Instead, this test drives the Python state helpers (state.py, confidence.py)
through the same sequence the orchestrator would, using fixture JSON for the
agent responses to validate the JSON contracts.
"""
import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "research_integration"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


def test_fixtures_parse_into_expected_shapes():
    """Each agent fixture parses and has the keys the orchestrator depends on."""
    resolver = load_fixture("topic_resolver_response.json")
    assert resolver["strategy"] in {"planning_only", "intent_planning", "unified"}
    assert all(t["depth"] in {"quick", "standard", "deep", "exhaustive"}
               for t in resolver["topics"])

    search = load_fixture("search_hop1_topic0.json")
    for url in search["selected_urls"]:
        assert url["tier"] in {"T1", "T2", "T3", "T4"}
        assert 0.0 <= url["credibility_score"] <= 1.0
        assert isinstance(url["is_primary"], bool)

    planner = load_fixture("hop_planner_topic0_hop1.json")
    assert planner["decision"] in {"continue", "stop", "replan"}

    # Replan-path fixture: pins the alternate decision shape so a contract drift
    # on replan_hint would be caught even though the stop-decision fixture above
    # never exercises it.
    planner_replan = load_fixture("hop_planner_topic0_hop1_replan.json")
    assert planner_replan["decision"] == "replan"
    assert "replan_hint" in planner_replan
    assert {"issue", "suggested_pattern", "suggested_query_focus"} <= planner_replan["replan_hint"].keys()

    classify = load_fixture("classify_response.json")
    assert "contradictions_detected" in classify


def test_quick_depth_run_via_state_helpers(tmp_path):
    """Drives state.py the way Stage 4 would for a quick-depth single-topic run."""
    from state import (
        create_run, init_topic, save_state, record_hop, append_confidence,
        mark_topic_status, load_run,
    )
    from confidence import compute_confidence

    state_dir = tmp_path / "state"
    state_dir.mkdir()

    run = create_run(state_dir, run_id="test-quick-run", tier="full")
    topic = init_topic("Test topic", mode="web_research", depth="quick")
    run["topics"] = [topic]
    save_state(state_dir, run)

    sources = [
        {"tier": "T1", "is_primary": True},
        {"tier": "T2", "is_primary": False},
        {"tier": "T2", "is_primary": False},
    ]
    score = compute_confidence(sources, depth="quick")
    assert score > 0.0

    hop_data = {
        "hop": 1, "pattern": None, "queries": ["q"],
        "sources_found": 3, "sources_kept": 3,
        "ended_at": "2026-05-26T15:00:00Z",
    }
    record_hop(state_dir, topic_name="Test topic", hop_data=hop_data)
    append_confidence(state_dir, topic_name="Test topic", score=score)
    mark_topic_status(state_dir, topic_name="Test topic", status="complete")

    final = load_run(state_dir)
    assert final["topics"][0]["status"] == "complete"
    assert final["topics"][0]["current_hop"] == 1
    assert final["topics"][0]["confidence_history"] == [score]
    assert len(final["topics"][0]["hop_genealogy"]) == 1


def test_replan_increments_count(tmp_path):
    from state import create_run, init_topic, save_state, increment_replan, load_run

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    run = create_run(state_dir, run_id="test-replan-run", tier="full")
    run["topics"] = [init_topic("T", mode="web_research", depth="standard")]
    save_state(state_dir, run)

    increment_replan(state_dir)
    increment_replan(state_dir)

    final = load_run(state_dir)
    assert final["replan_count"] == 2


def test_low_confidence_marks_run(tmp_path):
    from state import create_run, save_state, record_user_decision, load_run

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    run = create_run(state_dir, run_id="test-lowconf-run", tier="full")
    save_state(state_dir, run)

    record_user_decision(state_dir, decision="continue_anyway", confidence=0.52)
    run = load_run(state_dir)
    run["low_confidence"] = True
    run["final_confidence_score"] = 0.52
    save_state(state_dir, run)

    final = load_run(state_dir)
    assert final["low_confidence"] is True
    assert final["final_confidence_score"] == 0.52
    assert final["user_decisions"][0]["decision"] == "continue_anyway"
