# tests/test_produce_output.py
"""Tests for produce_output.py"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/fake/vault")
os.environ.setdefault("INBOX_PATH", "C:/fake/vault/Inbox")


def test_list_formats(tmp_path):
    from produce_output import list_formats
    (tmp_path / "web_article.txt").write_text("prompt", encoding="utf-8")
    (tmp_path / "briefing.txt").write_text("prompt", encoding="utf-8")
    formats = list_formats(tmp_path)
    assert "web_article" in formats
    assert "briefing" in formats


def test_list_formats_empty(tmp_path):
    from produce_output import list_formats
    formats = list_formats(tmp_path)
    assert formats == []


def test_build_output_path_with_output_path(tmp_path):
    from produce_output import build_output_path
    result = build_output_path(
        output_dir=tmp_path,
        date_str="2026-02-25",
        source_slug="my-research",
        fmt="web_article",
    )
    assert result == tmp_path / "2026-02-25-my-research-web_article.md"


def test_load_format_prompt(tmp_path):
    from produce_output import load_format_prompt
    (tmp_path / "web_article.txt").write_text("Write an article.", encoding="utf-8")
    result = load_format_prompt("web_article", tmp_path)
    assert result == "Write an article."


def test_load_format_prompt_missing(tmp_path):
    from produce_output import load_format_prompt
    with pytest.raises(FileNotFoundError):
        load_format_prompt("nonexistent", tmp_path)
