"""
ingest_batch.py — Batch URL Ingestion

Purpose: Process a list of URLs from a text file.

Usage:
    python ingest_batch.py urls.txt
    python ingest_batch.py urls.txt --dry-run

Dependencies: rich, python-dotenv (ingest.py for core logic)
"""

import argparse
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.progress import track

import config
from ingest import ingest_url, startup_checks

console = Console()


def parse_url_file(url_file: Path) -> list[str]:
    """Parse URLs from file, skipping blank lines and # comments."""
    if not url_file.exists():
        raise FileNotFoundError(f"URL file not found: {url_file}")
    urls = []
    for line in url_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            urls.append(stripped)
    return urls


def write_failed_urls(failed: list[str], out_path: Path) -> None:
    """Write list of failed URLs to a file."""
    out_path.write_text("\n".join(failed) + "\n", encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description="Batch ingest URLs from a file.")
    parser.add_argument("url_file", help="Path to text file with one URL per line")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    startup_checks()

    url_file = Path(args.url_file)
    urls = parse_url_file(url_file)
    console.print(f"Found {len(urls)} URLs to process.")

    succeeded = 0
    failed = []

    for url in track(urls, description="Ingesting URLs..."):
        try:
            ingest_url(url, dry_run=args.dry_run)
            succeeded += 1
        except Exception as e:
            console.print(f"[red]Failed:[/red] {url} — {e}")
            failed.append(url)
        time.sleep(2)

    console.print(f"\n[green]Succeeded:[/green] {succeeded} / {len(urls)}")
    if failed:
        failed_path = Path("failed_urls.txt")
        write_failed_urls(failed, failed_path)
        console.print(f"[yellow]Failed URLs written to:[/yellow] {failed_path}")


if __name__ == "__main__":
    main()
