# tests/test_find_related.py
"""Tests for find_related.py"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/Users/tim/OneDrive/Documents/Tim's Vault")
os.environ.setdefault("INBOX_PATH", "C:/Users/tim/OneDrive/Documents/Tim's Vault/Inbox")


def test_parse_keywords():
    from find_related import parse_keywords
    text = "machine learning\nneural networks\ntransformers\n"
    result = parse_keywords(text)
    assert result == ["machine learning", "neural networks", "transformers"]


def test_parse_keywords_strips_empty():
    from find_related import parse_keywords
    text = "term one\n\n   \nterm two\n"
    result = parse_keywords(text)
    assert result == ["term one", "term two"]


def test_search_vault_python(tmp_path):
    """search_vault_python returns scored notes matching keywords."""
    from find_related import search_vault_python
    note1 = tmp_path / "machine-learning.md"
    note1.write_text("Machine learning and neural networks.", encoding="utf-8")
    note2 = tmp_path / "cooking.md"
    note2.write_text("Recipes and ingredients.", encoding="utf-8")
    note3 = tmp_path / "transformers.md"
    note3.write_text("Transformers are neural network architectures.", encoding="utf-8")

    results = search_vault_python(
        tmp_path,
        keywords=["machine learning", "neural networks", "transformers"],
        source_path=None,
    )
    scored = {r["file"].name: r["score"] for r in results}
    assert scored.get("machine-learning.md", 0) > scored.get("cooking.md", 0)
    assert "cooking.md" not in [r["file"].name for r in results[:2]]


def test_search_vault_excludes_source(tmp_path):
    """search_vault_python excludes the source note from results."""
    from find_related import search_vault_python
    source = tmp_path / "source.md"
    source.write_text("Machine learning content.", encoding="utf-8")
    results = search_vault_python(tmp_path, keywords=["machine learning"], source_path=source)
    assert all(r["file"] != source for r in results)
