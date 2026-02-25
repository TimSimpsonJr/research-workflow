"""
find_related.py — Related Notes Finder

Purpose: Given a note, find related notes in the vault by keyword matching.

Usage:
    python find_related.py note.md
    python find_related.py note.md --append

Dependencies: anthropic, rich, python-dotenv
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

import config
from claude_pipe import call_claude, load_prompt_template

console = Console()


def parse_keywords(text: str) -> list[str]:
    """Parse Claude's keyword output: one term per line, no numbering."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def search_vault_python(
    vault_path: Path,
    keywords: list[str],
    source_path: Path | None,
    top_n: int = 10,
) -> list[dict]:
    """Score vault notes by number of matching keywords using Python re."""
    scores = {}
    keyword_patterns = [re.compile(re.escape(kw), re.IGNORECASE) for kw in keywords]

    for md in vault_path.rglob("*.md"):
        if source_path and md == source_path:
            continue
        content = md.read_text(encoding="utf-8", errors="ignore")
        score = sum(1 for pat in keyword_patterns if pat.search(content))
        if score > 0:
            scores[md] = score

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [{"file": f, "score": s} for f, s in ranked[:top_n]]


def search_vault_ripgrep(
    vault_path: Path,
    keywords: list[str],
    source_path: Path | None,
    top_n: int = 10,
) -> list[dict]:
    """Score vault notes using ripgrep for speed."""
    scores: dict[Path, int] = {}
    for kw in keywords:
        try:
            result = subprocess.run(
                ["rg", "-il", kw, str(vault_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            for line in result.stdout.splitlines():
                p = Path(line.strip())
                if source_path and p == source_path:
                    continue
                scores[p] = scores.get(p, 0) + 1
        except Exception:
            pass
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [{"file": f, "score": s} for f, s in ranked[:top_n]]


def startup_checks():
    if not config.VAULT_PATH.exists():
        console.print(f"[red]VAULT_PATH does not exist: {config.VAULT_PATH}[/red]")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Find related notes in the vault.")
    parser.add_argument("note", help="Path to the source note")
    parser.add_argument("--append", action="store_true", help="Append ## Related Notes section to source note")
    args = parser.parse_args()

    startup_checks()

    note_path = Path(args.note)
    if not note_path.exists():
        console.print(f"[red]Note not found: {note_path}[/red]")
        sys.exit(1)

    content = note_path.read_text(encoding="utf-8", errors="ignore")
    prompt = load_prompt_template("find_related", config.PROMPTS_PATH)

    console.print("Extracting keywords via Claude...")
    response_text, usage = call_claude(
        f"{content}\n\n---\n{prompt}",
        model=config.CLAUDE_MODEL_LIGHT,
        max_tokens=256,
    )
    keywords = parse_keywords(response_text)
    console.print(f"Keywords: {', '.join(keywords)}")

    # Use ripgrep if available, else Python
    if shutil.which("rg"):
        results = search_vault_ripgrep(config.VAULT_PATH, keywords, source_path=note_path)
    else:
        console.print("[dim]ripgrep not found, using Python search (slower)[/dim]")
        results = search_vault_python(config.VAULT_PATH, keywords, source_path=note_path)

    if not results:
        console.print("No related notes found.")
        return

    table = Table(title="Related Notes")
    table.add_column("Note", style="cyan")
    table.add_column("Matches", style="green")
    for r in results:
        try:
            rel = r["file"].relative_to(config.VAULT_PATH)
        except ValueError:
            rel = r["file"]
        table.add_row(str(rel), str(r["score"]))
    console.print(table)

    if args.append:
        links = "\n".join(f"- [[{r['file'].stem}]]" for r in results)
        section = f"\n\n## Related Notes\n\n{links}\n"
        with note_path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(section)
        console.print(f"[green]Related Notes section appended to:[/green] {note_path}")


if __name__ == "__main__":
    main()
