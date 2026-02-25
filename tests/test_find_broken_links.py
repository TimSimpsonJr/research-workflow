# tests/test_find_broken_links.py
"""Tests for find_broken_links.py"""

import pytest
from pathlib import Path
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/Users/tim/OneDrive/Documents/Tim's Vault")
os.environ.setdefault("INBOX_PATH", "C:/Users/tim/OneDrive/Documents/Tim's Vault/Inbox")


def test_extract_links_basic():
    from find_broken_links import extract_links
    content = "See [[My Note]] and [[Other Note|alias]]."
    links = extract_links(content)
    assert "My Note" in links
    assert "Other Note" in links
    assert "alias" not in links


def test_extract_links_heading_ref():
    from find_broken_links import extract_links
    links = extract_links("See [[Note#Section]].")
    assert "Note" in links


def test_normalize_link():
    from find_broken_links import normalize_link
    assert normalize_link("My Note") == "my note"
    assert normalize_link("My%20Note") == "my note"
    assert normalize_link("Note#Section") == "note"


def test_build_note_index(tmp_path):
    from find_broken_links import build_note_index
    (tmp_path / "My Note.md").write_text("", encoding="utf-8")
    (tmp_path / "Other.md").write_text("", encoding="utf-8")
    index = build_note_index(tmp_path)
    assert "my note" in index
    assert "other" in index


def test_find_broken_links_detects_broken(tmp_path):
    from find_broken_links import find_broken_links
    note = tmp_path / "note.md"
    note.write_text("See [[Nonexistent Note]] and [[note]].", encoding="utf-8")
    broken = find_broken_links(tmp_path)
    assert any(b["link"] == "Nonexistent Note" for b in broken)
    assert not any(b["link"] == "note" for b in broken)


def test_find_broken_links_none_broken(tmp_path):
    from find_broken_links import find_broken_links
    (tmp_path / "Target.md").write_text("", encoding="utf-8")
    (tmp_path / "source.md").write_text("See [[Target]].", encoding="utf-8")
    broken = find_broken_links(tmp_path)
    assert broken == []
