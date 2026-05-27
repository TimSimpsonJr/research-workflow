"""Tests for fetch_playwright.py — JS-heavy page extraction fallback."""

import sys
import pytest


def test_playwright_unavailable_raises(monkeypatch):
    """When playwright isn't installed, fetch_via_playwright raises RuntimeError."""
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    from fetch_playwright import fetch_via_playwright
    with pytest.raises(RuntimeError, match="playwright not available"):
        fetch_via_playwright("https://example.com")
