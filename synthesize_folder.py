"""
synthesize_folder.py — Folder Synthesis to MOC

Purpose: Package all notes in a folder into context, synthesize via Claude, write a new MOC note.

Usage:
    python synthesize_folder.py --folder "path\\to\\folder" --output "Topic-Synthesis.md"
    python synthesize_folder.py --folder "path\\to\\folder" --output "Topic-Synthesis.md" --recursive
    python synthesize_folder.py --folder "path\\to\\folder" --output "Topic-Synthesis.md" --no-repomix

Dependencies: anthropic, rich, python-dotenv. Optional: repomix (npm install -g repomix)
"""

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm

import config
from claude_pipe import call_claude, estimate_cost, load_prompt_template

console = Console()

MAX_CHARS = 150_000
TOKEN_CONFIRM_THRESHOLD = 100_000


REPOMIX_FALLBACK_PATHS = [
    p for p in [os.environ.get("REPOMIX_PATH")] if p
] or []
NODE_FALLBACK_PATH = os.environ.get("NODE_PATH", "")


def find_repomix() -> tuple[str, ...] | None:
    """Return command tuple to invoke repomix, or None if not found."""
    if shutil.which("repomix"):
        return ("repomix",)
    for path in REPOMIX_FALLBACK_PATHS:
        if Path(path).exists() and shutil.which("node"):
            return ("node", path)
        if Path(path).exists() and Path(NODE_FALLBACK_PATH).exists():
            return (NODE_FALLBACK_PATH, path)
    return None


def check_repomix() -> bool:
    """Return True if repomix is available."""
    return find_repomix() is not None


def collect_markdown_files(folder: Path, recursive: bool = False) -> list[Path]:
    """Collect .md files from folder, optionally recursive."""
    if recursive:
        return sorted(folder.rglob("*.md"))
    return sorted(folder.glob("*.md"))


def concatenate_files(files: list[Path]) -> str:
    """Concatenate files with separators."""
    parts = []
    for f in files:
        content = f.read_text(encoding="utf-8", errors="ignore")
        parts.append(f"\n\n---\n# Source: {f.name}\n\n{content}")
    return "".join(parts)


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token."""
    return len(text) // 4


def run_repomix(folder: Path, config_path: Path, output_path: Path) -> str:
    """Run repomix and return its output as a string."""
    cmd = find_repomix()
    if cmd is None:
        raise FileNotFoundError("repomix not found")
    subprocess.run(
        [*cmd, "--config", str(config_path), "--output-file", str(output_path), str(folder)],
        check=True,
        capture_output=True,
    )
    content = output_path.read_text(encoding="utf-8", errors="ignore")
    output_path.unlink(missing_ok=True)
    return content


def build_output_frontmatter(
    source_folder: str,
    file_count: int,
    used_repomix: bool,
) -> str:
    now = datetime.now(timezone.utc).isoformat()
    return (
        f"---\n"
        f"source_folder: {source_folder}\n"
        f"file_count: {file_count}\n"
        f"generated_at: {now}\n"
        f"repomix_used: {used_repomix}\n"
        f"---\n\n"
    )


def startup_checks():
    if not config.VAULT_PATH.exists():
        console.print(f"[red]VAULT_PATH does not exist: {config.VAULT_PATH}[/red]")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Synthesize a folder of notes into a MOC via Claude.")
    parser.add_argument("--folder", required=True, help="Path to folder of notes to synthesize")
    parser.add_argument("--output", required=True, help="Output filename (placed in MOCS_PATH or vault root)")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--no-repomix", action="store_true", help="Skip repomix, use Python fallback")
    parser.add_argument("--confirm", action="store_true", help="Auto-confirm large token counts")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    startup_checks()

    folder = Path(args.folder)
    if not folder.exists():
        console.print(f"[red]Folder not found: {folder}[/red]")
        sys.exit(1)

    use_repomix = not args.no_repomix and check_repomix()
    used_repomix = False

    if use_repomix:
        console.print("Using repomix to package notes...")
        repomix_config = Path(__file__).parent / "repomix.config.json"
        repomix_output = Path(__file__).parent / "repomix-output.txt"
        try:
            context = run_repomix(folder, repomix_config, repomix_output)
            used_repomix = True
        except subprocess.CalledProcessError as e:
            console.print(f"[yellow]Repomix failed, falling back to Python: {e}[/yellow]")
            use_repomix = False

    if not use_repomix:
        files = collect_markdown_files(folder, recursive=args.recursive)
        if not files:
            console.print("[red]No markdown files found.[/red]")
            sys.exit(1)
        context = concatenate_files(files)
        file_count = len(files)
    else:
        files = collect_markdown_files(folder, recursive=args.recursive)
        file_count = len(files)

    # Truncate if too long
    if len(context) > MAX_CHARS:
        console.print(f"[yellow]Context exceeds {MAX_CHARS} chars, truncating.[/yellow]")
        context = context[:MAX_CHARS]

    token_estimate = estimate_tokens(context)
    console.print(f"Estimated tokens: {token_estimate:,}")

    if token_estimate > TOKEN_CONFIRM_THRESHOLD and not args.confirm:
        if not Confirm.ask(f"Context is large ({token_estimate:,} tokens). Proceed?"):
            sys.exit(0)

    prompt = load_prompt_template("synthesize_topic", config.PROMPTS_PATH)
    message = f"{context}\n\n---\n{prompt}"

    if args.dry_run:
        console.print(f"[yellow]Dry run — {len(message)} chars, would send to Claude[/yellow]")
        return

    with console.status("Synthesizing with Claude..."):
        response_text, usage = call_claude(message, model=config.CLAUDE_MODEL_HEAVY, max_tokens=config.CLAUDE_MAX_TOKENS)

    cost = estimate_cost(usage["input_tokens"], usage["output_tokens"], config.CLAUDE_MODEL_HEAVY)
    console.print(f"[dim]Tokens: {usage['input_tokens']} in / {usage['output_tokens']} out | Est. cost: ${cost:.4f}[/dim]")

    frontmatter = build_output_frontmatter(str(folder), file_count, used_repomix)
    full_output = frontmatter + response_text

    out_dir = config.MOCS_PATH if config.MOCS_PATH and config.MOCS_PATH.exists() else config.VAULT_PATH
    out_path = (out_dir / args.output).resolve()
    if not str(out_path).startswith(str(out_dir.resolve())):
        console.print(f"[red]Output path escapes target directory: {args.output}[/red]")
        sys.exit(1)
    out_path.write_text(full_output, encoding="utf-8", newline="\n")
    console.print(f"[green]MOC written:[/green] {out_path}")


if __name__ == "__main__":
    main()
