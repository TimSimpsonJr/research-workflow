# tests/test_daily_digest.py
"""Tests for daily_digest.py"""

import pytest
from pathlib import Path
from unittest.mock import patch
import os
import time

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/fake/vault")
os.environ.setdefault("INBOX_PATH", "C:/fake/vault/Inbox")
os.environ.setdefault("DAILY_PATH", "C:/fake/vault/Daily")


def test_find_recent_notes(tmp_path):
    from daily_digest import find_recent_notes
    recent = tmp_path / "recent.md"
    recent.write_text("Recent content", encoding="utf-8")
    # old file: modify mtime to 48 hours ago
    old = tmp_path / "old.md"
    old.write_text("Old content", encoding="utf-8")
    old_time = time.time() - (48 * 3600)
    import os as _os
    _os.utime(old, (old_time, old_time))

    results = find_recent_notes(tmp_path, hours=24, exclude_paths=set())
    names = [r.name for r in results]
    assert "recent.md" in names
    assert "old.md" not in names


def test_find_recent_notes_excludes(tmp_path):
    from daily_digest import find_recent_notes
    note = tmp_path / "note.md"
    note.write_text("Content", encoding="utf-8")
    results = find_recent_notes(tmp_path, hours=24, exclude_paths={note})
    assert note not in results


def test_extract_note_preview():
    from daily_digest import extract_note_preview
    content = "---\ntitle: Test\n---\n\n# Heading\n\nLorem ipsum dolor sit amet, consectetur adipiscing elit. " * 10
    preview = extract_note_preview(content, max_chars=500)
    assert len(preview) <= 510  # small buffer for truncation marker


def test_format_digest_entry():
    from daily_digest import format_digest_entry
    entry = format_digest_entry("My Note.md", "Preview of content here.")
    assert "My Note.md" in entry
    assert "Preview of content here." in entry


def test_build_daily_note_template():
    from daily_digest import build_daily_note_template
    result = build_daily_note_template("2026-02-25")
    assert "2026-02-25" in result
    assert "---" in result


def test_append_digest_section(tmp_path):
    from daily_digest import append_digest_section
    daily_note = tmp_path / "2026-02-25.md"
    daily_note.write_text("---\ndate: 2026-02-25\n---\n\n# Daily Note\n", encoding="utf-8")
    append_digest_section(daily_note, "## Research Digest\n\nSome content here.")
    content = daily_note.read_text(encoding="utf-8")
    assert "## Research Digest" in content
    assert "Some content here." in content
