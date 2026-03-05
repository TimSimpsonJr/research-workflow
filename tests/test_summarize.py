# tests/test_summarize.py
"""Tests for summarize.py — article summarization via Ollama or file output."""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/fake/vault")
os.environ.setdefault("INBOX_PATH", "C:/fake/vault/Inbox")


# ── summarize_article ────────────────────────────

def test_summarize_single_with_ollama():
    from summarize import summarize_article
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"response": json.dumps({
        "summary": "ALPR cameras capture plates automatically.",
        "source_type": "journalism",
        "key_entities": ["Flock Safety"],
        "key_claims": ["422M reads in 2024"],
    })}
    with patch("summarize.requests.post", return_value=mock_response):
        result = summarize_article(
            content="Long article about ALPR surveillance...",
            title="ALPR Report",
            url="https://example.com",
            model="qwen2.5:14b",
        )
    assert result is not None
    assert "summary" in result
    assert isinstance(result["key_entities"], list)


def test_summarize_article_handles_ollama_failure():
    from summarize import summarize_article
    with patch("summarize.requests.post", side_effect=Exception("connection refused")):
        result = summarize_article(
            content="Content", title="Title", url="https://x.com",
            model="qwen2.5:14b",
        )
    assert result is None


def test_summarize_article_handles_invalid_json():
    from summarize import summarize_article
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"response": "not valid json at all"}
    with patch("summarize.requests.post", return_value=mock_response):
        result = summarize_article(
            content="Content", title="Title", url="https://x.com",
            model="qwen2.5:14b",
        )
    assert result is None


def test_summarize_article_passes_correct_payload():
    from summarize import summarize_article
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"response": json.dumps({
        "summary": "Test", "source_type": "other",
        "key_entities": [], "key_claims": [],
    })}
    with patch("summarize.requests.post", return_value=mock_response) as mock_post:
        summarize_article(
            content="Article text here",
            title="My Title",
            url="https://example.com/article",
            model="qwen2.5:14b",
            ollama_url="http://myhost:11434",
        )
    call_args = mock_post.call_args
    assert call_args[0][0] == "http://myhost:11434/api/generate"
    payload = call_args[1].get("json") or call_args[0][1] if len(call_args[0]) > 1 else call_args[1]["json"]
    assert payload["model"] == "qwen2.5:14b"
    assert "Article text here" in payload["prompt"]
    assert payload["stream"] is False


# ── summarize_batch ──────────────────────────────

def test_summarize_batch_processes_all():
    from summarize import summarize_batch
    fetch_results = {
        "fetched": [
            {"url": "https://a.com", "title": "Article A", "content": "Content A about ALPR"},
            {"url": "https://b.com", "title": "Article B", "content": "Content B about surveillance"},
        ]
    }
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"response": json.dumps({
        "summary": "Summary", "source_type": "journalism",
        "key_entities": [], "key_claims": [],
    })}
    with patch("summarize.requests.post", return_value=mock_response):
        summaries = summarize_batch(fetch_results, model="qwen2.5:14b")
    assert len(summaries) == 2


def test_summarize_batch_includes_url_and_title():
    from summarize import summarize_batch
    fetch_results = {
        "fetched": [
            {"url": "https://a.com", "title": "Article A", "content": "Content A"},
        ]
    }
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"response": json.dumps({
        "summary": "Sum", "source_type": "journalism",
        "key_entities": [], "key_claims": [],
    })}
    with patch("summarize.requests.post", return_value=mock_response):
        summaries = summarize_batch(fetch_results, model="qwen2.5:14b")
    assert summaries[0]["url"] == "https://a.com"
    assert summaries[0]["title"] == "Article A"


def test_summarize_batch_skips_failures():
    from summarize import summarize_batch
    fetch_results = {
        "fetched": [
            {"url": "https://a.com", "title": "A", "content": "Content A"},
            {"url": "https://b.com", "title": "B", "content": "Content B"},
        ]
    }
    with patch("summarize.requests.post", side_effect=Exception("connection refused")):
        summaries = summarize_batch(fetch_results, model="qwen2.5:14b")
    assert len(summaries) == 0


# ── prepare_for_claude_code ──────────────────────

def test_prepare_for_claude_code_writes_files(tmp_path):
    from summarize import prepare_for_claude_code
    fetch_results = {
        "fetched": [
            {"url": "https://a.com", "title": "Article A", "content": "Content A " * 500},
        ]
    }
    output = prepare_for_claude_code(fetch_results, tmp_path)
    assert len(output) == 1
    written_file = tmp_path / output[0]["file"]
    assert written_file.exists()
    text = written_file.read_text()
    assert "Article A" in text
    assert "https://a.com" in text


def test_prepare_for_claude_code_truncates_content(tmp_path):
    from summarize import prepare_for_claude_code
    long_content = "x" * 10000
    fetch_results = {
        "fetched": [{"url": "https://a.com", "title": "Long", "content": long_content}]
    }
    output = prepare_for_claude_code(fetch_results, tmp_path)
    written_file = tmp_path / output[0]["file"]
    text = written_file.read_text()
    # Should be truncated to around 3000 chars of content (plus headers)
    assert len(text) < 5000


def test_prepare_for_claude_code_returns_correct_entries(tmp_path):
    from summarize import prepare_for_claude_code
    fetch_results = {
        "fetched": [
            {"url": "https://a.com", "title": "Article A", "content": "Content A"},
            {"url": "https://b.com", "title": "Article B", "content": "Content B"},
        ]
    }
    output = prepare_for_claude_code(fetch_results, tmp_path)
    assert len(output) == 2
    assert output[0]["url"] == "https://a.com"
    assert output[0]["title"] == "Article A"
    assert output[1]["url"] == "https://b.com"
    # Each entry has a "file" key with a relative filename
    assert output[0]["file"].endswith(".md")
    assert output[1]["file"].endswith(".md")


def test_prepare_for_claude_code_slugifies_filenames(tmp_path):
    from summarize import prepare_for_claude_code
    fetch_results = {
        "fetched": [
            {"url": "https://a.com", "title": "Hello World! Test Article", "content": "Content"},
        ]
    }
    output = prepare_for_claude_code(fetch_results, tmp_path)
    filename = output[0]["file"]
    assert filename.startswith("0-")
    assert "hello-world" in filename.lower()
