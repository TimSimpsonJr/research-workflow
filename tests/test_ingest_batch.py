# tests/test_ingest_batch.py
"""Tests for ingest_batch.py"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/Users/tim/OneDrive/Documents/Tim's Vault")
os.environ.setdefault("INBOX_PATH", "C:/Users/tim/OneDrive/Documents/Tim's Vault/Inbox")


def test_parse_url_file(tmp_path):
    """parse_url_file skips blank lines and comments."""
    from ingest_batch import parse_url_file
    url_file = tmp_path / "urls.txt"
    url_file.write_text(
        "https://example.com/1\n"
        "\n"
        "# This is a comment\n"
        "https://example.com/2\n",
        encoding="utf-8",
    )
    urls = parse_url_file(url_file)
    assert urls == ["https://example.com/1", "https://example.com/2"]


def test_parse_url_file_missing(tmp_path):
    """parse_url_file raises FileNotFoundError for missing file."""
    from ingest_batch import parse_url_file
    with pytest.raises(FileNotFoundError):
        parse_url_file(tmp_path / "nonexistent.txt")


def test_write_failed_urls(tmp_path):
    """write_failed_urls creates a file with failed URLs."""
    from ingest_batch import write_failed_urls
    failed = ["https://example.com/failed1", "https://example.com/failed2"]
    out = tmp_path / "failed_urls.txt"
    write_failed_urls(failed, out)
    content = out.read_text(encoding="utf-8")
    assert "https://example.com/failed1" in content
    assert "https://example.com/failed2" in content
