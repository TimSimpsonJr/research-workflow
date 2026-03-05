# tests/test_produce_output.py
"""Tests for produce_output.py"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ──────────────────────────────────────────────
# Pure function tests (no mocks needed)
# ──────────────────────────────────────────────

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


def test_list_formats_missing_dir():
    from produce_output import list_formats
    formats = list_formats(Path("/nonexistent/dir"))
    assert formats == []


def test_build_output_path_non_digest_has_no_date(tmp_path):
    """Non-daily-digest formats should NOT have a date prefix."""
    from produce_output import build_output_path
    result = build_output_path(
        output_dir=tmp_path,
        date_str="2026-02-25",
        source_slug="my-research",
        fmt="web_article",
    )
    assert result == tmp_path / "my-research-web_article.md"


def test_build_output_path_daily_digest_has_date(tmp_path):
    """daily_digest format SHOULD have a date prefix."""
    from produce_output import build_output_path
    result = build_output_path(
        output_dir=tmp_path,
        date_str="2026-02-25",
        source_slug="my-research",
        fmt="daily_digest",
    )
    assert result == tmp_path / "2026-02-25-my-research-daily_digest.md"


def test_build_output_path_all_non_digest_formats(tmp_path):
    """All existing production formats should have no date prefix."""
    from produce_output import build_output_path
    for fmt in ["web_article", "video_script", "social_post", "briefing", "talking_points", "email_newsletter"]:
        result = build_output_path(tmp_path, "2026-02-25", "slug", fmt)
        assert result.name == f"slug-{fmt}.md", f"Failed for format: {fmt}"


def test_load_format_prompt(tmp_path):
    from produce_output import load_format_prompt
    (tmp_path / "web_article.txt").write_text("Write an article.", encoding="utf-8")
    result = load_format_prompt("web_article", tmp_path)
    assert result == "Write an article."


def test_load_format_prompt_missing(tmp_path):
    from produce_output import load_format_prompt
    with pytest.raises(FileNotFoundError):
        load_format_prompt("nonexistent", tmp_path)


def test_slugify_basic():
    from produce_output import _slugify
    assert _slugify("Hello World") == "hello-world"


def test_slugify_special_chars():
    from produce_output import _slugify
    assert _slugify("My Research!!! (Draft #2)") == "my-research-draft-2"


def test_slugify_max_length():
    from produce_output import _slugify
    long_text = "a" * 100
    result = _slugify(long_text, max_length=10)
    assert len(result) <= 10


# ──────────────────────────────────────────────
# Ollama mode tests (mocked requests.post)
# ──────────────────────────────────────────────

def test_generate_with_ollama_success():
    from produce_output import generate_with_ollama

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"response": "Generated article text here."}
    mock_response.raise_for_status = MagicMock()

    with patch("produce_output.requests.post", return_value=mock_response) as mock_post:
        result = generate_with_ollama("test prompt", model="llama3.2")

    assert result == "Generated article text here."
    mock_post.assert_called_once_with(
        "http://localhost:11434/api/generate",
        json={
            "model": "llama3.2",
            "prompt": "test prompt",
            "stream": False,
        },
        timeout=300,
    )


def test_generate_with_ollama_custom_url():
    from produce_output import generate_with_ollama

    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "output"}
    mock_response.raise_for_status = MagicMock()

    with patch("produce_output.requests.post", return_value=mock_response) as mock_post:
        result = generate_with_ollama("prompt", model="mistral", ollama_url="http://myhost:9999")

    assert result == "output"
    mock_post.assert_called_once_with(
        "http://myhost:9999/api/generate",
        json={
            "model": "mistral",
            "prompt": "prompt",
            "stream": False,
        },
        timeout=300,
    )


def test_generate_with_ollama_connection_error():
    from produce_output import generate_with_ollama

    with patch("produce_output.requests.post", side_effect=ConnectionError("refused")):
        result = generate_with_ollama("prompt", model="llama3.2")

    assert result is None


def test_generate_with_ollama_http_error():
    from produce_output import generate_with_ollama

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = Exception("500 Server Error")

    with patch("produce_output.requests.post", return_value=mock_response):
        result = generate_with_ollama("prompt", model="llama3.2")

    assert result is None


# ──────────────────────────────────────────────
# File output mode tests
# ──────────────────────────────────────────────

def test_prepare_file_for_claude(tmp_path):
    from produce_output import prepare_file_for_claude

    message = "Some content\n\n---\nFormat prompt here"
    result_path = prepare_file_for_claude(message, tmp_path, "my-note", "web_article")

    assert result_path == tmp_path / "my-note-web_article-prompt.md"
    assert result_path.exists()
    assert result_path.read_text(encoding="utf-8") == message


def test_prepare_file_for_claude_creates_dir(tmp_path):
    from produce_output import prepare_file_for_claude

    nested_dir = tmp_path / "deep" / "nested"
    result_path = prepare_file_for_claude("content", nested_dir, "slug", "briefing")

    assert nested_dir.exists()
    assert result_path.exists()


# ──────────────────────────────────────────────
# CLI integration tests
# ──────────────────────────────────────────────

def test_main_list_formats(tmp_path, capsys):
    """--list-formats should print available formats and exit."""
    from produce_output import main
    import produce_output

    formats_dir = tmp_path / "output_formats"
    formats_dir.mkdir()
    (formats_dir / "web_article.txt").write_text("prompt", encoding="utf-8")
    (formats_dir / "briefing.txt").write_text("prompt", encoding="utf-8")

    original_prompts = produce_output.PROMPTS_PATH
    produce_output.PROMPTS_PATH = tmp_path
    try:
        with patch("sys.argv", ["produce_output.py", "--list-formats"]):
            main()
    finally:
        produce_output.PROMPTS_PATH = original_prompts

    captured = capsys.readouterr()
    assert "web_article" in captured.out
    assert "briefing" in captured.out


def test_main_dry_run(tmp_path, capsys):
    """--dry-run should show message length without calling Ollama."""
    from produce_output import main
    import produce_output

    formats_dir = tmp_path / "output_formats"
    formats_dir.mkdir()
    (formats_dir / "web_article.txt").write_text("Write an article.", encoding="utf-8")

    source_file = tmp_path / "note.md"
    source_file.write_text("Some research content here.", encoding="utf-8")

    original_prompts = produce_output.PROMPTS_PATH
    produce_output.PROMPTS_PATH = tmp_path
    try:
        with patch("sys.argv", ["produce_output.py", "--file", str(source_file), "--format", "web_article", "--dry-run"]):
            main()
    finally:
        produce_output.PROMPTS_PATH = original_prompts

    captured = capsys.readouterr()
    assert "Dry run" in captured.out
    assert "web_article" in captured.out


def test_main_ollama_success(tmp_path, capsys):
    """When Ollama succeeds, output should be printed to stdout."""
    from produce_output import main
    import produce_output

    formats_dir = tmp_path / "output_formats"
    formats_dir.mkdir()
    (formats_dir / "web_article.txt").write_text("Write an article.", encoding="utf-8")

    source_file = tmp_path / "note.md"
    source_file.write_text("Research content.", encoding="utf-8")

    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "Generated article output."}
    mock_response.raise_for_status = MagicMock()

    original_prompts = produce_output.PROMPTS_PATH
    produce_output.PROMPTS_PATH = tmp_path
    try:
        with patch("sys.argv", ["produce_output.py", "--file", str(source_file), "--format", "web_article"]):
            with patch("produce_output.requests.post", return_value=mock_response):
                main()
    finally:
        produce_output.PROMPTS_PATH = original_prompts

    captured = capsys.readouterr()
    assert "Generated article output." in captured.out


def test_main_ollama_failure_falls_back_to_file(tmp_path, capsys):
    """When Ollama fails, should fall back to file output."""
    from produce_output import main
    import produce_output

    formats_dir = tmp_path / "output_formats"
    formats_dir.mkdir()
    (formats_dir / "web_article.txt").write_text("Write an article.", encoding="utf-8")

    source_file = tmp_path / "note.md"
    source_file.write_text("Research content.", encoding="utf-8")

    output_dir = tmp_path / "output"

    original_prompts = produce_output.PROMPTS_PATH
    produce_output.PROMPTS_PATH = tmp_path
    try:
        with patch("sys.argv", [
            "produce_output.py",
            "--file", str(source_file),
            "--format", "web_article",
            "--output-dir", str(output_dir),
        ]):
            with patch("produce_output.requests.post", side_effect=ConnectionError("refused")):
                main()
    finally:
        produce_output.PROMPTS_PATH = original_prompts

    captured = capsys.readouterr()
    assert "File prepared at" in captured.out
    assert "process with Claude Code" in captured.out

    # Verify the file was actually created
    prompt_file = output_dir / "note-web_article-prompt.md"
    assert prompt_file.exists()
    content = prompt_file.read_text(encoding="utf-8")
    assert "Research content." in content
    assert "Write an article." in content
