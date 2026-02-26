"""
ingest.py — URL to Vault Inbox

Purpose: Fetch a URL via Jina Reader, write a clean markdown note to the vault inbox.

Usage:
    python ingest.py "https://example.com/article"
    python ingest.py "https://example.com/article" --dry-run

Dependencies: requests, rich, python-dotenv
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from rich.console import Console

import config
from fetch_and_clean import validate_url
from utils import slugify, startup_checks

console = Console()


def extract_title(content: str, url: str) -> str:
    """Extract title from first # heading, fall back to domain."""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return urlparse(url).netloc


def build_frontmatter(
    title: str,
    source: str,
    fetched_at: str,
    tag_format: str,
    extra_fields: list[str],
) -> str:
    """Build YAML frontmatter matching vault conventions."""
    if tag_format == "inline":
        tags_line = "tags: [inbox, unprocessed]"
    else:
        tags_line = "tags:\n  - inbox\n  - unprocessed"

    extras = "\n".join(f"{field}: " for field in extra_fields
                       if field and field not in {"title", "source", "fetched_at", "tags"})
    extras_block = f"\n{extras}" if extras else ""

    # Quote title to handle colons, hashes, or other YAML special characters
    safe_title = title.replace('"', '\\"')
    return (
        f"---\n"
        f'title: "{safe_title}"\n'
        f"source: {source}\n"
        f"fetched_at: {fetched_at}\n"
        f"{tags_line}{extras_block}\n"
        f"---\n\n"
    )


def unique_output_path(inbox_path: Path, date: str, slug: str) -> Path:
    """Return a unique file path, appending -2, -3, etc. if needed."""
    base = inbox_path / f"{date}-{slug}.md"
    if not base.exists():
        return base
    counter = 2
    while True:
        candidate = inbox_path / f"{date}-{slug}-{counter}.md"
        if not candidate.exists():
            return candidate
        counter += 1


def fetch_url(url: str) -> str:
    """Fetch URL via Jina Reader and return markdown content.

    Raises ValueError if the URL targets a private/internal address.
    """
    validate_url(url)
    jina_url = f"{config.JINA_BASE_URL}/{url}"
    response = requests.get(jina_url, timeout=30)
    response.raise_for_status()
    return response.text


def ingest_url(url: str, dry_run: bool = False) -> Path | None:
    """Core ingestion logic. Returns output path or None on dry run."""
    console.print(f"Fetching: {url}")
    with console.status("Fetching via Jina Reader..."):
        content = fetch_url(url)

    title = extract_title(content, url)
    slug = slugify(title) or slugify(urlparse(url).netloc) or "untitled"
    now = datetime.now(timezone.utc)
    date_str = now.strftime(config.DATE_FORMAT)
    fetched_at = now.isoformat()

    frontmatter = build_frontmatter(
        title=title,
        source=url,
        fetched_at=fetched_at,
        tag_format=config.TAG_FORMAT,
        extra_fields=config.FRONTMATTER_FIELDS,
    )
    full_content = frontmatter + content

    if dry_run:
        preview_path = unique_output_path(config.INBOX_PATH, date_str, slug)
        console.print(f"[yellow]Dry run — would write to: {preview_path}[/yellow]")
        preview = full_content[:300]
        if len(full_content) > 300:
            preview += "..."
        console.print(preview)
        return None

    out_path = unique_output_path(config.INBOX_PATH, date_str, slug)
    out_path.write_text(full_content, encoding="utf-8", newline="\n")
    console.print(f"[green]Written:[/green] {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Fetch a URL and save to vault inbox.")
    parser.add_argument("url", help="URL to fetch")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    startup_checks(require_api_key=True, ensure_inbox=True)
    ingest_url(args.url, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
