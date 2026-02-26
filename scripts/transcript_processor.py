"""
transcript_processor.py — Transcript to Research Notes

Purpose: Process a Whisper transcript into structured research notes.

Usage:
    python transcript_processor.py transcript.txt
    python transcript_processor.py transcript.vtt --output-dir "path\\to\\Interviews"

Dependencies: anthropic, rich, python-dotenv
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

import config
from claude_pipe import call_claude, estimate_cost, load_prompt_template
from utils import slugify, startup_checks

console = Console()


def strip_vtt(content: str) -> str:
    """Strip WebVTT timestamps and metadata, returning plain dialogue text."""
    if not content.startswith("WEBVTT"):
        return content
    lines = content.splitlines()
    dialogue_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line == "WEBVTT":
            continue
        # Skip timestamp lines (00:00:00.000 --> 00:00:00.000)
        if re.match(r"\d{2}:\d{2}:\d{2}[\.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[\.,]\d{3}", line):
            continue
        # Skip cue identifier lines (pure numbers)
        if re.match(r"^\d+$", line):
            continue
        dialogue_lines.append(line)
    return "\n".join(dialogue_lines)


def detect_format(content: str) -> str:
    """Detect whether content is VTT or plain text."""
    if content.strip().startswith("WEBVTT"):
        return "vtt"
    return "txt"


def build_output_paths(output_dir: Path, date_str: str, slug: str) -> tuple[Path, Path]:
    """Return (notes_path, quotes_path) for transcript output."""
    notes = output_dir / f"{date_str}-{slug}-notes.md"
    quotes = output_dir / f"{date_str}-{slug}-quotes.md"
    return notes, quotes


def main():
    parser = argparse.ArgumentParser(description="Process a Whisper transcript into structured research notes.")
    parser.add_argument("transcript", help="Path to transcript file (.txt or .vtt)")
    parser.add_argument("--output-dir", help="Directory to write output notes (default: INBOX_PATH)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    startup_checks()

    transcript_path = Path(args.transcript)
    if not transcript_path.exists():
        console.print(f"[red]Transcript not found: {transcript_path}[/red]")
        sys.exit(1)

    output_dir = Path(args.output_dir).resolve() if args.output_dir else config.INBOX_PATH
    vault_resolved = config.VAULT_PATH.resolve()
    if not str(output_dir).startswith(str(vault_resolved)):
        console.print(f"[yellow]Warning: output dir is outside the vault: {output_dir}[/yellow]")
    if not output_dir.exists():
        console.print(f"[yellow]Output dir not found, creating: {output_dir}[/yellow]")
        output_dir.mkdir(parents=True)

    raw_content = transcript_path.read_text(encoding="utf-8", errors="ignore")
    fmt = detect_format(raw_content)
    clean_content = strip_vtt(raw_content) if fmt == "vtt" else raw_content

    prompt = load_prompt_template("extract_transcript", config.PROMPTS_PATH)
    message = f"{clean_content}\n\n---\n{prompt}"

    now = datetime.now(timezone.utc)
    date_str = now.strftime(config.DATE_FORMAT)
    slug = slugify(transcript_path.stem)
    notes_path, quotes_path = build_output_paths(output_dir, date_str, slug)

    if args.dry_run:
        console.print(f"[yellow]Dry run — would write to: {notes_path} and {quotes_path}[/yellow]")
        return

    with console.status("Processing transcript with Claude..."):
        response_text, usage = call_claude(message, model=config.CLAUDE_MODEL_HEAVY, max_tokens=config.CLAUDE_MAX_TOKENS)

    cost = estimate_cost(usage["input_tokens"], usage["output_tokens"], config.CLAUDE_MODEL_HEAVY)
    console.print(f"[dim]Tokens: {usage['input_tokens']} in / {usage['output_tokens']} out | Est. cost: ${cost:.4f}[/dim]")

    # Extract quotes section for the quotes file
    quotes_match = re.search(r"## Notable Quotes\n(.*?)(?=\n## |\Z)", response_text, re.DOTALL)
    quotes_content = quotes_match.group(0) if quotes_match else "## Notable Quotes\n\nNone extracted."

    notes_fm = f"---\nsource: {transcript_path.name}\ngenerated_at: {now.isoformat()}\n---\n\n"
    quotes_fm = f"---\nsource: {transcript_path.name}\ngenerated_at: {now.isoformat()}\n---\n\n"

    notes_path.write_text(notes_fm + response_text, encoding="utf-8", newline="\n")
    quotes_path.write_text(quotes_fm + quotes_content, encoding="utf-8", newline="\n")

    console.print(f"[green]Notes:[/green] {notes_path}")
    console.print(f"[green]Quotes:[/green] {quotes_path}")


if __name__ == "__main__":
    main()
