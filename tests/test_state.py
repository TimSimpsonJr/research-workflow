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
    assert run["stage"] == "resolve"
    assert run["tier_detected"] == "mid"


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
