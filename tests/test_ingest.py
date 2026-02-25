# tests/test_ingest.py
"""Tests for ingest.py"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/Users/tim/OneDrive/Documents/Tim's Vault")
os.environ.setdefault("INBOX_PATH", "C:/Users/tim/OneDrive/Documents/Tim's Vault/Inbox")


def test_slugify_basic():
    from ingest import slugify
    assert slugify("Hello World") == "hello-world"


def test_slugify_special_chars():
    from ingest import slugify
    assert slugify("Hello, World! (2024)") == "hello-world-2024"


def test_slugify_max_length():
    from ingest import slugify
    long = "a" * 100
    result = slugify(long)
    assert len(result) <= 60


def test_slugify_leading_trailing_hyphens():
    from ingest import slugify
    result = slugify("---hello---")
    assert not result.startswith("-")
    assert not result.endswith("-")


def test_extract_title_from_heading():
    from ingest import extract_title
    content = "# My Article Title\n\nSome content here."
    assert extract_title(content, "https://example.com/article") == "My Article Title"


def test_extract_title_fallback_to_domain():
    from ingest import extract_title
    content = "No heading here, just plain text."
    assert extract_title(content, "https://example.com/article") == "example.com"


def test_build_frontmatter_list_tags():
    from ingest import build_frontmatter
    fm = build_frontmatter(
        title="Test Article",
        source="https://example.com",
        fetched_at="2026-02-25T12:00:00+00:00",
        tag_format="list",
        extra_fields=["summary"],
    )
    assert 'title: "Test Article"' in fm
    assert "source: https://example.com" in fm
    assert "- inbox" in fm
    assert "- unprocessed" in fm


def test_build_frontmatter_inline_tags():
    from ingest import build_frontmatter
    fm = build_frontmatter(
        title="Test Article",
        source="https://example.com",
        fetched_at="2026-02-25T12:00:00+00:00",
        tag_format="inline",
        extra_fields=[],
    )
    assert "tags: [inbox, unprocessed]" in fm


def test_unique_output_path(tmp_path):
    from ingest import unique_output_path
    slug = "my-article"
    date = "2026-02-25"
    path1 = unique_output_path(tmp_path, date, slug)
    assert path1 == tmp_path / "2026-02-25-my-article.md"
    # Create first file
    path1.write_text("content", encoding="utf-8")
    path2 = unique_output_path(tmp_path, date, slug)
    assert path2 == tmp_path / "2026-02-25-my-article-2.md"


def test_fetch_url_success():
    from ingest import fetch_url
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "# Article\n\nContent here."
    mock_response.raise_for_status = MagicMock()
    with patch("ingest.requests.get", return_value=mock_response):
        result = fetch_url("https://example.com/article")
    assert "Article" in result


def test_fetch_url_failure():
    from ingest import fetch_url
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = Exception("404")
    with patch("ingest.requests.get", return_value=mock_response):
        with pytest.raises(Exception):
            fetch_url("https://example.com/404")
