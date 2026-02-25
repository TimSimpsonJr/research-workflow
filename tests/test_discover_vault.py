# tests/test_discover_vault.py
"""Tests for discover_vault.py"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys
import os


def test_slug_only_import():
    """discover_vault module is importable without side effects."""
    import discover_vault  # noqa: F401


def test_categorize_folders_inbox():
    """Folders named like inbox are categorized correctly."""
    from discover_vault import categorize_folder
    assert categorize_folder("Inbox") == "inbox"
    assert categorize_folder("00 Inbox") == "inbox"
    assert categorize_folder("_Inbox") == "inbox"
    assert categorize_folder("Capture") == "inbox"
    assert categorize_folder("Queue") == "inbox"


def test_categorize_folders_daily():
    from discover_vault import categorize_folder
    assert categorize_folder("Daily") == "daily"
    assert categorize_folder("Daily Notes") == "daily"
    assert categorize_folder("Journal") == "daily"
    assert categorize_folder("Calendar") == "daily"


def test_categorize_folders_mocs():
    from discover_vault import categorize_folder
    assert categorize_folder("MOCs") == "mocs"
    assert categorize_folder("Maps") == "mocs"
    assert categorize_folder("_MOCs") == "mocs"
    assert categorize_folder("Index") == "mocs"


def test_categorize_folders_output():
    from discover_vault import categorize_folder
    assert categorize_folder("Output") == "output"
    assert categorize_folder("Publish") == "output"
    assert categorize_folder("Production") == "output"
    assert categorize_folder("Export") == "output"


def test_categorize_folders_unknown():
    from discover_vault import categorize_folder
    assert categorize_folder("Random Research Notes") is None


def test_find_tagging_note_found(tmp_path):
    """find_tagging_note returns path when a tag-named note exists."""
    from discover_vault import find_tagging_note
    note = tmp_path / "Tagging System.md"
    note.write_text("# Tags\n- #research", encoding="utf-8")
    result = find_tagging_note(tmp_path)
    assert result == note


def test_find_tagging_note_not_found(tmp_path):
    """find_tagging_note returns None when no tag note exists."""
    from discover_vault import find_tagging_note
    (tmp_path / "Some Note.md").write_text("content", encoding="utf-8")
    result = find_tagging_note(tmp_path)
    assert result is None


def test_find_tagging_note_nested(tmp_path):
    """find_tagging_note searches recursively."""
    from discover_vault import find_tagging_note
    sub = tmp_path / "Meta"
    sub.mkdir()
    note = sub / "Tag Methodology.md"
    note.write_text("# Tags", encoding="utf-8")
    result = find_tagging_note(tmp_path)
    assert result == note


def test_generate_env_content():
    """generate_env_content returns a valid .env string."""
    from discover_vault import generate_env_content
    content = generate_env_content(
        vault_path=Path("C:/Users/tim/OneDrive/Documents/Tim's Vault"),
        inbox_path=Path("C:/Users/tim/OneDrive/Documents/Tim's Vault/Inbox"),
        daily_path=Path("C:/Users/tim/OneDrive/Documents/Tim's Vault/Daily"),
        mocs_path=None,
        output_path=None,
        tagging_note_path=None,
        api_key="sk-ant-test123",
        tag_format="list",
        date_format="%Y-%m-%d",
        frontmatter_fields=["title", "source", "tags", "created"],
    )
    assert "VAULT_PATH=" in content
    assert "INBOX_PATH=" in content
    assert "ANTHROPIC_API_KEY=sk-ant-test123" in content
    assert "TAG_FORMAT=list" in content


def test_sample_tag_format_list(tmp_path):
    """sample_tag_format detects list-style tags from sample notes."""
    from discover_vault import sample_tag_format
    note = tmp_path / "note.md"
    note.write_text("---\ntags:\n  - research\n  - ai\n---\n# Title\n", encoding="utf-8")
    result = sample_tag_format(tmp_path)
    assert result == "list"


def test_sample_tag_format_inline(tmp_path):
    """sample_tag_format detects inline-style tags from sample notes."""
    from discover_vault import sample_tag_format
    note = tmp_path / "note.md"
    note.write_text("---\ntags: [research, ai]\n---\n# Title\n", encoding="utf-8")
    result = sample_tag_format(tmp_path)
    assert result == "inline"


def test_detect_tag_format_from_text_list():
    from discover_vault import detect_tag_format_from_text
    assert detect_tag_format_from_text("---\ntags:\n  - research\n---\n") == "list"


def test_detect_tag_format_from_text_inline():
    from discover_vault import detect_tag_format_from_text
    assert detect_tag_format_from_text("---\ntags: [research, ai]\n---\n") == "inline"


def test_detect_tag_format_from_text_no_frontmatter():
    from discover_vault import detect_tag_format_from_text
    assert detect_tag_format_from_text("# Just a note\nno frontmatter") is None


def test_detect_tag_format_from_text_no_tags_key():
    from discover_vault import detect_tag_format_from_text
    assert detect_tag_format_from_text("---\ntitle: My Note\n---\n") is None
