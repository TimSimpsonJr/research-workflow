"""
search_searxng.py -- SearXNG search backend for the full infrastructure tier.

Queries a SearXNG instance and returns scored results compatible with
the search-agent output format.

Usage:
    python search_searxng.py --query "ALPR surveillance SC" --url http://localhost:8888
    python search_searxng.py --query "ALPR surveillance SC" --url http://localhost:8888 --output results.json
    python search_searxng.py --query "ALPR surveillance SC" --url http://localhost:8888 --engines google,duckduckgo

Dependencies: requests
"""

import argparse
import json
import sys
from urllib.parse import urlencode

import requests


# ──────────────────────────────────────────────
# Source quality scoring
# ──────────────────────────────────────────────

# Primary sources: government, education, court records
_PRIMARY_DOMAINS = {
    ".gov", ".edu", ".mil",
}
_PRIMARY_KEYWORDS = {
    "courtlistener.com", "pacer.gov", "uscourts.gov",
    "regulations.gov", "federalregister.gov",
    "legislature.gov", "legis.state",
}

# Secondary sources: major journalism, academic journals, established nonprofits
_SECONDARY_DOMAINS = {
    "reuters.com", "apnews.com", "propublica.org",
    "nytimes.com", "washingtonpost.com", "theguardian.com",
    "bbc.com", "bbc.co.uk", "npr.org", "pbs.org",
    "arstechnica.com", "theatlantic.com", "wired.com",
    "nature.com", "sciencedirect.com", "springer.com",
    "jstor.org", "arxiv.org", "pubmed.ncbi.nlm.nih.gov",
    "aclu.org", "eff.org", "brennancenter.org",
}

# Tertiary indicators: blogs, aggregators, forums
_TERTIARY_KEYWORDS = {
    "reddit.com", "quora.com", "medium.com",
    "blogspot.com", "wordpress.com", "tumblr.com",
    "stackexchange.com", "stackoverflow.com",
    "facebook.com", "twitter.com", "x.com",
}


def score_source(url: str) -> tuple[int, str]:
    """Score a URL by source quality.

    Returns (score, quality_tier) where:
      - score 3, "primary"   -- .gov, .edu, court records
      - score 2, "secondary" -- major journalism, academic journals
      - score 1, "tertiary"  -- blogs, aggregators, forums, everything else
    """
    url_lower = url.lower()

    # Check primary: TLD-based
    for tld in _PRIMARY_DOMAINS:
        # Match domain endings like ".gov/" or ".gov" at end, also subdomains like "sc.gov"
        if tld in url_lower.split("//", 1)[-1].split("/", 1)[0]:
            return 3, "primary"

    # Check primary: keyword-based (court records, etc.)
    for keyword in _PRIMARY_KEYWORDS:
        if keyword in url_lower:
            return 3, "primary"

    # Check secondary: known domains
    for domain in _SECONDARY_DOMAINS:
        if domain in url_lower:
            return 2, "secondary"

    # Check tertiary: known low-quality domains
    for keyword in _TERTIARY_KEYWORDS:
        if keyword in url_lower:
            return 1, "tertiary"

    # Default: tertiary for unknown sources
    return 1, "tertiary"


# ──────────────────────────────────────────────
# SearXNG search
# ──────────────────────────────────────────────

def search(
    query: str,
    searxng_url: str,
    engines: list[str] | None = None,
    max_results: int = 10,
) -> list[dict]:
    """Query a SearXNG instance and return scored results.

    Args:
        query: Search query string.
        searxng_url: Base URL of the SearXNG instance (e.g., http://localhost:8888).
        engines: Optional list of engine names to use (e.g., ["google", "duckduckgo"]).
        max_results: Maximum number of results to return.

    Returns:
        List of result dicts with keys: url, title, snippet, source_score, source_quality, engine.

    Raises:
        requests.exceptions.ConnectionError: If SearXNG is unreachable.
        requests.exceptions.HTTPError: If SearXNG returns an error status.
    """
    base = searxng_url.rstrip("/")
    params: dict[str, str] = {
        "q": query,
        "format": "json",
    }
    if engines:
        params["engines"] = ",".join(engines)

    resp = requests.get(f"{base}/search", params=params, timeout=15)
    resp.raise_for_status()

    data = resp.json()
    raw_results = data.get("results", [])

    scored: list[dict] = []
    seen_urls: set[str] = set()

    for item in raw_results:
        url = item.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        source_score, source_quality = score_source(url)
        scored.append({
            "url": url,
            "title": item.get("title", ""),
            "snippet": item.get("content", ""),
            "source_score": source_score,
            "source_quality": source_quality,
            "engine": item.get("engine", "unknown"),
        })

        if len(scored) >= max_results:
            break

    # Sort by source_score descending, then by original order
    scored.sort(key=lambda r: r["source_score"], reverse=True)
    return scored


# ──────────────────────────────────────────────
# Pipeline format conversion
# ──────────────────────────────────────────────

def format_for_pipeline(results: list[dict]) -> list[dict]:
    """Convert SearXNG scored results to the search-agent output format.

    The search-agent produces selected_urls entries with:
      url, title, snippet, relevance_score, source_quality, reason

    This function maps SearXNG results to that same shape so they
    can be merged into the pipeline seamlessly.
    """
    formatted: list[dict] = []
    for r in results:
        # Map source_score (1-3) to relevance_score (1-10 scale)
        # Primary=3 -> 8, Secondary=2 -> 6, Tertiary=1 -> 4
        relevance = r["source_score"] * 2 + 2
        formatted.append({
            "url": r["url"],
            "title": r["title"],
            "snippet": r["snippet"],
            "relevance_score": relevance,
            "source_quality": r["source_quality"],
            "reason": f"SearXNG result via {r.get('engine', 'unknown')} — {r['source_quality']} source",
        })
    return formatted


# ──────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search via SearXNG and return scored results."
    )
    parser.add_argument("--query", required=True, help="Search query string")
    parser.add_argument("--url", required=True, help="SearXNG instance URL (e.g., http://localhost:8888)")
    parser.add_argument("--engines", help="Comma-separated engine list (e.g., google,duckduckgo)")
    parser.add_argument("--max-results", type=int, default=10, help="Max results to return (default: 10)")
    parser.add_argument("--output", help="Output path for results JSON (stdout if omitted)")
    parser.add_argument("--pipeline-format", action="store_true",
                        help="Output in search-agent pipeline format")
    args = parser.parse_args()

    engines = args.engines.split(",") if args.engines else None

    try:
        results = search(
            query=args.query,
            searxng_url=args.url,
            engines=engines,
            max_results=args.max_results,
        )
    except requests.exceptions.ConnectionError:
        print(f"[search_searxng] ERROR: Cannot connect to SearXNG at {args.url}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.HTTPError as exc:
        print(f"[search_searxng] ERROR: SearXNG returned error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.pipeline_format:
        output_data = format_for_pipeline(results)
    else:
        output_data = results

    output_json = json.dumps(output_data, ensure_ascii=False, indent=2)

    if args.output:
        from pathlib import Path
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"[search_searxng] Results written to {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
