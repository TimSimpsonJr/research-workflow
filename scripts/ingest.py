"""
ingest.py — URL to Vault Inbox

Purpose: Fetch a URL via Jina Reader, write a clean markdown note to the vault inbox.
Optionally extracts embedded media (images, YouTube) and downloads them to the vault
attachments folder with citation tracking.

Usage:
    python ingest.py "https://example.com/article"
    python ingest.py "https://example.com/article" --dry-run
    python ingest.py "https://example.com/article" --no-media

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

    # Quote title and source to handle colons, hashes, newlines, or other YAML special characters
    safe_title = title.replace("\n", " ").replace("\r", " ").replace('"', '\\"')
    safe_source = source.replace("\n", "").replace("\r", "").replace('"', '\\"')
    return (
        f"---\n"
        f'title: "{safe_title}"\n'
        f'source: "{safe_source}"\n'
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


def ingest_url(url: str, dry_run: bool = False, extract_media: bool = True) -> Path | None:
    """Core ingestion logic. Returns output path or None on dry run.

    Args:
        url: URL to fetch.
        dry_run: Preview without writing.
        extract_media: If True, download embedded images and process YouTube
            URLs found in the content. Saves media to vault attachments folder.
    """
    console.print(f"Fetching: {url}")
    with console.status("Fetching via Jina Reader..."):
        content = fetch_url(url)

    title = extract_title(content, url)
    slug = slugify(title) or slugify(urlparse(url).netloc) or "untitled"
    now = datetime.now(timezone.utc)
    date_str = now.strftime(config.DATE_FORMAT)
    fetched_at = now.isoformat()

    # Media extraction: download embedded images, process YouTube URLs
    citations = []
    if extract_media and not dry_run:
        try:
            from media_handler import extract_and_download_media
            attachments_dir = getattr(config, "ATTACHMENTS_PATH", None)
            if not attachments_dir:
                attachments_dir = config.VAULT_PATH / "Attachments"
            with console.status("Extracting embedded media..."):
                content, citations = extract_and_download_media(
                    markdown=content,
                    attachments_dir=attachments_dir,
                    slug=slug,
                    vault_root=config.VAULT_PATH,
                    source_url=url,
                )
            if citations:
                console.print(f"[green]Extracted {len(citations)} media asset(s)[/green]")
        except ImportError:
            pass  # media_handler not available, skip

    frontmatter = build_frontmatter(
        title=title,
        source=url,
        fetched_at=fetched_at,
        tag_format=config.TAG_FORMAT,
        extra_fields=config.FRONTMATTER_FIELDS,
    )

    # Inject citation metadata into frontmatter if we have any
    if citations:
        from media_handler import inject_citations_into_frontmatter, append_sources_section
        frontmatter = inject_citations_into_frontmatter(frontmatter, citations)
        content = append_sources_section(content, citations)

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
    parser.add_argument("--no-media", action="store_true",
                        help="Skip media extraction (images, YouTube)")
    args = parser.parse_args()

    startup_checks(require_api_key=True, ensure_inbox=True)
    ingest_url(args.url, dry_run=args.dry_run, extract_media=not args.no_media)


if __name__ == "__main__":
    main()
