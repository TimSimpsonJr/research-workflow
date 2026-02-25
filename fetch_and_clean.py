"""
fetch_and_clean.py — URL Fetch, Clean, and Cache

Purpose: Tier 2 of the research pipeline. Accepts a search_context JSON,
fetches each URL via Jina Reader (with Wayback Machine fallback), caches
results by MD5(url), and outputs fetch_results JSON.

Usage:
    python fetch_and_clean.py --input search_context.json
    python fetch_and_clean.py --input search_context.json --output fetch_results.json
    python fetch_and_clean.py --input search_context.json --dry-run

Dependencies: requests
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
    try:
        fetched_at = datetime.fromisoformat(entry["fetched_at"])
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - fetched_at > timedelta(days=ttl_days)
    except (KeyError, ValueError, TypeError):
        return True  # Treat unparseable entries as expired


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
    """
    jina_url = f"{JINA_BASE_URL}/{url}"
    headers = {"Accept": "text/markdown"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = requests.get(jina_url, headers=headers, timeout=30)
    response.raise_for_status()
    content = response.text
    title = ""
    for line in content.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    return content, title


def fetch_via_wayback(url: str, api_key: str | None = None) -> tuple[str, str]:
    """
    Fetch URL via Wayback Machine archive.
    Returns (content_markdown, title).
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
            truncated = cached["content"][:MAX_CONTENT_CHARS]
            fetched.append({
                "url": url,
                "title": cached.get("title", ""),
                "content": truncated,
                "fetch_method": cached.get("fetch_method", "cached"),
                "cache_hit": True,
                "fetched_at": cached["fetched_at"],
                "word_count": len(truncated.split()),
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
