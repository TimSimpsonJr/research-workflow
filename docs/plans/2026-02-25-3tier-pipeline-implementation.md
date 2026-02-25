# 3-Tier Research Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split `research-haiku` into a 3-tier pipeline (Haiku search → Python fetch/cache → Haiku classify) and update post-research scripts to use Sonnet instead of Opus.

**Architecture:** The existing Sonnet orchestrator (`research` skill) is updated to spawn a Haiku search agent, pipe its URL list through a Python caching layer (`fetch_and_clean.py`), then spawn a Haiku classify agent — before passing classification results to the existing Sonnet note-writing step. Two post-research scripts (`synthesize_folder.py`, `produce_output.py`) are updated to use Sonnet and fix filename conventions.

**Tech Stack:** Python 3.12, `requests`, `anthropic` SDK, Claude Haiku/Sonnet models, Jina Reader API, Wayback Machine API, Claude Code skills (markdown)

**Python full path:** `C:\Users\tim\AppData\Local\Programs\Python\Python312\python.exe`
**Scripts dir:** `C:\Users\tim\OneDrive\Documents\Projects\research-workflow\`
**Pytest:** `C:\Users\tim\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe`

---

## Task 1: Switch heavy model default from Opus to Sonnet

Two files need changes. `config.py` sets the default model string; `claude_pipe.py` maintains a cost-per-token table. Neither script individually hardcodes `claude-opus-4-6` — they reference `config.CLAUDE_MODEL_HEAVY` — so changing the default in `config.py` and updating the cost table is sufficient.

**Files:**
- Modify: `config.py:25`
- Modify: `claude_pipe.py:28-34`
- Test: no automated test needed — this is a constant change; verify manually via dry-run in Task 6

---

**Step 1: Edit `config.py` line 25**

Change:
```python
CLAUDE_MODEL_HEAVY = os.environ.get("CLAUDE_MODEL_HEAVY", "claude-opus-4-6")
```
To:
```python
CLAUDE_MODEL_HEAVY = os.environ.get("CLAUDE_MODEL_HEAVY", "claude-sonnet-4-6")
```

---

**Step 2: Add Sonnet to cost table in `claude_pipe.py`**

The `COST_PER_M_INPUT` and `COST_PER_M_OUTPUT` dicts currently only have Opus and Haiku. If `CLAUDE_MODEL_HEAVY` is now Sonnet, calls will trigger the fallback warning. Add Sonnet entries.

Change lines 27–34:
```python
# Approximate cost per million tokens (USD)
COST_PER_M_INPUT = {
    "claude-opus-4-6": 15.0,
    "claude-sonnet-4-6": 3.0,
    "claude-haiku-4-5-20251001": 0.25,
}
COST_PER_M_OUTPUT = {
    "claude-opus-4-6": 75.0,
    "claude-sonnet-4-6": 15.0,
    "claude-haiku-4-5-20251001": 1.25,
}
```

---

**Step 3: Run existing tests to confirm nothing broken**

```bash
C:\Users\tim\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe C:\Users\tim\OneDrive\Documents\Projects\research-workflow\tests\ -v
```
Expected: all tests pass (72 tests, no regressions).

---

**Step 4: Commit**

```bash
git -C "C:\Users\tim\OneDrive\Documents\Projects\research-workflow" add config.py claude_pipe.py
git -C "C:\Users\tim\OneDrive\Documents\Projects\research-workflow" commit -m "feat: switch CLAUDE_MODEL_HEAVY default from Opus to Sonnet"
```

---

## Task 2: Fix `produce_output.py` filename — date only on daily_digest

Currently `build_output_path()` always produces `{date}-{slug}-{fmt}.md`. The change: only prefix the date when `fmt == "daily_digest"`. All other formats get `{slug}-{fmt}.md`.

**Files:**
- Modify: `produce_output.py:45-47`
- Modify: `tests/test_produce_output.py` — update existing test, add new tests

---

**Step 1: Write failing tests first**

Replace the body of `tests/test_produce_output.py` with:

```python
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
```

---

**Step 2: Run the new tests to confirm they FAIL**

```bash
C:\Users\tim\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe C:\Users\tim\OneDrive\Documents\Projects\research-workflow\tests\test_produce_output.py -v
```
Expected: `test_build_output_path_non_digest_has_no_date`, `test_build_output_path_daily_digest_has_date`, and `test_build_output_path_all_non_digest_formats` all FAIL (old logic always includes the date).

---

**Step 3: Update `build_output_path()` in `produce_output.py`**

Replace lines 45–47:
```python
def build_output_path(output_dir: Path, date_str: str, source_slug: str, fmt: str) -> Path:
    """Build the output file path."""
    return output_dir / f"{date_str}-{source_slug}-{fmt}.md"
```
With:
```python
def build_output_path(output_dir: Path, date_str: str, source_slug: str, fmt: str) -> Path:
    """Build the output file path. Date prefix only for daily_digest format."""
    if fmt == "daily_digest":
        return output_dir / f"{date_str}-{source_slug}-{fmt}.md"
    return output_dir / f"{source_slug}-{fmt}.md"
```

---

**Step 4: Run tests again to confirm they PASS**

```bash
C:\Users\tim\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe C:\Users\tim\OneDrive\Documents\Projects\research-workflow\tests\test_produce_output.py -v
```
Expected: all 7 tests PASS.

---

**Step 5: Run full test suite**

```bash
C:\Users\tim\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe C:\Users\tim\OneDrive\Documents\Projects\research-workflow\tests\ -v
```
Expected: all tests pass.

---

**Step 6: Commit**

```bash
git -C "C:\Users\tim\OneDrive\Documents\Projects\research-workflow" add produce_output.py tests/test_produce_output.py
git -C "C:\Users\tim\OneDrive\Documents\Projects\research-workflow" commit -m "feat: date prefix in produce_output only for daily_digest format"
```

---

## Task 3: Create `fetch_and_clean.py`

New Python script that fetches URLs via Jina Reader API, caches by MD5, falls back to Wayback Machine, deduplicates URLs, and outputs `fetch_results.json`. This is the Python tier between Haiku search and Haiku classify.

**Files:**
- Create: `fetch_and_clean.py`
- Create: `tests/test_fetch_and_clean.py`

---

**Step 1: Write the failing tests first**

Create `tests/test_fetch_and_clean.py`:

```python
# tests/test_fetch_and_clean.py
"""Tests for fetch_and_clean.py"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/fake/vault")
os.environ.setdefault("INBOX_PATH", "C:/fake/vault/Inbox")


# ──────────────────────────────────────────────
# url_cache_key
# ──────────────────────────────────────────────

def test_url_cache_key_is_md5():
    from fetch_and_clean import url_cache_key
    import hashlib
    url = "https://example.com/article"
    expected = hashlib.md5(url.encode("utf-8")).hexdigest()
    assert url_cache_key(url) == expected


def test_url_cache_key_different_urls_differ():
    from fetch_and_clean import url_cache_key
    assert url_cache_key("https://a.com") != url_cache_key("https://b.com")


# ──────────────────────────────────────────────
# normalize_url + deduplicate_urls
# ──────────────────────────────────────────────

def test_normalize_url_strips_trailing_slash():
    from fetch_and_clean import normalize_url
    assert normalize_url("https://example.com/") == "https://example.com"


def test_normalize_url_lowercases():
    from fetch_and_clean import normalize_url
    assert normalize_url("HTTPS://EXAMPLE.COM") == "https://example.com"


def test_deduplicate_urls_removes_duplicates():
    from fetch_and_clean import deduplicate_urls
    urls = [
        {"url": "https://example.com/"},
        {"url": "https://EXAMPLE.COM/"},
        {"url": "https://other.com"},
    ]
    result = deduplicate_urls(urls)
    assert len(result) == 2
    assert result[1]["url"] == "https://other.com"


def test_deduplicate_urls_preserves_order():
    from fetch_and_clean import deduplicate_urls
    urls = [
        {"url": "https://a.com"},
        {"url": "https://b.com"},
        {"url": "https://a.com"},
    ]
    result = deduplicate_urls(urls)
    assert [r["url"] for r in result] == ["https://a.com", "https://b.com"]


# ──────────────────────────────────────────────
# Cache load/save/expiry
# ──────────────────────────────────────────────

def test_load_cache_returns_none_when_missing(tmp_path):
    from fetch_and_clean import load_cache
    assert load_cache(tmp_path, "nonexistent_key") is None


def test_load_cache_returns_entry_when_present(tmp_path):
    from fetch_and_clean import load_cache, save_cache
    entry = {"url": "https://example.com", "content": "hello", "fetched_at": datetime.now(timezone.utc).isoformat(), "title": "Test", "fetch_method": "jina"}
    save_cache(tmp_path, "testkey", entry)
    loaded = load_cache(tmp_path, "testkey")
    assert loaded["content"] == "hello"


def test_is_expired_returns_false_for_fresh_entry():
    from fetch_and_clean import is_expired
    entry = {"fetched_at": datetime.now(timezone.utc).isoformat()}
    assert is_expired(entry, ttl_days=7) is False


def test_is_expired_returns_true_for_old_entry():
    from fetch_and_clean import is_expired
    old_time = datetime.now(timezone.utc) - timedelta(days=8)
    entry = {"fetched_at": old_time.isoformat()}
    assert is_expired(entry, ttl_days=7) is True


def test_save_cache_creates_file(tmp_path):
    from fetch_and_clean import save_cache
    entry = {"url": "u", "content": "c", "fetched_at": "2026-01-01T00:00:00+00:00", "title": "", "fetch_method": "jina"}
    save_cache(tmp_path, "mykey", entry)
    assert (tmp_path / "mykey.json").exists()


# ──────────────────────────────────────────────
# fetch_via_jina (mocked)
# ──────────────────────────────────────────────

def test_fetch_via_jina_returns_content_and_title():
    from fetch_and_clean import fetch_via_jina
    mock_response = MagicMock()
    mock_response.text = "# My Article\n\nSome content here."
    mock_response.raise_for_status = MagicMock()
    with patch("fetch_and_clean.requests.get", return_value=mock_response):
        content, title = fetch_via_jina("https://example.com")
    assert content == "# My Article\n\nSome content here."
    assert title == "My Article"


def test_fetch_via_jina_title_empty_when_no_heading():
    from fetch_and_clean import fetch_via_jina
    mock_response = MagicMock()
    mock_response.text = "Just some text, no heading."
    mock_response.raise_for_status = MagicMock()
    with patch("fetch_and_clean.requests.get", return_value=mock_response):
        content, title = fetch_via_jina("https://example.com")
    assert title == ""


# ──────────────────────────────────────────────
# fetch_url fallback logic (mocked)
# ──────────────────────────────────────────────

def test_fetch_url_uses_jina_first():
    from fetch_and_clean import fetch_url
    with patch("fetch_and_clean.fetch_via_jina", return_value=("content", "title")) as mock_jina:
        content, title, method = fetch_url("https://example.com")
    assert method == "jina"
    mock_jina.assert_called_once()


def test_fetch_url_falls_back_to_wayback_when_jina_fails():
    from fetch_and_clean import fetch_url
    with patch("fetch_and_clean.fetch_via_jina", side_effect=Exception("timeout")):
        with patch("fetch_and_clean.fetch_via_wayback", return_value=("archived content", "archived title")) as mock_wb:
            content, title, method = fetch_url("https://example.com")
    assert method == "wayback"
    assert content == "archived content"


def test_fetch_url_raises_when_both_fail():
    from fetch_and_clean import fetch_url
    with patch("fetch_and_clean.fetch_via_jina", side_effect=Exception("jina fail")):
        with patch("fetch_and_clean.fetch_via_wayback", side_effect=Exception("wayback fail")):
            with pytest.raises(RuntimeError, match="All fetch methods failed"):
                fetch_url("https://example.com")


# ──────────────────────────────────────────────
# process_urls — cache hit / cache miss / failure
# ──────────────────────────────────────────────

def test_process_urls_cache_hit_skips_fetch(tmp_path):
    from fetch_and_clean import process_urls, save_cache, url_cache_key
    url = "https://example.com/article"
    cache_key = url_cache_key(url)
    entry = {
        "url": url,
        "content": "cached content",
        "title": "Cached",
        "fetch_method": "jina",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    save_cache(tmp_path, cache_key, entry)

    with patch("fetch_and_clean.fetch_url") as mock_fetch:
        fetched, failed = process_urls(
            urls=[{"url": url}],
            cache_dir=tmp_path,
            ttl_days=7,
            jina_api_key=None,
        )
    mock_fetch.assert_not_called()
    assert len(fetched) == 1
    assert fetched[0]["cache_hit"] is True
    assert fetched[0]["content"] == "cached content"


def test_process_urls_fetches_when_cache_miss(tmp_path):
    from fetch_and_clean import process_urls
    with patch("fetch_and_clean.fetch_url", return_value=("fresh content", "Fresh Title", "jina")):
        fetched, failed = process_urls(
            urls=[{"url": "https://example.com/new"}],
            cache_dir=tmp_path,
            ttl_days=7,
            jina_api_key=None,
        )
    assert len(fetched) == 1
    assert fetched[0]["cache_hit"] is False
    assert fetched[0]["content"] == "fresh content"


def test_process_urls_fetch_failure_goes_to_failed_list(tmp_path):
    from fetch_and_clean import process_urls
    with patch("fetch_and_clean.fetch_url", side_effect=RuntimeError("all methods failed")):
        fetched, failed = process_urls(
            urls=[{"url": "https://broken.com"}],
            cache_dir=tmp_path,
            ttl_days=7,
            jina_api_key=None,
        )
    assert len(fetched) == 0
    assert len(failed) == 1
    assert failed[0]["url"] == "https://broken.com"


def test_process_urls_content_truncated_at_50k(tmp_path):
    from fetch_and_clean import process_urls, MAX_CONTENT_CHARS
    long_content = "x" * (MAX_CONTENT_CHARS + 1000)
    with patch("fetch_and_clean.fetch_url", return_value=(long_content, "title", "jina")):
        fetched, _ = process_urls(
            urls=[{"url": "https://example.com/long"}],
            cache_dir=tmp_path,
            ttl_days=7,
            jina_api_key=None,
        )
    assert len(fetched[0]["content"]) == MAX_CONTENT_CHARS


def test_process_urls_expired_cache_refetches(tmp_path):
    from fetch_and_clean import process_urls, save_cache, url_cache_key
    url = "https://example.com/old"
    cache_key = url_cache_key(url)
    old_time = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    entry = {"url": url, "content": "old content", "title": "", "fetch_method": "jina", "fetched_at": old_time}
    save_cache(tmp_path, cache_key, entry)

    with patch("fetch_and_clean.fetch_url", return_value=("refreshed content", "title", "jina")) as mock_fetch:
        fetched, failed = process_urls(
            urls=[{"url": url}],
            cache_dir=tmp_path,
            ttl_days=7,
            jina_api_key=None,
        )
    mock_fetch.assert_called_once()
    assert fetched[0]["cache_hit"] is False
    assert fetched[0]["content"] == "refreshed content"
```

---

**Step 2: Run the tests to confirm they FAIL**

```bash
C:\Users\tim\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe C:\Users\tim\OneDrive\Documents\Projects\research-workflow\tests\test_fetch_and_clean.py -v
```
Expected: `ModuleNotFoundError: No module named 'fetch_and_clean'` — confirms test file is wired but implementation missing.

---

**Step 3: Create `fetch_and_clean.py`**

Create `C:\Users\tim\OneDrive\Documents\Projects\research-workflow\fetch_and_clean.py`:

```python
"""
fetch_and_clean.py — URL Fetch, Clean, and Cache

Purpose: Tier 2 of the research pipeline. Accepts a search_context JSON,
fetches each URL via Jina Reader (with Wayback Machine fallback), caches
results by MD5(url), and outputs fetch_results JSON.

Usage:
    python fetch_and_clean.py --input search_context.json
    python fetch_and_clean.py --input search_context.json --output fetch_results.json
    python fetch_and_clean.py --input search_context.json --dry-run

Input schema:  see docs/plans/2026-02-25-research-pipeline-3tier-design.md
Output schema: see docs/plans/2026-02-25-research-pipeline-3tier-design.md

Dependencies: requests, python-dotenv
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

DEFAULT_CACHE_DIR = Path(__file__).parent / ".cache" / "fetch"
DEFAULT_TTL_DAYS = 7
MAX_CONTENT_CHARS = 50_000
JINA_BASE_URL = "https://r.jina.ai"
WAYBACK_API = "https://archive.org/wayback/available"


# ──────────────────────────────────────────────
# URL helpers
# ──────────────────────────────────────────────

def url_cache_key(url: str) -> str:
    """Return MD5 hash of URL as cache filename key."""
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def normalize_url(url: str) -> str:
    """Normalize URL for deduplication: lowercase, strip trailing slash."""
    return url.rstrip("/").lower()


def deduplicate_urls(urls: list[dict]) -> list[dict]:
    """Remove duplicate URLs (case-insensitive, trailing-slash agnostic). Preserves order."""
    seen: set[str] = set()
    result: list[dict] = []
    for item in urls:
        key = normalize_url(item["url"])
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


# ──────────────────────────────────────────────
# Cache helpers
# ──────────────────────────────────────────────

def load_cache(cache_dir: Path, cache_key: str) -> dict | None:
    """Return cached entry dict, or None if missing or corrupt."""
    cache_file = cache_dir / f"{cache_key}.json"
    if not cache_file.exists():
        return None
    try:
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def is_expired(entry: dict, ttl_days: int) -> bool:
    """Return True if cache entry is older than ttl_days."""
    fetched_at = datetime.fromisoformat(entry["fetched_at"])
    return datetime.now(timezone.utc) - fetched_at > timedelta(days=ttl_days)


def save_cache(cache_dir: Path, cache_key: str, entry: dict) -> None:
    """Write entry JSON to cache file. Creates cache_dir if needed."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{cache_key}.json"
    cache_file.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")


# ──────────────────────────────────────────────
# Fetch helpers
# ──────────────────────────────────────────────

def fetch_via_jina(url: str, api_key: str | None = None) -> tuple[str, str]:
    """
    Fetch URL via Jina Reader API (https://r.jina.ai).
    Returns (content_markdown, title).
    Raises requests.HTTPError or requests.Timeout on failure.
    """
    jina_url = f"{JINA_BASE_URL}/{url}"
    headers = {"Accept": "text/markdown"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = requests.get(jina_url, headers=headers, timeout=30)
    response.raise_for_status()
    content = response.text
    # Extract title from first H1 markdown heading if present
    title = ""
    for line in content.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    return content, title


def fetch_via_wayback(url: str, api_key: str | None = None) -> tuple[str, str]:
    """
    Fetch URL via Wayback Machine archive. Returns (content_markdown, title).
    First checks Wayback availability API, then fetches the archived URL via Jina.
    Raises ValueError if no snapshot is available.
    """
    avail_response = requests.get(WAYBACK_API, params={"url": url}, timeout=15)
    avail_response.raise_for_status()
    data = avail_response.json()
    closest = data.get("archived_snapshots", {}).get("closest", {})
    if not closest or closest.get("status") != "200":
        raise ValueError(f"No Wayback snapshot available for: {url}")
    archive_url = closest["url"]
    return fetch_via_jina(archive_url, api_key)


def fetch_url(url: str, jina_api_key: str | None = None) -> tuple[str, str, str]:
    """
    Fetch URL content with fallback strategy.
    Returns (content, title, method) where method is "jina" or "wayback".
    Raises RuntimeError if all methods fail.
    """
    try:
        content, title = fetch_via_jina(url, jina_api_key)
        return content, title, "jina"
    except Exception:
        pass

    try:
        content, title = fetch_via_wayback(url, jina_api_key)
        return content, title, "wayback"
    except Exception as e:
        raise RuntimeError(f"All fetch methods failed for {url}") from e


# ──────────────────────────────────────────────
# Main processing
# ──────────────────────────────────────────────

def process_urls(
    urls: list[dict],
    cache_dir: Path,
    ttl_days: int,
    jina_api_key: str | None,
) -> tuple[list[dict], list[dict]]:
    """
    Fetch and cache a list of URL dicts. Each dict must have a "url" key.
    Returns (fetched_list, failed_list).
    Never raises — failures are collected in failed_list.
    """
    fetched: list[dict] = []
    failed: list[dict] = []

    for item in urls:
        url = item["url"]
        cache_key = url_cache_key(url)

        # Cache hit?
        cached = load_cache(cache_dir, cache_key)
        if cached is not None and not is_expired(cached, ttl_days):
            fetched.append({
                "url": url,
                "title": cached.get("title", ""),
                "content": cached["content"][:MAX_CONTENT_CHARS],
                "fetch_method": cached.get("fetch_method", "cached"),
                "cache_hit": True,
                "fetched_at": cached["fetched_at"],
                "word_count": len(cached["content"].split()),
            })
            continue

        # Cache miss or expired — fetch
        try:
            content, title, method = fetch_url(url, jina_api_key)
            content = content[:MAX_CONTENT_CHARS]
            now = datetime.now(timezone.utc).isoformat()

            save_cache(cache_dir, cache_key, {
                "url": url,
                "title": title,
                "content": content,
                "fetch_method": method,
                "fetched_at": now,
            })

            fetched.append({
                "url": url,
                "title": title,
                "content": content,
                "fetch_method": method,
                "cache_hit": False,
                "fetched_at": now,
                "word_count": len(content.split()),
            })

        except Exception as exc:
            print(f"[fetch_and_clean] FAILED {url}: {exc}", file=sys.stderr)
            failed.append({
                "url": url,
                "error": str(exc),
                "attempts": ["jina", "wayback"],
            })

    return fetched, failed


# ──────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch and cache URLs for the research pipeline (Tier 2)."
    )
    parser.add_argument("--input", required=True, help="Path to search_context.json")
    parser.add_argument("--output", help="Output path for fetch_results.json (stdout if omitted)")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--ttl-days", type=int, default=DEFAULT_TTL_DAYS)
    parser.add_argument("--dry-run", action="store_true", help="Print URLs; do not fetch")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[fetch_and_clean] ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    search_context: dict = json.loads(input_path.read_text(encoding="utf-8"))
    urls = deduplicate_urls(search_context.get("selected_urls", []))

    if args.dry_run:
        print(f"[fetch_and_clean] Dry run — {len(urls)} URL(s) would be fetched:", file=sys.stderr)
        for item in urls:
            print(f"  {item['url']}", file=sys.stderr)
        return

    jina_api_key: str | None = os.environ.get("JINA_API_KEY")
    cache_dir = Path(args.cache_dir)

    fetched, failed = process_urls(urls, cache_dir, args.ttl_days, jina_api_key)

    result = {
        "topic": search_context.get("topic", ""),
        "search_context": search_context,
        "fetched": fetched,
        "failed": failed,
        "stats": {
            "total_urls": len(urls),
            "fetched": len(fetched),
            "failed": len(failed),
            "cache_hits": sum(1 for f in fetched if f["cache_hit"]),
            "total_words": sum(f["word_count"] for f in fetched),
        },
    }

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output_json, encoding="utf-8")
        print(f"[fetch_and_clean] Results written to {output_path}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
```

---

**Step 4: Install `requests` if not already present**

```bash
C:\Users\tim\AppData\Local\Programs\Python\Python312\Scripts\pip.exe install requests
```

---

**Step 5: Run tests to confirm they PASS**

```bash
C:\Users\tim\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe C:\Users\tim\OneDrive\Documents\Projects\research-workflow\tests\test_fetch_and_clean.py -v
```
Expected: all tests PASS.

---

**Step 6: Run full test suite**

```bash
C:\Users\tim\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe C:\Users\tim\OneDrive\Documents\Projects\research-workflow\tests\ -v
```
Expected: all tests pass.

---

**Step 7: Commit**

```bash
git -C "C:\Users\tim\OneDrive\Documents\Projects\research-workflow" add fetch_and_clean.py tests/test_fetch_and_clean.py requirements.txt
git -C "C:\Users\tim\OneDrive\Documents\Projects\research-workflow" commit -m "feat: add fetch_and_clean.py — Tier 2 URL fetch/cache layer"
```

> Note: if `requests` was already in requirements.txt, skip adding it. If not, add it: `echo requests >> requirements.txt` before committing.

---

## Task 4: Create `research-search` skill

New Haiku skill replacing the search/URL-selection portion of `research-haiku`. Outputs a `search_context` JSON object.

**Files:**
- Create: `C:\Users\tim\.claude\skills\research-search\SKILL.md`

No automated tests — skill files are Claude Code markdown skills. Validate manually: call `/research "test topic"` after Task 7 (full pipeline wired up).

---

**Step 1: Create the skill directory and file**

Create `C:\Users\tim\.claude\skills\research-search\SKILL.md`:

```markdown
---
name: research-search
description: Haiku search agent for the vault research pipeline. Spawned internally by the research skill. Do not invoke directly.
---

# Research — Search Agent (Tier 1)

## CRITICAL: Model Check

Before doing ANYTHING else, check your system prompt for your model identity.

Find the line: "You are powered by the model named..."

If that line is not present in your system prompt, OR if it does not say `claude-haiku-4-5-20251001`:
- Output exactly: `ERROR: research-search requires claude-haiku-4-5-20251001. Running on wrong model. Aborting.`
- Stop immediately.

Only continue past this point if you have confirmed you are Haiku.

---

## Your Role

**Do not write, create, edit, or delete any files.**

**Output only the single JSON object described in Step 3. No narration, no explanation, no backticks.**

You are the search and URL selection agent. Given a topic string, you will:
1. Search the web for relevant sources
2. Evaluate results and select the best 3–7 URLs
3. Output a single raw JSON object — nothing else

---

## Input

You will receive:
- `topic` — the research topic string

---

## Step 1: Search

Run 1–3 WebSearch queries for the topic (vary phrasing if initial results are weak). Collect all result URLs and snippets.

## Step 2: Evaluate and Select URLs

For each candidate result:
- Score relevance 1–10 (10 = directly addresses the topic)
- Prefer: credible journalism, government sources, org websites, academic sources
- Avoid: paywalled sites, aggregators without original content, obvious spam
- Select the top 3–7 URLs

For each rejected URL, briefly note why.

Do not fetch the full content of any page. Use snippets and titles only for evaluation.

## Step 3: Output

Your entire response is a single JSON object. Rules:
- First character must be `{`
- Last character must be `}`
- No backticks, no markdown fences, no narration before or after

{
  "topic": "the topic string you were given",
  "query_used": "the exact search query string you used",
  "selected_urls": [
    {
      "url": "https://...",
      "title": "page title",
      "snippet": "brief description from search results",
      "relevance_score": 8,
      "reason": "primary source covering the topic directly"
    }
  ],
  "rejected_urls": [
    {
      "url": "https://...",
      "reason": "paywall"
    }
  ],
  "search_notes": "any observations about the search landscape, or empty string"
}
```

---

**Step 2: Verify file was created**

```bash
cat "C:/Users/tim/.claude/skills/research-search/SKILL.md" | head -5
```
Expected: shows the frontmatter `---` and `name: research-search`.

---

**Step 3: Commit**

```bash
git -C "C:\Users\tim\OneDrive\Documents\Projects\research-workflow" add "C:\Users\tim\.claude\skills\research-search\SKILL.md"
git -C "C:\Users\tim\OneDrive\Documents\Projects\research-workflow" commit -m "feat: add research-search skill (Tier 1 Haiku search agent)"
```

> Note: This file is outside the research-workflow directory. If it's not tracked by this repo, commit it to whichever git repo covers `C:\Users\tim\.claude\`.

---

## Task 5: Create `research-classify` skill

New Haiku skill replacing the classification/vault-mapping portion of `research-haiku`. Receives `fetch_results` JSON in its prompt and outputs a `classification` JSON object.

**Files:**
- Create: `C:\Users\tim\.claude\skills\research-classify\SKILL.md`

---

**Step 1: Create the skill file**

Create `C:\Users\tim\.claude\skills\research-classify\SKILL.md`:

```markdown
---
name: research-classify
description: Haiku classification agent for the vault research pipeline. Spawned internally by the research skill. Do not invoke directly.
---

# Research — Classify Agent (Tier 3)

## CRITICAL: Model Check

Before doing ANYTHING else, check your system prompt for your model identity.

Find the line: "You are powered by the model named..."

If that line is not present, OR if it does not say `claude-haiku-4-5-20251001`:
- Output exactly: `ERROR: research-classify requires claude-haiku-4-5-20251001. Running on wrong model. Aborting.`
- Stop immediately.

Only continue past this point if you have confirmed you are Haiku.

---

## Your Role

**Do not write, create, edit, or delete any files.**

**Output only the single JSON object described in Step 4. No narration. No backticks.**

You are the classification and vault-mapping agent. Given cleaned article content (from `fetch_and_clean.py`) you will:
1. Build the vault file list
2. For each fetched article, classify content and determine vault placement
3. Output a single raw JSON object

---

## Input

You will receive a `fetch_results` JSON object (inline in this prompt) with this structure:
- `topic` — original research topic
- `search_context` — search metadata passthrough
- `fetched` — list of `{ url, title, content, ... }` objects
- `failed` — URLs that could not be fetched

Vault root: `C:\Users\tim\OneDrive\Documents\Tim's Vault`

---

## Step 1: Build Vault File List

Use the Glob tool:
- Pattern: `**/*.md`
- Path: `C:\Users\tim\OneDrive\Documents\Tim's Vault`

Store the full list of relative file paths. Strip the vault root prefix to get relative paths.

## Step 2: Discover MOC Notes

Flag files as potential MOC/index notes if they match ANY of:
- Filename starts with `_`
- Filename contains: `MOC`, `Index`, `Hub`, `Overview`, `Dashboard`, or `000`
- The file's immediate parent directory contains 5 or more `.md` files

## Step 3: Classify Each Article

For each item in `fetched`, determine:

**Content type:**
- `campaign` — local/municipal effort to restrict, ban, or oppose a surveillance technology or vendor
- `legislation` — a bill, ordinance, or law being proposed, amended, or passed
- `general_research` — background, analysis, journalism, organization profiles, reference material

**Vault match:**
Scan the full file list for notes whose filenames closely match the article's subject.
- Close match found → `action: "update"`, `existing_note: relative/path`
- No match → `action: "create"`, `existing_note: null`

**Target path:**
- For `update`: use the exact existing note path
- For `create`: find 2–3 thematically similar notes in the file list and use their parent folder. Follow the naming convention of notes in that folder.

**Relevant files:**
Include notes that are: the matching note (if any), 1–3 closely related notes for format reference, MOC notes in the same folder area. Keep to 3–6 files maximum.

**Tags and links:**
- `suggested_tags`: 2–4 tags appropriate for this note (see vault CLAUDE.md for tagging conventions)
- `suggested_links`: existing vault notes whose topics appear in this article, formatted as `[[Note Title]]`
- `stub_links`: concepts, people, or organizations worth researching later that don't have notes yet

## Step 4: Output

Your entire response is a single JSON object. Rules:
- First character must be `{`
- Last character must be `}`
- No backticks, no fences, no narration

{
  "topic": "original topic string",
  "search_context": { "passthrough": "from fetch_results" },
  "notes_to_create": [
    {
      "title": "Proposed Note Title",
      "filename": "Proposed Note Title.md",
      "folder": "Areas/Activism/Surveillance/",
      "content_summary": "What this note should contain — key facts, arguments, context from the article",
      "source_urls": ["https://..."],
      "suggested_tags": ["research", "surveillance", "greenville-sc"],
      "suggested_links": ["[[Related Existing Note]]"],
      "stub_links": ["[[Topic To Research Later]]"],
      "priority": "primary"
    }
  ],
  "vault_context": {
    "existing_notes_found": ["relative/path/to/relevant/existing.md"],
    "suggested_moc_update": "relative/path/to/moc.md or null"
  }
}
```

---

**Step 2: Verify file was created**

```bash
cat "C:/Users/tim/.claude/skills/research-classify/SKILL.md" | head -5
```
Expected: shows frontmatter with `name: research-classify`.

---

**Step 3: Commit**

```bash
git -C "C:\Users\tim\OneDrive\Documents\Projects\research-workflow" add "C:\Users\tim\.claude\skills\research-classify\SKILL.md"
git -C "C:\Users\tim\OneDrive\Documents\Projects\research-workflow" commit -m "feat: add research-classify skill (Tier 3 Haiku classify agent)"
```

---

## Task 6: Update `research` orchestrator skill

Wire the three tiers together. The orchestrator now: (1) spawns `research-search` for topics, (2) runs `fetch_and_clean.py` via Bash, (3) spawns `research-classify`, (4) writes notes using the classification output.

**Files:**
- Modify: `C:\Users\tim\.claude\skills\research\SKILL.md`

---

**Step 1: Read the current skill file**

Read `C:\Users\tim\.claude\skills\research\SKILL.md` in full before editing. The current file has 6 steps. The new version replaces Steps 2–4 with a 3-tier flow while keeping Steps 1 and 5–6 (note writing and summary) mostly intact.

---

**Step 2: Replace the full content of the research skill**

Overwrite `C:\Users\tim\.claude\skills\research\SKILL.md` with:

```markdown
---
name: research
description: Research a topic or note and write results into the Obsidian vault. Usage: /research path/to/note.md  OR  /research "topic string". Runs as Sonnet; spawns Haiku agents for search and classification.
---

# Research — Sonnet Orchestrator (3-Tier Pipeline)

## CRITICAL: Model Check

Before doing ANYTHING else, check your context window for your model identity.

Find the line: "You are powered by the model named..."

If that line is not present, OR if it does not say `claude-sonnet-4-6`:
- Output exactly: `ERROR: research requires claude-sonnet-4-6. Running on wrong model. Aborting.`
- Stop immediately.

Only continue past this point if you have confirmed you are Sonnet 4.6.

---

## Your Role

You orchestrate research into the vault using a 3-tier pipeline:
1. **Haiku search** — finds and evaluates URLs for a topic
2. **Python fetch** — fetches and caches page content via Jina Reader
3. **Haiku classify** — maps content to vault structure
4. **Sonnet write** — you synthesize and write the final notes

Vault root: `C:\Users\tim\OneDrive\Documents\Tim's Vault`
Scripts dir: `C:\Users\tim\OneDrive\Documents\Projects\research-workflow`
Python: `C:\Users\tim\AppData\Local\Programs\Python\Python312\python.exe`

---

## Step 1: Parse Input

The argument is everything after `/research `.

**If it looks like a file path** (contains `/` or `\` or ends in `.md`):
- Read the note at that path (relative to vault root)
- Extract `known_urls`: all `http://` or `https://` URLs in the note text
- Extract `topics`: headings, named campaigns, organizations, people, bill numbers, questions without a URL

**If it is a plain string:**
- `known_urls`: []
- `topics`: [the full input string]

---

## Step 2: Build Search Context

**Case A — Topics only (no known URLs):**

Read the `research-search` skill:
`C:\Users\tim\.claude\skills\research-search\SKILL.md`

For each topic, spawn a Haiku agent:
- `subagent_type`: `general-purpose`
- `model`: `haiku`
- `prompt`: research-search skill content + this input block:

```
---
topic: [the topic string]
```

Wait for the response. Extract the JSON object from the response (first `{` to last `}`). If it starts with `ERROR:`, output it and stop.

Collect all `selected_urls` arrays from all topic responses into a combined list. Build a single `search_context.json` with:
- `topic`: the first topic (or combined topic string if multiple)
- `query_used`: from the agent response
- `selected_urls`: combined deduplicated list
- `rejected_urls`: combined list
- `search_notes`: combined notes

**Case B — Known URLs only (no topics):**

Skip the Haiku search agent. Build `search_context.json` directly:
```json
{
  "topic": "[derived from note title or first heading]",
  "query_used": "",
  "selected_urls": [
    { "url": "[each known_url]", "title": "", "snippet": "", "relevance_score": 10, "reason": "provided directly" }
  ],
  "rejected_urls": [],
  "search_notes": "URLs provided directly, search skipped"
}
```

**Case C — Both topics and known URLs:**

Run Case A for topics, then add the known URLs to `selected_urls` with `relevance_score: 10` and `reason: "provided directly"`.

---

## Step 3: Fetch Content via Python

Write the `search_context` JSON to a temporary file:
- Path: `C:\Users\tim\OneDrive\Documents\Projects\research-workflow\.tmp\search_context.json`
- Create the `.tmp` directory if it doesn't exist (use Bash: `mkdir -p .tmp`)

Run the fetch script:
```bash
"C:\Users\tim\AppData\Local\Programs\Python\Python312\python.exe" "C:\Users\tim\OneDrive\Documents\Projects\research-workflow\fetch_and_clean.py" --input "C:\Users\tim\OneDrive\Documents\Projects\research-workflow\.tmp\search_context.json" --output "C:\Users\tim\OneDrive\Documents\Projects\research-workflow\.tmp\fetch_results.json"
```

Wait for it to complete. If it exits with a non-zero code, output the stderr and stop.

Read `fetch_results.json` from `.tmp\fetch_results.json`.

If `fetched` is empty and `failed` is non-empty, output:
`Fetch failed for all URLs. Errors: [list failed[].error]`
Then stop.

If `failed` is non-empty but `fetched` is not empty, print a warning:
`Warning: Could not fetch: [list failed[].url]`
Then continue.

---

## Step 4: Classify via Haiku

Read the `research-classify` skill:
`C:\Users\tim\.claude\skills\research-classify\SKILL.md`

Spawn a Haiku agent:
- `subagent_type`: `general-purpose`
- `model`: `haiku`
- `prompt`: research-classify skill content + the full contents of `fetch_results.json` appended after a `---` separator

Wait for the response. Extract the JSON object (first `{` to last `}`). If it starts with `ERROR:`, output it and stop.

If `notes_to_create` is empty, output:
`Classification returned no notes to create. Check fetch results for content quality.`
Then stop.

---

## Step 5: Write Notes

For each entry in `notes_to_create`:

### 5a. Read relevant files

Read all files in `vault_context.existing_notes_found` plus any notes referenced in `suggested_links`. Store contents keyed by path.

### 5b. Synthesize note content

Write the complete note content following ALL of these rules:

**Wikilinks:**
- Add `[[wikilinks]]` from `suggested_links` where the topic appears in the note
- Add `[[stub_links]]` for concepts in `stub_links` that don't have notes yet

**Tags:**
- Include `suggested_tags` in the frontmatter YAML

**Sources:**
- Include the full source URL inline at the point where first referenced
- Add a `## Sources` section at the bottom listing all `source_urls`

**Format matching:**
- If `action` is `update` or `folder` contains existing notes, match their section structure exactly
- For campaign notes: match the format of existing campaign notes in that folder

**For `create`:** Write the complete new note from scratch using `content_summary` as your guide.

**For `update`:** Merge new information into the existing note. Expand sections. Never discard existing content.

### 5c. Write the note

- `create`: Write to `C:\Users\tim\OneDrive\Documents\Tim's Vault\{folder}\{filename}`
- `update`: Overwrite the existing note path

### 5d. Update MOC notes

If `suggested_moc_update` is not null, read that MOC file and add/update an entry for the note just written. Match the MOC's existing format exactly.

Also check if the folder containing the target note has any file starting with `_` or containing `MOC`, `Index`, `Hub`, or `Overview` that wasn't already in `existing_notes_found` — if so, update it too.

---

## Step 6: Print Summary

```
Research complete.

Created:
  - [path of each created note, or "none"]

Updated:
  - [path of each updated note and MOC, or "none"]

Warnings:
  - [any fetch failures or issues, or "none"]
```
```

---

**Step 3: Verify the file was written**

```bash
head -10 "C:/Users/tim/.claude/skills/research/SKILL.md"
```
Expected: shows the updated frontmatter and `# Research — Sonnet Orchestrator (3-Tier Pipeline)` heading.

---

**Step 4: Commit**

```bash
git -C "C:\Users\tim\OneDrive\Documents\Projects\research-workflow" add "C:\Users\tim\.claude\skills\research\SKILL.md"
git -C "C:\Users\tim\OneDrive\Documents\Projects\research-workflow" commit -m "feat: update research skill orchestrator for 3-tier pipeline"
```

---

## Task 7: Deprecate `research-haiku` skill

Add a deprecation notice to the top of `research-haiku` SKILL.md. Keep the file and all content intact for rollback purposes.

**Files:**
- Modify: `C:\Users\tim\.claude\skills\research-haiku\SKILL.md` — prepend deprecation block only

---

**Step 1: Prepend deprecation notice**

Add to the very top of `C:\Users\tim\.claude\skills\research-haiku\SKILL.md`, before the `---` frontmatter:

```
> **DEPRECATED as of 2026-02-25.**
> This skill has been replaced by the 3-tier pipeline:
> - Tier 1 search: `research-search` skill
> - Tier 2 fetch: `fetch_and_clean.py` script
> - Tier 3 classify: `research-classify` skill
>
> This file is kept for rollback reference only. Do not invoke directly.
> The `research` orchestrator skill no longer references this file.

```

(The existing `---` frontmatter block should remain immediately after this notice.)

---

**Step 2: Commit**

```bash
git -C "C:\Users\tim\OneDrive\Documents\Projects\research-workflow" add "C:\Users\tim\.claude\skills\research-haiku\SKILL.md"
git -C "C:\Users\tim\OneDrive\Documents\Projects\research-workflow" commit -m "chore: deprecate research-haiku skill, replaced by 3-tier pipeline"
```

---

## Task 8: Update vault CLAUDE.md

Add a scripts reference section to `C:\Users\tim\OneDrive\Documents\Tim's Vault\CLAUDE.md`.

**Files:**
- Modify: `C:\Users\tim\OneDrive\Documents\Tim's Vault\CLAUDE.md` — append new section

---

**Step 1: Read the current CLAUDE.md**

Read `C:\Users\tim\OneDrive\Documents\Tim's Vault\CLAUDE.md` in full before editing.

---

**Step 2: Append the scripts section**

Add this section at the end of the file (after the last existing section):

```markdown
## Research Workflow Scripts

Scripts live in `C:\Users\tim\OneDrive\Documents\Projects\research-workflow\`.
Python: `C:\Users\tim\AppData\Local\Programs\Python\Python312\python.exe`

### Research Pipeline (invoked automatically via `/research` skill)

- `fetch_and_clean.py` — Tier 2: fetches URLs via Jina Reader API, caches by MD5 (7-day TTL), Wayback Machine fallback
- Skills involved: `research-search` (Haiku, Tier 1), `research-classify` (Haiku, Tier 3)

### Post-Research Toolkit (invoke manually after research is complete)

| Script | Purpose | Example |
|--------|---------|---------|
| `synthesize_folder.py` | Synthesize a folder of notes into a MOC/overview via Sonnet | `python synthesize_folder.py --folder "Research/Topic" --output "Topic-MOC.md"` |
| `produce_output.py` | Transform a note into a downstream format (article, script, briefing, etc.) | `python produce_output.py --file Note.md --format web_article` |
| `daily_digest.py` | Generate a date-stamped digest of vault activity | `python daily_digest.py` |
| `find_related.py` | Find semantically related notes | `python find_related.py --note Note.md` |
| `find_broken_links.py` | Audit vault for broken wikilinks | `python find_broken_links.py` |
| `vault_lint.py` | Check notes for formatting/tagging issues | `python vault_lint.py` |
| `discover_vault.py` | Regenerate vault structure map (run after vault reorganization) | `python discover_vault.py` |

### Available Output Formats for `produce_output.py`

Run `python produce_output.py --list-formats` to see current formats.
Built-in: `web_article`, `video_script`, `social_post`, `briefing`, `talking_points`, `email_newsletter`
```

---

**Step 3: Commit**

```bash
git -C "C:\Users\tim\OneDrive\Documents\Projects\research-workflow" add "C:\Users\tim\OneDrive\Documents\Tim's Vault\CLAUDE.md"
git -C "C:\Users\tim\OneDrive\Documents\Projects\research-workflow" commit -m "docs: add research workflow scripts section to vault CLAUDE.md"
```

---

## Task 9: Run full test suite and verify

**Step 1: Run all tests**

```bash
C:\Users\tim\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe C:\Users\tim\OneDrive\Documents\Projects\research-workflow\tests\ -v
```
Expected: all tests pass (72 original + new tests for `fetch_and_clean.py` and `produce_output.py`).

**Step 2: Smoke test `fetch_and_clean.py` with a dry run**

Create a minimal test input file:
```bash
echo '{"topic": "test", "selected_urls": [{"url": "https://example.com"}]}' > /tmp/sc_test.json
"C:\Users\tim\AppData\Local\Programs\Python\Python312\python.exe" "C:\Users\tim\OneDrive\Documents\Projects\research-workflow\fetch_and_clean.py" --input /tmp/sc_test.json --dry-run
```
Expected output: `[fetch_and_clean] Dry run — 1 URL(s) would be fetched:` followed by the URL.

**Step 3: Verify model change is picked up**

```bash
"C:\Users\tim\AppData\Local\Programs\Python\Python312\python.exe" -c "import sys; sys.path.insert(0, 'C:/Users/tim/OneDrive/Documents/Projects/research-workflow'); import config; print(config.CLAUDE_MODEL_HEAVY)"
```
Expected: `claude-sonnet-4-6`

---

## Implementation Order Summary

| Task | Description | Risk |
|------|-------------|------|
| 1 | Opus → Sonnet default in config | Low — constant change |
| 2 | `produce_output.py` filename fix | Low — logic change + tests |
| 3 | `fetch_and_clean.py` | Medium — new script, network mocking |
| 4 | `research-search` skill | Low — markdown file |
| 5 | `research-classify` skill | Low — markdown file |
| 6 | Update `research` orchestrator | Medium — wires all tiers together |
| 7 | Deprecate `research-haiku` | Low — prepend comment only |
| 8 | Update vault CLAUDE.md | Low — append only |
| 9 | Full test + smoke test | Verification only |
