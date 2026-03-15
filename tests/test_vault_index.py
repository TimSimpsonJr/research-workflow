# tests/test_vault_index.py
"""Tests for vault_index.py — SQLite FTS5 vault index."""

import pytest
from pathlib import Path


def _create_note(vault: Path, rel_path: str, content: str, frontmatter: str = "") -> Path:
    """Helper: create a markdown note in the test vault."""
    full = vault / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    text = f"---\n{frontmatter}\n---\n{content}" if frontmatter else content
    full.write_text(text, encoding="utf-8")
    return full


def test_build_index_creates_db(tmp_path):
    from vault_index import build_index
    _create_note(tmp_path, "note1.md", "Some content about ALPR")
    db_path = build_index(tmp_path)
    assert db_path.exists()
    assert db_path.name == "vault_index.db"


def test_build_index_indexes_all_md_files(tmp_path):
    from vault_index import build_index, search
    _create_note(tmp_path, "Projects/note1.md", "ALPR surveillance")
    _create_note(tmp_path, "Projects/note2.md", "City council meeting")
    _create_note(tmp_path, "Inbox/note3.md", "Draft note")
    build_index(tmp_path)
    results = search(tmp_path, "surveillance")
    assert len(results) == 1
    assert "note1.md" in results[0]["path"]


def test_build_index_extracts_frontmatter_tags(tmp_path):
    from vault_index import build_index, search
    _create_note(tmp_path, "note.md", "Content here",
                 frontmatter="title: Test Note\ntags: [research, surveillance]")
    build_index(tmp_path)
    results = search(tmp_path, "surveillance")
    assert len(results) == 1
    assert "surveillance" in results[0]["tags"]


def test_search_returns_empty_for_no_match(tmp_path):
    from vault_index import build_index, search
    _create_note(tmp_path, "note.md", "Nothing relevant here")
    build_index(tmp_path)
    results = search(tmp_path, "quantum physics")
    assert len(results) == 0


def test_update_index_only_reindexes_changed_files(tmp_path):
    from vault_index import build_index, update_index, search
    _create_note(tmp_path, "note1.md", "Original content")
    build_index(tmp_path)
    # Modify one file, add another
    _create_note(tmp_path, "note1.md", "Updated content about ALPR")
    _create_note(tmp_path, "note2.md", "New note about surveillance")
    stats = update_index(tmp_path)
    assert stats["updated"] >= 1
    assert stats["added"] >= 1
    results = search(tmp_path, "ALPR")
    assert len(results) == 1


def test_search_by_title(tmp_path):
    from vault_index import build_index, search
    _create_note(tmp_path, "Greenville ALPR.md", "Content",
                 frontmatter="title: Greenville County ALPR Surveillance")
    build_index(tmp_path)
    results = search(tmp_path, "Greenville")
    assert len(results) == 1


def test_list_all_notes(tmp_path):
    from vault_index import build_index, list_notes
    _create_note(tmp_path, "a.md", "Note A")
    _create_note(tmp_path, "b.md", "Note B")
    _create_note(tmp_path, "sub/c.md", "Note C")
    build_index(tmp_path)
    notes = list_notes(tmp_path)
    assert len(notes) == 3


def test_index_skips_research_workflow_dir(tmp_path):
    from vault_index import build_index, list_notes
    _create_note(tmp_path, "real-note.md", "Keep me")
    _create_note(tmp_path, ".research-workflow/config.json", '{"test": true}')
    _create_note(tmp_path, ".research-workflow/state/run.json", '{}')
    build_index(tmp_path)
    notes = list_notes(tmp_path)
    paths = [n["path"] for n in notes]
    assert any("real-note" in p for p in paths)
    assert not any(".research-workflow" in p for p in paths)


def test_note_exists_by_title(tmp_path):
    from vault_index import build_index, note_exists
    _create_note(tmp_path, "ALPR.md", "Content",
                 frontmatter="title: Automatic License Plate Readers")
    build_index(tmp_path)
    assert note_exists(tmp_path, "Automatic License Plate Readers") is True
    assert note_exists(tmp_path, "Quantum Computing") is False


def test_search_matches_deep_body_text(tmp_path):
    """Full body is indexed, not just the first 500 chars."""
    from vault_index import build_index, search
    filler = "unrelated filler words " * 100  # push past 500 chars
    body = f"{filler}\nThe city deployed automatic license plate readers on Main Street."
    _create_note(tmp_path, "deep.md", body)
    build_index(tmp_path)
    results = search(tmp_path, "license plate")
    assert len(results) == 1
    assert "deep.md" in results[0]["path"]


def test_prefix_query_matches_morphological_variants(tmp_path):
    """Prefix matching: 'surveil' matches 'surveillance', 'surveilling', etc."""
    from vault_index import build_index, search
    _create_note(tmp_path, "a.md", "Police surveillance program launched")
    _create_note(tmp_path, "b.md", "Officers surveilling the intersection")
    _create_note(tmp_path, "c.md", "Nothing relevant here at all")
    build_index(tmp_path)
    results = search(tmp_path, "surveil")
    paths = [r["path"] for r in results]
    assert "a.md" in paths
    assert "b.md" in paths
    assert "c.md" not in paths


def test_title_match_ranks_above_body_match(tmp_path):
    """BM25 weights: title match (10x) should outrank a body-only match (1x)."""
    from vault_index import build_index, search
    _create_note(tmp_path, "title_hit.md", "Unrelated body text",
                 frontmatter="title: ALPR Surveillance Overview")
    _create_note(tmp_path, "body_hit.md",
                 "This note mentions ALPR surveillance once in passing.")
    build_index(tmp_path)
    results = search(tmp_path, "ALPR surveillance")
    assert len(results) == 2
    assert "title_hit.md" in results[0]["path"]


def test_search_empty_query_returns_empty(tmp_path):
    from vault_index import build_index, search
    _create_note(tmp_path, "note.md", "Some content")
    build_index(tmp_path)
    assert search(tmp_path, "") == []
    assert search(tmp_path, "   ") == []
