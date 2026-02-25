# tests/test_claude_pipe.py
"""Tests for claude_pipe.py"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys
import os

# Set required env vars before importing config
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/Users/tim/OneDrive/Documents/Tim's Vault")
os.environ.setdefault("INBOX_PATH", "C:/Users/tim/OneDrive/Documents/Tim's Vault/Inbox")


def test_import():
    import claude_pipe  # noqa: F401


def test_load_prompt_template(tmp_path):
    """load_prompt_template reads a .txt file from PROMPTS_PATH."""
    from claude_pipe import load_prompt_template
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "summarize.txt").write_text("Summarize this.", encoding="utf-8")
    result = load_prompt_template("summarize", prompt_dir)
    assert result == "Summarize this."


def test_load_prompt_template_missing(tmp_path):
    """load_prompt_template raises FileNotFoundError for unknown prompt."""
    from claude_pipe import load_prompt_template
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        load_prompt_template("nonexistent", prompt_dir)


def test_build_message():
    """build_message concatenates file content and prompt with exact separator."""
    from claude_pipe import build_message
    result = build_message("File content here.", "Summarize this.")
    assert result == "File content here.\n\n---\nSummarize this."


def test_estimate_cost():
    """estimate_cost returns correct USD value for known token counts."""
    from claude_pipe import estimate_cost
    # Haiku: $0.25/M input, $1.25/M output
    # 1000 input: 0.00025, 500 output: 0.000625 → 0.000875
    cost = estimate_cost(1000, 500, model="claude-haiku-4-5-20251001")
    assert abs(cost - 0.000875) < 1e-9


def test_call_claude_returns_text(tmp_path):
    """call_claude returns text response from mocked API."""
    from claude_pipe import call_claude

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Summary result")]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50

    with patch("claude_pipe.anthropic.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.return_value = mock_response
        text, usage = call_claude("test message", model="claude-haiku-4-5-20251001", max_tokens=512)

    assert text == "Summary result"
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 50


def test_write_output_with_frontmatter(tmp_path):
    """write_output writes parseable YAML frontmatter and response body."""
    import yaml
    from claude_pipe import write_output
    out_file = tmp_path / "result.md"
    write_output("Response text", out_file, source_note="note.md", prompt_used="summarize")
    content = out_file.read_text(encoding="utf-8")
    # Verify frontmatter is delimited correctly
    parts = content.split("---")
    assert len(parts) >= 3
    fm = yaml.safe_load(parts[1])
    assert fm["source_note"] == "note.md"
    assert fm["prompt_used"] == "summarize"
    assert "generated_at" in fm
    # Verify body follows frontmatter
    assert "Response text" in content
