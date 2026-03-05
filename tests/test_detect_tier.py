"""Tests for detect_tier.py — infrastructure detection."""

import pytest
from unittest.mock import patch, MagicMock


def test_check_ollama_not_installed():
    from detect_tier import check_ollama
    with patch("detect_tier.shutil.which", return_value=None):
        result = check_ollama()
    assert result["installed"] is False
    assert result["recommended_model"] is None


def test_check_ollama_installed_but_not_running():
    from detect_tier import check_ollama
    with patch("detect_tier.shutil.which", return_value="/usr/bin/ollama"):
        with patch("detect_tier.subprocess.run", side_effect=Exception("connection refused")):
            result = check_ollama()
    assert result["installed"] is True
    assert result["running"] is False


def test_recommend_model_low_ram():
    from detect_tier import recommend_model
    result = recommend_model(ram_gb=6, vram_gb=0)
    assert result["recommendation"] == "skip"


def test_recommend_model_medium_ram():
    from detect_tier import recommend_model
    result = recommend_model(ram_gb=16, vram_gb=0)
    assert result["recommendation"] == "use"
    assert "7b" in result["model"] or "8b" in result["model"]


def test_recommend_model_high_vram():
    from detect_tier import recommend_model
    result = recommend_model(ram_gb=32, vram_gb=12)
    assert result["recommendation"] == "use"
    assert "14b" in result["model"] or "32b" in result["model"]


def test_check_searxng_not_available():
    from detect_tier import check_searxng
    result = check_searxng(url=None)
    assert result["available"] is False


def test_check_searxng_url_unreachable():
    from detect_tier import check_searxng
    with patch("detect_tier.requests.get", side_effect=Exception("connection refused")):
        result = check_searxng(url="http://localhost:8888")
    assert result["available"] is False


def test_check_ytdlp_installed():
    from detect_tier import check_ytdlp
    with patch("detect_tier.shutil.which", return_value="/usr/bin/yt-dlp"):
        result = check_ytdlp()
    assert result["installed"] is True


def test_check_ytdlp_not_installed():
    from detect_tier import check_ytdlp
    with patch("detect_tier.shutil.which", return_value=None):
        result = check_ytdlp()
    assert result["installed"] is False


def test_detect_tier_base():
    from detect_tier import detect_tier
    with patch("detect_tier.check_ollama", return_value={"installed": False, "running": False, "recommended_model": None}):
        with patch("detect_tier.check_searxng", return_value={"available": False}):
            tier = detect_tier(searxng_url=None)
    assert tier == "base"


def test_detect_tier_mid():
    from detect_tier import detect_tier
    with patch("detect_tier.check_ollama", return_value={"installed": True, "running": True, "recommended_model": "qwen2.5:14b"}):
        with patch("detect_tier.check_searxng", return_value={"available": False}):
            tier = detect_tier(searxng_url=None)
    assert tier == "mid"


def test_detect_tier_full():
    from detect_tier import detect_tier
    with patch("detect_tier.check_ollama", return_value={"installed": True, "running": True, "recommended_model": "qwen2.5:14b"}):
        with patch("detect_tier.check_searxng", return_value={"available": True}):
            tier = detect_tier(searxng_url="http://localhost:8888")
    assert tier == "full"
