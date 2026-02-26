"""
find_broken_links.py — Wiki-Link Checker

Purpose: Find [[wiki-links]] that don't resolve to existing files.

Usage: python find_broken_links.py

Dependencies: rich, python-dotenv
"""

import re
import sys
from pathlib import Path
from urllib.parse import unquote

from rich.console import Console
from rich.table import Table

import config
from utils import startup_checks

console = Console()


def extract_links(content: str) -> list[str]:
    """Extract all [[link]] and [[link|alias]] targets from content."""
    matches = re.findall(r"\[\[([^\]]+)\]\]", content)
    links = []
    for match in matches:
        target = match.split("|")[0]
        target = target.split("#")[0].strip()
        if target:
            links.append(target)
    return links


def normalize_link(link: str) -> str:
    """Normalize a link for comparison: strip heading, URL-decode, lowercase."""
    link = link.split("#")[0]
    link = unquote(link).strip().lower()
    return link


def build_note_index(vault_path: Path) -> set[str]:
    """Build a set of normalized note stems for fast lookup."""
    return {md.stem.lower() for md in vault_path.rglob("*.md")}


def find_broken_links(vault_path: Path) -> list[dict]:
    """Return list of {file, link} dicts for broken wiki-links."""
    index = build_note_index(vault_path)
    broken = []
    for md in sorted(vault_path.rglob("*.md")):
        content = md.read_text(encoding="utf-8", errors="ignore")
        for link in extract_links(content):
            if normalize_link(link) not in index:
                broken.append({"file": md, "link": link})
    return broken


def main():
    startup_checks()
    broken = find_broken_links(config.VAULT_PATH)

    if not broken:
        console.print("[green]No broken links found.[/green]")
        sys.exit(0)

    table = Table(title=f"Broken Wiki-Links ({len(broken)} found)")
    table.add_column("File", style="cyan")
    table.add_column("Broken Link", style="red")
    for item in broken:
        rel = item["file"].relative_to(config.VAULT_PATH)
        table.add_row(str(rel), item["link"])
    console.print(table)
    sys.exit(1)


if __name__ == "__main__":
    main()
