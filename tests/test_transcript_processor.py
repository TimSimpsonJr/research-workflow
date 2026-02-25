# tests/test_transcript_processor.py
"""Tests for transcript_processor.py"""

import pytest
from pathlib import Path
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/fake/vault")
os.environ.setdefault("INBOX_PATH", "C:/fake/vault/Inbox")


def test_strip_vtt_timestamps():
    from transcript_processor import strip_vtt
    vtt = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:05.000\n"
        "Hello, this is the first line.\n\n"
        "00:00:06.000 --> 00:00:10.000\n"
        "And this is the second.\n"
    )
    result = strip_vtt(vtt)
    assert "WEBVTT" not in result
    assert "00:00" not in result
    assert "Hello, this is the first line." in result
    assert "And this is the second." in result


def test_strip_vtt_plain_text_passthrough():
    from transcript_processor import strip_vtt
    text = "This is a plain text transcript."
    result = strip_vtt(text)
    assert result == text


def test_detect_format_vtt():
    from transcript_processor import detect_format
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nHello."
    assert detect_format(vtt) == "vtt"


def test_detect_format_txt():
    from transcript_processor import detect_format
    txt = "Speaker: Hello, welcome to the interview."
    assert detect_format(txt) == "txt"


def test_build_output_paths(tmp_path):
    from transcript_processor import build_output_paths
    notes_path, quotes_path = build_output_paths(tmp_path, "2026-02-25", "my-interview")
    assert notes_path == tmp_path / "2026-02-25-my-interview-notes.md"
    assert quotes_path == tmp_path / "2026-02-25-my-interview-quotes.md"
