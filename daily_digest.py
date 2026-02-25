"""
daily_digest.py — Daily Vault Summary

Purpose: Summarize today's new/modified notes, append to daily note.

Usage:
    python daily_digest.py
    python daily_digest.py --setup-scheduler

Dependencies: anthropic, rich, python-dotenv
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

import config
from claude_pipe import call_claude, estimate_cost

console = Console()

SCHEDULER_INSTRUCTIONS = """
To run daily_digest.py automatically each morning:
1. Open Task Scheduler (search "Task Scheduler" in Start menu)
2. Action → Create Basic Task → name it "Vault Daily Digest"
3. Trigger: Daily, at your preferred time
4. Action: Start a Program
   Program/script: python
   Arguments:      {scripts_path}\\daily_digest.py
   Start in:       {scripts_path}
5. Finish
"""


def find_recent_notes(vault_path: Path, hours: int, exclude_paths: set) -> list[Path]:
    """Find .md files modified in the last `hours` hours."""
    cutoff = time.time() - (hours * 3600)
    return [
        md for md in vault_path.rglob("*.md")
        if md.stat().st_mtime > cutoff and md not in exclude_paths
    ]


def extract_note_preview(content: str, max_chars: int = 500) -> str:
    """Extract first max_chars characters, skipping frontmatter."""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:].lstrip()
    preview = content[:max_chars]
    if len(content) > max_chars:
        preview += "..."
    return preview.strip()


def format_digest_entry(filename: str, preview: str) -> str:
    """Format a single note entry for the digest."""
    return f"**{filename}**\n{preview}\n"


def build_daily_note_template(date_str: str) -> str:
    """Build a minimal daily note when one doesn't exist."""
    return f"---\ndate: {date_str}\ntags: [daily]\n---\n\n# {date_str}\n\n"


def append_digest_section(daily_note_path: Path, digest_content: str) -> None:
    """Append digest content to the daily note."""
    existing = daily_note_path.read_text(encoding="utf-8", errors="ignore")
    updated = existing.rstrip() + "\n\n" + digest_content + "\n"
    daily_note_path.write_text(updated, encoding="utf-8", newline="\n")


def startup_checks():
    if not config.VAULT_PATH.exists():
        console.print(f"[red]VAULT_PATH does not exist: {config.VAULT_PATH}[/red]")
        sys.exit(1)
    if not config.ANTHROPIC_API_KEY:
        console.print("[red]ANTHROPIC_API_KEY not set in .env[/red]")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Summarize today's vault activity to daily note.")
    parser.add_argument("--setup-scheduler", action="store_true", help="Print Windows Task Scheduler setup instructions")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.setup_scheduler:
        scripts_path = Path(__file__).parent
        console.print(SCHEDULER_INSTRUCTIONS.format(scripts_path=scripts_path))
        return

    startup_checks()

    now = datetime.now(timezone.utc)
    date_str = now.strftime(config.DATE_FORMAT)

    # Determine daily note path
    daily_dir = config.DAILY_PATH if config.DAILY_PATH and config.DAILY_PATH.exists() else config.VAULT_PATH
    daily_note_path = daily_dir / f"{date_str}.md"

    # Collect excluded paths
    exclude_paths = set()
    if config.DAILY_PATH:
        exclude_paths.update(config.DAILY_PATH.rglob("*.md"))
    if daily_note_path.exists():
        exclude_paths.add(daily_note_path)

    recent_notes = find_recent_notes(config.VAULT_PATH, hours=24, exclude_paths=exclude_paths)
    if not recent_notes:
        console.print("[yellow]No notes modified in the last 24 hours.[/yellow]")
        return

    console.print(f"Found {len(recent_notes)} recently modified notes.")

    # Build digest entries
    entries = []
    for note in sorted(recent_notes, key=lambda p: p.stat().st_mtime, reverse=True):
        content = note.read_text(encoding="utf-8", errors="ignore")
        preview = extract_note_preview(content)
        entries.append(format_digest_entry(note.name, preview))

    combined = "\n".join(entries)
    summarize_prompt = (
        "The following are recent research notes from today. "
        "Write a brief digest (3-5 sentences) summarizing the key themes and new information added today. "
        "Be concise and factual."
    )
    message = f"{combined}\n\n---\n{summarize_prompt}"

    if args.dry_run:
        console.print(f"[yellow]Dry run — {len(recent_notes)} notes, would append to {daily_note_path}[/yellow]")
        return

    with console.status("Generating digest with Claude..."):
        response_text, usage = call_claude(message, model=config.CLAUDE_MODEL_LIGHT, max_tokens=512)

    cost = estimate_cost(usage["input_tokens"], usage["output_tokens"], config.CLAUDE_MODEL_LIGHT)
    console.print(f"[dim]Tokens: {usage['input_tokens']} in / {usage['output_tokens']} out | Est. cost: ${cost:.4f}[/dim]")

    digest_content = f"## Research Digest\n\n{response_text}\n\n### Notes Updated\n\n"
    digest_content += "\n".join(f"- [[{n.stem}]]" for n in recent_notes)

    # Create daily note if missing
    if not daily_note_path.exists():
        daily_note_path.write_text(build_daily_note_template(date_str), encoding="utf-8", newline="\n")
        console.print(f"[green]Created daily note:[/green] {daily_note_path}")

    append_digest_section(daily_note_path, digest_content)
    console.print(f"[green]Digest appended to:[/green] {daily_note_path}")


if __name__ == "__main__":
    main()
