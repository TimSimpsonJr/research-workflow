"""
summarize.py — Article Summarization via Ollama or File Output

Purpose: Distills fetched articles to ~500 tokens via Ollama, or produces
file-based output for Claude Code to summarize via Haiku subagents.

Usage:
    # Ollama mode (requires running Ollama instance):
    python summarize.py --input fetch_results.json --model qwen2.5:14b

    # Claude Code file output mode (no Ollama needed):
    python summarize.py --input fetch_results.json --prepare-for-claude --output-dir ./summaries

Dependencies: requests
"""

import argparse
import json
import re
import sys
from pathlib import Path

import requests

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

SCRIPTS_DIR = Path(__file__).parent
PROMPT_PATH = SCRIPTS_DIR / "prompts" / "summarize_fetch.txt"
MAX_CONTENT_CHARS = 3000


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _load_prompt() -> str:
    """Load the summarize_fetch prompt template."""
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


from text_utils import slugify as _slugify


# ──────────────────────────────────────────────
# Ollama summarization
# ──────────────────────────────────────────────

def summarize_article(
    content: str,
    title: str,
    url: str,
    model: str,
    ollama_url: str = "http://localhost:11434",
) -> dict | None:
    """Summarize a single article via Ollama's /api/generate endpoint.

    Sends article content + prompt to Ollama and parses the JSON response.

    Returns:
        Dict with keys: summary, source_type, key_entities, key_claims.
        None on any failure (network, parse, etc.).
    """
    prompt_template = _load_prompt()
    full_prompt = f"Title: {title}\nURL: {url}\n\n{content}\n\n---\n{prompt_template}"

    try:
        response = requests.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model,
                "prompt": full_prompt,
                "stream": False,
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        result = json.loads(data["response"])
        return result
    except Exception as exc:
        print(f"[summarize] Failed to summarize '{title}': {exc}", file=sys.stderr)
        return None


def summarize_batch(
    fetch_results: dict,
    model: str,
    ollama_url: str = "http://localhost:11434",
) -> list[dict]:
    """Summarize all fetched articles via Ollama.

    Iterates over fetch_results["fetched"], calls summarize_article for each,
    and returns a list of summary dicts with url, title, and summary fields merged.
    Failures (None returns) are filtered out.
    """
    summaries: list[dict] = []

    for item in fetch_results.get("fetched", []):
        result = summarize_article(
            content=item["content"],
            title=item["title"],
            url=item["url"],
            model=model,
            ollama_url=ollama_url,
        )
        if result is not None:
            summaries.append({
                "url": item["url"],
                "title": item["title"],
                **result,
            })

    return summaries


# ──────────────────────────────────────────────
# Claude Code file output (no Ollama)
# ──────────────────────────────────────────────

def prepare_for_claude_code(
    fetch_results: dict,
    output_dir: Path,
) -> list[dict]:
    """Write each article to a separate file for Haiku subagent summarization.

    For when Ollama is NOT available. Each file contains title, url, and
    truncated content (first 3000 chars). Files are named {index}-{slug}.md.

    Returns:
        List of {"url", "title", "file"} entries where "file" is the
        filename (relative to output_dir).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []

    for index, item in enumerate(fetch_results.get("fetched", [])):
        slug = _slugify(item.get("title", "untitled"))
        filename = f"{index}-{slug}.md"

        truncated_content = item["content"][:MAX_CONTENT_CHARS]

        file_content = (
            f"# {item['title']}\n\n"
            f"Source: {item['url']}\n\n"
            f"---\n\n"
            f"{truncated_content}\n"
        )

        (output_dir / filename).write_text(file_content, encoding="utf-8")

        entries.append({
            "url": item["url"],
            "title": item["title"],
            "file": filename,
        })

    return entries


# ──────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize fetched articles via Ollama or prepare files for Claude Code."
    )
    parser.add_argument("--input", required=True, help="Path to fetch_results.json")
    parser.add_argument("--model", default="qwen2.5:14b", help="Ollama model name")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama API base URL")
    parser.add_argument("--output", help="Output path for summaries JSON (stdout if omitted)")
    parser.add_argument("--prepare-for-claude", action="store_true",
                        help="Write files for Claude Code instead of calling Ollama")
    parser.add_argument("--output-dir", default="./summaries",
                        help="Directory for Claude Code file output (used with --prepare-for-claude)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[summarize] ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    fetch_results: dict = json.loads(input_path.read_text(encoding="utf-8"))

    if args.prepare_for_claude:
        output_dir = Path(args.output_dir)
        entries = prepare_for_claude_code(fetch_results, output_dir)
        result = {"mode": "claude_code", "files": entries}
        print(f"[summarize] Wrote {len(entries)} file(s) to {output_dir}", file=sys.stderr)
    else:
        summaries = summarize_batch(fetch_results, args.model, args.ollama_url)
        result = {
            "mode": "ollama",
            "model": args.model,
            "summaries": summaries,
            "stats": {
                "total": len(fetch_results.get("fetched", [])),
                "summarized": len(summaries),
                "failed": len(fetch_results.get("fetched", [])) - len(summaries),
            },
        }

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output_json, encoding="utf-8")
        print(f"[summarize] Results written to {output_path}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
