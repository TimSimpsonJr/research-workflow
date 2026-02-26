"""
produce_output.py — Research to Production Format

Purpose: Transform any research or synthesis note into a specific downstream output format.

Usage:
    python produce_output.py --file synthesis.md --format web_article
    python produce_output.py --file synthesis.md --format video_script
    python produce_output.py --file synthesis.md --format social_post --context "Twitter thread, 8 tweets"
    python produce_output.py --list-formats

Dependencies: anthropic, rich, python-dotenv
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

import config
from claude_pipe import call_claude, estimate_cost, load_vault_rules
from utils import slugify, startup_checks

console = Console()


def list_formats(formats_dir: Path) -> list[str]:
    """List all available format names by scanning the output_formats directory."""
    if not formats_dir.exists():
        return []
    return sorted(f.stem for f in formats_dir.glob("*.txt"))


def load_format_prompt(fmt: str, formats_dir: Path) -> str:
    """Load a format prompt by name."""
    path = formats_dir / f"{fmt}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Format prompt not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def build_output_path(output_dir: Path, date_str: str, source_slug: str, fmt: str) -> Path:
    """Build the output file path. Date prefix only for daily_digest format."""
    if fmt == "daily_digest":
        return output_dir / f"{date_str}-{source_slug}-{fmt}.md"
    return output_dir / f"{source_slug}-{fmt}.md"


def main():
    parser = argparse.ArgumentParser(description="Transform research notes into production-ready formats.")
    parser.add_argument("--file", help="Path to the research/synthesis note")
    parser.add_argument("--format", dest="fmt", help="Output format name")
    parser.add_argument("--context", help="Additional context appended to the prompt")
    parser.add_argument("--list-formats", action="store_true", help="List all available formats")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    formats_dir = config.PROMPTS_PATH / "output_formats"

    if args.list_formats:
        formats = list_formats(formats_dir)
        if not formats:
            console.print("[yellow]No formats found in prompts/output_formats/[/yellow]")
        else:
            table = Table(title="Available Output Formats")
            table.add_column("Format", style="cyan")
            for fmt in formats:
                table.add_row(fmt)
            console.print(table)
        return

    if not args.file or not args.fmt:
        console.print("[red]--file and --format are required (or use --list-formats)[/red]")
        sys.exit(1)

    startup_checks()

    file_path = Path(args.file)
    if not file_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        sys.exit(1)

    try:
        format_prompt = load_format_prompt(args.fmt, formats_dir)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        available = list_formats(formats_dir)
        console.print(f"Available formats: {', '.join(available)}")
        sys.exit(1)

    if args.context:
        format_prompt += f"\n\nAdditional context for this output: {args.context}"

    content = file_path.read_text(encoding="utf-8", errors="ignore")
    vault_rules = load_vault_rules(config.PROMPTS_PATH)
    message = f"{content}\n\n---\n{format_prompt}"
    if vault_rules:
        message += f"\n\n---\n{vault_rules}"

    if args.dry_run:
        console.print(f"[yellow]Dry run — {len(message)} chars, format: {args.fmt}[/yellow]")
        return

    with console.status(f"Generating {args.fmt} with Claude..."):
        response_text, usage = call_claude(message, model=config.CLAUDE_MODEL_HEAVY, max_tokens=config.CLAUDE_MAX_TOKENS)

    cost = estimate_cost(usage["input_tokens"], usage["output_tokens"], config.CLAUDE_MODEL_HEAVY)
    console.print(f"[dim]Tokens: {usage['input_tokens']} in / {usage['output_tokens']} out | Est. cost: ${cost:.4f}[/dim]")

    now = datetime.now(timezone.utc)
    date_str = now.strftime(config.DATE_FORMAT)
    source_slug = slugify(file_path.stem)

    output_dir = config.OUTPUT_PATH if config.OUTPUT_PATH and config.OUTPUT_PATH.exists() else None

    if output_dir:
        out_path = build_output_path(output_dir, date_str, source_slug, args.fmt)
        out_path.write_text(response_text, encoding="utf-8", newline="\n")
        console.print(f"[green]Output written:[/green] {out_path}")
    else:
        console.print(response_text)


if __name__ == "__main__":
    main()
