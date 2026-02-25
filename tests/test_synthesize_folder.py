# tests/test_synthesize_folder.py
"""Tests for synthesize_folder.py"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/fake/vault")
os.environ.setdefault("INBOX_PATH", "C:/fake/vault/Inbox")


def test_collect_markdown_files(tmp_path):
    from synthesize_folder import collect_markdown_files
    (tmp_path / "note1.md").write_text("Content 1", encoding="utf-8")
    (tmp_path / "note2.md").write_text("Content 2", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "note3.md").write_text("Content 3", encoding="utf-8")

    files_non_recursive = collect_markdown_files(tmp_path, recursive=False)
    assert len(files_non_recursive) == 2

    files_recursive = collect_markdown_files(tmp_path, recursive=True)
    assert len(files_recursive) == 3


def test_concatenate_files(tmp_path):
    from synthesize_folder import concatenate_files
    note1 = tmp_path / "alpha.md"
    note1.write_text("Alpha content", encoding="utf-8")
    note2 = tmp_path / "beta.md"
    note2.write_text("Beta content", encoding="utf-8")

    result = concatenate_files([note1, note2])
    assert "Alpha content" in result
    assert "Beta content" in result
    assert "# Source: alpha.md" in result
    assert "# Source: beta.md" in result


def test_estimate_tokens():
    from synthesize_folder import estimate_tokens
    text = "word " * 1000
    tokens = estimate_tokens(text)
    # Rough estimate: ~750 tokens per 1000 words (4 chars/token)
    assert 200 < tokens < 2000


def test_repomix_available_check():
    from synthesize_folder import check_repomix
    # Just verify it returns a bool
    result = check_repomix()
    assert isinstance(result, bool)
