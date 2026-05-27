# tests/test_state.py
"""Tests for state.py — pipeline state management."""

import json
import pytest
from pathlib import Path
from datetime import datetime, timezone


def test_create_run_writes_current_run(tmp_path):
    from state import create_run
    run = create_run(tmp_path, "sc-alpr", "mid")
    assert (tmp_path / "current_run.json").exists()
    assert run["run_id"] == "sc-alpr"
    assert run["stage"] == "triage"
    assert run["tier_detected"] == "mid"


def test_state_version_constant():
    from state import STATE_VERSION
    assert STATE_VERSION == 3


def test_create_run_writes_version(tmp_path):
    from state import create_run
    run = create_run(tmp_path, run_id="2026-05-26-test", tier="full")
    assert run["version"] == 3


def test_create_run_initial_stage_is_triage(tmp_path):
    from state import create_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    assert run["stage"] == "triage"


def test_create_run_fails_if_run_exists(tmp_path):
    from state import create_run
    create_run(tmp_path, "run1", "base")
    with pytest.raises(FileExistsError):
        create_run(tmp_path, "run2", "base")


def test_load_run_returns_none_when_no_run(tmp_path):
    from state import load_run
    assert load_run(tmp_path) is None


def test_load_run_returns_current_run(tmp_path):
    from state import create_run, load_run
    create_run(tmp_path, "test-run", "base")
    run = load_run(tmp_path)
    assert run["run_id"] == "test-run"


def test_update_stage_changes_stage(tmp_path):
    from state import create_run, update_stage, load_run
    create_run(tmp_path, "test", "base")
    update_stage(tmp_path, "search")
    run = load_run(tmp_path)
    assert run["stage"] == "search"


def test_save_stage_output_writes_atomically(tmp_path):
    from state import create_run, save_stage_output
    create_run(tmp_path, "test", "base")
    data = {"results": [1, 2, 3]}
    save_stage_output(tmp_path, "search_results", data)
    output_file = tmp_path / "search_results.json"
    assert output_file.exists()
    assert json.loads(output_file.read_text())["results"] == [1, 2, 3]


def test_load_stage_output_returns_none_when_missing(tmp_path):
    from state import load_stage_output
    assert load_stage_output(tmp_path, "search_results") is None


def test_load_stage_output_returns_data(tmp_path):
    from state import create_run, save_stage_output, load_stage_output
    create_run(tmp_path, "test", "base")
    save_stage_output(tmp_path, "fetch_results", {"data": "yes"})
    loaded = load_stage_output(tmp_path, "fetch_results")
    assert loaded["data"] == "yes"


def test_append_written_note(tmp_path):
    from state import create_run, append_written_note, load_stage_output
    create_run(tmp_path, "test", "base")
    append_written_note(tmp_path, "Greenville ALPR", "Projects/Surveillance/Greenville.md", "sonnet")
    append_written_note(tmp_path, "Charleston ALPR", "Projects/Surveillance/Charleston.md", "sonnet")
    written = load_stage_output(tmp_path, "written_notes")
    assert len(written["completed"]) == 2
    assert written["completed"][0]["topic"] == "Greenville ALPR"


def test_abandon_run_archives_state(tmp_path):
    from state import create_run, save_stage_output, abandon_run, load_run
    create_run(tmp_path, "old-run", "base")
    save_stage_output(tmp_path, "search_results", {"data": True})
    abandon_run(tmp_path)
    assert load_run(tmp_path) is None
    history_dir = tmp_path / "history" / "old-run"
    assert history_dir.exists()
    assert (history_dir / "current_run.json").exists()
    assert (history_dir / "search_results.json").exists()


def test_complete_run_archives_state(tmp_path):
    from state import create_run, complete_run, load_run
    create_run(tmp_path, "done-run", "base")
    complete_run(tmp_path)
    assert load_run(tmp_path) is None
    history_dir = tmp_path / "history" / "done-run"
    assert history_dir.exists()


def test_is_stale_run(tmp_path):
    from state import create_run, is_stale_run
    create_run(tmp_path, "test", "base")
    assert is_stale_run(tmp_path, max_age_hours=24) is False


def test_load_run_drops_old_schema(tmp_path, capsys):
    from state import load_run
    # Write a fake v2-era state file
    state_file = tmp_path / "current_run.json"
    state_file.write_text(json.dumps({"run_id": "old", "version": 2, "tier": "full"}))
    result = load_run(tmp_path)
    assert result is None
    err = capsys.readouterr().err   # message goes to stderr (see implementation)
    assert "older schema" in err.lower()
    # The state file should have been moved out (abandoned to history/)
    assert not (tmp_path / "current_run.json").exists()


def test_load_run_drops_missing_version(tmp_path, capsys):
    from state import load_run
    state_file = tmp_path / "current_run.json"
    state_file.write_text(json.dumps({"run_id": "old", "tier": "full"}))  # no version
    result = load_run(tmp_path)
    assert result is None


def test_create_run_topic_initialization(tmp_path):
    from state import create_run, init_topic
    run = create_run(tmp_path, run_id="r1", tier="full")
    topic = init_topic("SC ALPR programs", mode="web_research", depth="standard")
    assert topic == {
        "topic": "SC ALPR programs",
        "mode": "web_research",
        "depth": "standard",
        "max_hops": 3,
        "current_hop": 0,
        "status": "active",
        "hop_genealogy": [],
        "confidence_history": [],
        "contradiction_rate": 0.0,
        "seen_urls": [],
        "replan_hint": None,
        "next_hop": None,
    }


def test_record_hop_appends_to_genealogy(tmp_path):
    from state import create_run, init_topic, record_hop, save_state
    run = create_run(tmp_path, run_id="r1", tier="full")
    topic = init_topic("X", mode="web_research", depth="standard")
    run["topics"] = [topic]
    save_state(tmp_path, run)

    hop_data = {
        "hop": 1,
        "pattern": None,
        "queries": ["q1"],
        "sources_found": 12,
        "sources_kept": 7,
        "ended_at": "2026-05-26T14:25:00Z",
    }
    record_hop(tmp_path, topic_name="X", hop_data=hop_data)

    from state import load_run
    reloaded = load_run(tmp_path)
    assert reloaded["topics"][0]["hop_genealogy"] == [hop_data]
    assert reloaded["topics"][0]["current_hop"] == 1


def test_mark_topic_status(tmp_path):
    from state import create_run, init_topic, mark_topic_status, save_state, load_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    run["topics"] = [init_topic("X", mode="web_research", depth="standard")]
    save_state(tmp_path, run)

    mark_topic_status(tmp_path, topic_name="X", status="complete")
    assert load_run(tmp_path)["topics"][0]["status"] == "complete"


def test_append_confidence(tmp_path):
    from state import create_run, init_topic, append_confidence, save_state, load_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    run["topics"] = [init_topic("X", mode="web_research", depth="standard")]
    save_state(tmp_path, run)

    append_confidence(tmp_path, topic_name="X", score=0.42)
    append_confidence(tmp_path, topic_name="X", score=0.71)
    assert load_run(tmp_path)["topics"][0]["confidence_history"] == [0.42, 0.71]


def test_set_contradiction_rate(tmp_path):
    from state import create_run, init_topic, set_contradiction_rate, save_state, load_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    run["topics"] = [init_topic("X", mode="web_research", depth="standard")]
    save_state(tmp_path, run)

    set_contradiction_rate(tmp_path, topic_name="X", rate=0.18)
    assert load_run(tmp_path)["topics"][0]["contradiction_rate"] == 0.18

    # Overwrites with newer value
    set_contradiction_rate(tmp_path, topic_name="X", rate=0.32)
    assert load_run(tmp_path)["topics"][0]["contradiction_rate"] == 0.32


def test_set_replan_hint(tmp_path):
    from state import create_run, init_topic, set_replan_hint, save_state, load_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    run["topics"] = [init_topic("X", mode="web_research", depth="standard")]
    save_state(tmp_path, run)

    hint = {"issue": "thin sources", "suggested_pattern": "entity_expansion",
            "suggested_query_focus": "official agency data"}
    set_replan_hint(tmp_path, topic_name="X", hint=hint)
    assert load_run(tmp_path)["topics"][0]["replan_hint"] == hint


def test_bump_max_hops(tmp_path):
    """Bumping max_hops lets a topic re-enter the hop loop after exhausting its budget."""
    from state import create_run, init_topic, bump_max_hops, save_state, load_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    run["topics"] = [init_topic("X", mode="web_research", depth="standard")]  # max_hops=3
    save_state(tmp_path, run)

    bump_max_hops(tmp_path, topic_name="X", increment=1)
    assert load_run(tmp_path)["topics"][0]["max_hops"] == 4


def test_add_seen_urls_appends_dedup(tmp_path):
    """add_seen_urls preserves order, skips duplicates, can be called repeatedly."""
    from state import create_run, init_topic, add_seen_urls, save_state, load_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    run["topics"] = [init_topic("X", mode="web_research", depth="standard")]
    save_state(tmp_path, run)

    add_seen_urls(tmp_path, topic_name="X", urls=["https://a", "https://b"])
    add_seen_urls(tmp_path, topic_name="X", urls=["https://b", "https://c"])  # b is dup

    assert load_run(tmp_path)["topics"][0]["seen_urls"] == ["https://a", "https://b", "https://c"]


def test_add_seen_urls_unknown_topic_raises(tmp_path):
    import pytest
    from state import create_run, init_topic, save_state, add_seen_urls
    run = create_run(tmp_path, run_id="r1", tier="full")
    run["topics"] = [init_topic("X", mode="web_research", depth="standard")]
    save_state(tmp_path, run)

    with pytest.raises(KeyError, match="Topic not found"):
        add_seen_urls(tmp_path, topic_name="missing", urls=["https://a"])


def test_apply_hop_decision_continue_is_atomic(tmp_path):
    """apply_hop_decision applies hop record + routing + quality signals + status in one save."""
    from state import create_run, init_topic, save_state, apply_hop_decision, load_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    topic = init_topic("X", mode="web_research", depth="standard")
    topic["replan_hint"] = {"issue": "stale"}  # simulate a prior replan
    run["topics"] = [topic]
    save_state(tmp_path, run)

    hop_data = {"hop": 1, "pattern": None, "queries": [], "sources_kept": 5,
                "ended_at": "2026-05-26T15:00:00Z"}
    next_hop = {"pattern": "entity_expansion", "from": "Flock Safety", "rationale": "..."}
    apply_hop_decision(tmp_path, topic_name="X", hop_data=hop_data,
                       decision="continue", confidence_score=0.68,
                       contradiction_rate=0.12, next_hop=next_hop)

    t = load_run(tmp_path)["topics"][0]
    assert t["hop_genealogy"] == [hop_data]
    assert t["current_hop"] == 1
    assert t["confidence_history"] == [0.68]
    assert t["contradiction_rate"] == 0.12
    assert t["next_hop"] == next_hop
    assert t["replan_hint"] is None  # cleared atomically
    assert t["status"] == "active"


def test_apply_hop_decision_stop_marks_complete(tmp_path):
    from state import create_run, init_topic, save_state, apply_hop_decision, load_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    run["topics"] = [init_topic("X", mode="web_research", depth="standard")]
    save_state(tmp_path, run)

    apply_hop_decision(tmp_path, topic_name="X",
                       hop_data={"hop": 1, "ended_at": "..."},
                       decision="stop", confidence_score=0.82,
                       contradiction_rate=0.05)

    t = load_run(tmp_path)["topics"][0]
    assert t["current_hop"] == 1
    assert t["confidence_history"] == [0.82]
    assert t["contradiction_rate"] == 0.05
    assert t["next_hop"] is None
    assert t["status"] == "complete"


def test_apply_hop_decision_replan_stores_hint(tmp_path):
    from state import create_run, init_topic, save_state, apply_hop_decision, load_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    run["topics"] = [init_topic("X", mode="web_research", depth="standard")]
    save_state(tmp_path, run)

    hint = {"issue": "thin sources", "suggested_pattern": "entity_expansion",
            "suggested_query_focus": "official data"}
    apply_hop_decision(tmp_path, topic_name="X",
                       hop_data={"hop": 1, "ended_at": "..."},
                       decision="replan", confidence_score=0.41,
                       contradiction_rate=0.38, replan_hint=hint)

    t = load_run(tmp_path)["topics"][0]
    assert t["current_hop"] == 1
    assert t["confidence_history"] == [0.41]
    assert t["contradiction_rate"] == 0.38
    assert t["next_hop"] is None
    assert t["replan_hint"] == hint
    assert t["status"] == "replan_pending"


def test_apply_hop_decision_unknown_raises(tmp_path):
    from state import create_run, init_topic, save_state, apply_hop_decision
    run = create_run(tmp_path, run_id="r1", tier="full")
    run["topics"] = [init_topic("X", mode="web_research", depth="standard")]
    save_state(tmp_path, run)

    with pytest.raises(ValueError, match="Unknown decision"):
        apply_hop_decision(tmp_path, topic_name="X",
                           hop_data={"hop": 1},
                           decision="bogus",
                           confidence_score=0.0, contradiction_rate=0.0)


def test_add_usage_starts_at_zero(tmp_path):
    from state import create_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    assert run["usage"] == {
        "haiku":  {"calls": 0, "in_tokens": 0, "out_tokens": 0},
        "sonnet": {"calls": 0, "in_tokens": 0, "out_tokens": 0},
        "opus":   {"calls": 0, "in_tokens": 0, "out_tokens": 0},
        "ollama": {"calls": 0},
    }


def test_add_usage_accumulates(tmp_path):
    from state import create_run, add_usage, load_run, save_state
    run = create_run(tmp_path, run_id="r1", tier="full")
    save_state(tmp_path, run)

    add_usage(tmp_path, model="haiku", in_tokens=1000, out_tokens=200, stage="search")
    add_usage(tmp_path, model="haiku", in_tokens=500,  out_tokens=100, stage="summarize")
    add_usage(tmp_path, model="ollama", in_tokens=0, out_tokens=0, stage="summarize")

    usage = load_run(tmp_path)["usage"]
    assert usage["haiku"] == {"calls": 2, "in_tokens": 1500, "out_tokens": 300}
    assert usage["ollama"]["calls"] == 1


def test_replan_count_starts_at_zero(tmp_path):
    from state import create_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    assert run["replan_count"] == 0
    assert run["user_decisions"] == []


def test_increment_replan(tmp_path):
    from state import create_run, save_state, increment_replan, load_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    save_state(tmp_path, run)
    increment_replan(tmp_path)
    increment_replan(tmp_path)
    assert load_run(tmp_path)["replan_count"] == 2


def test_record_user_decision(tmp_path):
    from state import create_run, save_state, record_user_decision, load_run
    run = create_run(tmp_path, run_id="r1", tier="full")
    save_state(tmp_path, run)
    record_user_decision(tmp_path, decision="continue_anyway", confidence=0.52)
    decisions = load_run(tmp_path)["user_decisions"]
    assert len(decisions) == 1
    assert decisions[0]["decision"] == "continue_anyway"
    assert decisions[0]["confidence"] == 0.52
    assert "at" in decisions[0]


def test_record_user_decision_rejects_reserved_keys(tmp_path):
    """Caller-supplied 'decision' or 'at' in **details would silently override canonical fields."""
    import pytest
    from state import create_run, save_state, record_user_decision
    run = create_run(tmp_path, run_id="r1", tier="full")
    save_state(tmp_path, run)

    with pytest.raises(TypeError, match="reserved keys"):
        record_user_decision(tmp_path, decision="continue", at="2020-01-01T00:00:00Z")


def test_add_usage_rejects_unknown_model(tmp_path):
    """Typos in model name (e.g. 'haku') would create ghost buckets — guard at the call site."""
    import pytest
    from state import create_run, save_state, add_usage
    run = create_run(tmp_path, run_id="r1", tier="full")
    save_state(tmp_path, run)

    with pytest.raises(ValueError, match="unknown model"):
        add_usage(tmp_path, model="haku", in_tokens=100, out_tokens=10, stage="search")


def test_abandon_run_sweeps_hop_intermediate_files(tmp_path):
    from state import create_run, abandon_run
    create_run(tmp_path, run_id="2026-05-26-hop-test", tier="full")

    # Simulate per-hop intermediate files
    (tmp_path / "fetch_results_hop1.json").write_text("{}")
    (tmp_path / "fetch_results_hop2.json").write_text("{}")
    (tmp_path / "summaries_hop1.json").write_text("{}")
    (tmp_path / "search_context_hop1.json").write_text("{}")

    abandon_run(tmp_path)

    # All per-hop files land alongside current_run.json under history/{run_id}/
    history_dir = tmp_path / "history" / "2026-05-26-hop-test"
    assert history_dir.exists()
    assert (history_dir / "fetch_results_hop1.json").exists()
    assert (history_dir / "fetch_results_hop2.json").exists()
    assert (history_dir / "summaries_hop1.json").exists()
    assert (history_dir / "search_context_hop1.json").exists()
    # Active run file should be gone
    assert not (tmp_path / "current_run.json").exists()


def test_complete_run_returns_run_data(tmp_path):
    from state import create_run, complete_run
    create_run(tmp_path, run_id="2026-05-26-complete-test", tier="full")

    result = complete_run(tmp_path)

    assert result is not None
    assert result["run_id"] == "2026-05-26-complete-test"
    assert "completed_at" in result
    # The file is gone (archived)
    assert not (tmp_path / "current_run.json").exists()


def test_write_case_record(tmp_path):
    from state import write_case_record
    case_data = {
        "case_id": "2026-05-26-test",
        "version": 1,
        "query": "test research",
        "domain_tags": ["test"],
        "outcomes": {"sources_processed": 5},
    }
    # cases_dir is .research-workflow/cases under the vault root
    cases_dir = tmp_path / "cases"
    write_case_record(cases_dir, case_data)

    case_file = cases_dir / "2026-05-26-test.json"
    assert case_file.exists()
    assert json.loads(case_file.read_text()) == case_data
