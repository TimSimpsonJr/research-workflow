"""
produce_output.py — Research to Production Format

Purpose: Transform any research or synthesis note into a specific downstream output format
via Ollama, or prepare a file for Claude Code processing.

Usage:
    python produce_output.py --file synthesis.md --format web_article
    python produce_output.py --file synthesis.md --format video_script --output-dir ./output
    python produce_output.py --file synthesis.md --format social_post --context "Twitter thread, 8 tweets"
    python produce_output.py --list-formats
    python produce_output.py --file synthesis.md --format web_article --model llama3.2

Dependencies: requests
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

SCRIPTS_DIR = Path(__file__).parent
PROMPTS_PATH = SCRIPTS_DIR / "prompts"
DATE_FORMAT = "%Y-%m-%d"


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

from text_utils import slugify as _slugify


# ──────────────────────────────────────────────
# Pure functions (no external dependencies)
# ──────────────────────────────────────────────

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


# ──────────────────────────────────────────────
# Ollama generation
# ──────────────────────────────────────────────

def generate_with_ollama(
    message: str,
    model: str,
    ollama_url: str = "http://localhost:11434",
) -> str | None:
    """Send a prompt to Ollama's /api/generate endpoint and return the response text.

    Returns:
        The response text on success, None on any failure.
    """
    try:
        response = requests.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model,
                "prompt": message,
                "stream": False,
            },
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("response", "")
    except Exception as exc:
        print(f"[produce_output] Ollama call failed: {exc}", file=sys.stderr)
        return None


# ──────────────────────────────────────────────
# File output (for Claude Code processing)
# ──────────────────────────────────────────────

def prepare_file_for_claude(
    message: str,
    output_dir: Path,
    source_slug: str,
    fmt: str,
) -> Path:
    """Write content + prompt to a file for Claude Code to process.

    Returns:
        The path to the prepared file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"{source_slug}-{fmt}-prompt.md"
    file_path.write_text(message, encoding="utf-8", newline="\n")
    return file_path


# ──────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Transform research notes into production-ready formats."
    )
    parser.add_argument("--file", help="Path to the research/synthesis note")
    parser.add_argument("--format", dest="fmt", help="Output format name")
    parser.add_argument("--context", help="Additional context appended to the prompt")
    parser.add_argument("--list-formats", action="store_true", help="List all available formats")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be sent without calling the model")
    parser.add_argument("--output-dir", help="Directory for output files (prints to stdout if omitted)")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama API base URL")
    parser.add_argument("--model", default="llama3.2", help="Ollama model name")
    args = parser.parse_args()

    formats_dir = PROMPTS_PATH / "output_formats"

    if args.list_formats:
        formats = list_formats(formats_dir)
        if not formats:
            print("No formats found in prompts/output_formats/")
        else:
            print("Available Output Formats:")
            for fmt in formats:
                print(f"  {fmt}")
        return

    if not args.file or not args.fmt:
        print("Error: --file and --format are required (or use --list-formats)", file=sys.stderr)
        sys.exit(1)

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    try:
        format_prompt = load_format_prompt(args.fmt, formats_dir)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        available = list_formats(formats_dir)
        print(f"Available formats: {', '.join(available)}", file=sys.stderr)
        sys.exit(1)

    if args.context:
        format_prompt += f"\n\nAdditional context for this output: {args.context}"

    content = file_path.read_text(encoding="utf-8", errors="ignore")
    vault_rules_path = PROMPTS_PATH / "vault_rules.txt"
    vault_rules = vault_rules_path.read_text(encoding="utf-8").strip() if vault_rules_path.exists() else ""
    message = f"{content}\n\n---\n{format_prompt}"
    if vault_rules:
        message += f"\n\n---\n{vault_rules}"

    if args.dry_run:
        print(f"Dry run -- {len(message)} chars, format: {args.fmt}")
        return

    # Try Ollama first, fall back to file output
    response_text = generate_with_ollama(message, args.model, args.ollama_url)

    if response_text is not None:
        # Ollama succeeded — write or print
        now = datetime.now(timezone.utc)
        date_str = now.strftime(DATE_FORMAT)
        source_slug = _slugify(file_path.stem)

        if args.output_dir:
            output_dir = Path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            out_path = build_output_path(output_dir, date_str, source_slug, args.fmt)
            out_path.write_text(response_text, encoding="utf-8", newline="\n")
            print(f"Output written: {out_path}")
        else:
            print(response_text)
    else:
        # Ollama unavailable or failed — fall back to file output
        source_slug = _slugify(file_path.stem)
        output_dir = Path(args.output_dir) if args.output_dir else Path(".")
        prepared_path = prepare_file_for_claude(message, output_dir, source_slug, args.fmt)
        print(f"File prepared at {prepared_path} -- process with Claude Code")


if __name__ == "__main__":
    main()
