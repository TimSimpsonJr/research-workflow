"""
vault_lint.py — Frontmatter Validator

Purpose: Find notes missing required frontmatter fields.

Usage:
    python vault_lint.py
    python vault_lint.py --folder Campaigns
    python vault_lint.py --fix

Dependencies: PyYAML, rich, python-dotenv
"""

import argparse
import sys
from pathlib import Path

import yaml
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

import config

console = Console()


def parse_frontmatter(note_path: Path) -> dict:
    """Parse YAML frontmatter from a markdown note. Returns empty dict if none."""
    text = note_path.read_text(encoding="utf-8", errors="ignore")
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    try:
        return yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        return {}


def find_missing_fields(frontmatter: dict, required: list[str]) -> list[str]:
    """Return list of required fields missing or empty in frontmatter."""
    return [f for f in required if not frontmatter.get(f)]


def lint_vault(vault_path: Path, required_fields: list[str]) -> list[dict]:
    """Walk vault, return list of {file, missing} dicts for notes with issues."""
    issues = []
    for md in sorted(vault_path.rglob("*.md")):
        fm = parse_frontmatter(md)
        missing = find_missing_fields(fm, required_fields)
        if missing:
            issues.append({"file": md, "missing": missing, "frontmatter": fm})
    return issues


def fix_issue(note_path: Path, missing_fields: list[str]) -> None:
    """Interactively prompt for missing field values and write them back."""
    text = note_path.read_text(encoding="utf-8", errors="ignore")
    if text.startswith("---"):
        end = text.find("---", 3)
        fm_text = text[3:end]
        rest = text[end + 3:]
    else:
        fm_text = ""
        rest = text

    additions = []
    for field in missing_fields:
        value = Prompt.ask(f"  Value for '{field}' in {note_path.name}")
        additions.append(f"{field}: {value}")

    new_fm = fm_text.rstrip() + "\n" + "\n".join(additions) + "\n"
    note_path.write_text(f"---{new_fm}---{rest}", encoding="utf-8", newline="\n")


def startup_checks():
    if not config.VAULT_PATH.exists():
        console.print(f"[red]VAULT_PATH does not exist: {config.VAULT_PATH}[/red]")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Find notes missing required frontmatter.")
    parser.add_argument("--folder", help="Subfolder within vault to lint (default: whole vault)")
    parser.add_argument("--fix", action="store_true", help="Interactively fix missing fields")
    args = parser.parse_args()

    startup_checks()

    target = (config.VAULT_PATH / args.folder).resolve() if args.folder else config.VAULT_PATH
    vault_resolved = config.VAULT_PATH.resolve()
    if not str(target).startswith(str(vault_resolved)):
        console.print(f"[red]Folder escapes vault path: {args.folder}[/red]")
        sys.exit(1)
    if not target.exists():
        console.print(f"[red]Folder not found: {target}[/red]")
        sys.exit(1)

    issues = lint_vault(target, config.FRONTMATTER_FIELDS)

    if not issues:
        console.print("[green]No issues found.[/green]")
        sys.exit(0)

    table = Table(title=f"Frontmatter Issues ({len(issues)} notes)")
    table.add_column("File", style="cyan")
    table.add_column("Missing Fields", style="red")
    for issue in issues:
        rel = issue["file"].relative_to(config.VAULT_PATH)
        table.add_row(str(rel), ", ".join(issue["missing"]))
    console.print(table)

    if args.fix:
        for issue in issues:
            console.print(f"\n[bold]{issue['file'].name}[/bold]")
            fix_issue(issue["file"], issue["missing"])
        console.print("[green]Done fixing issues.[/green]")

    sys.exit(1)


if __name__ == "__main__":
    main()
