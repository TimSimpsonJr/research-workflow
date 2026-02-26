"""
claude_pipe.py — Generic Claude API Pipe

Purpose: Core building block. Send any file to Claude with a named prompt template.

Usage:
    python claude_pipe.py --file note.md --prompt summarize
    python claude_pipe.py --file note.md --prompt summarize --output result.md
    python claude_pipe.py --file note.md --prompt summarize --model light

Dependencies: anthropic, rich, python-dotenv
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from rich.console import Console

import config
from utils import startup_checks

console = Console()

# Approximate cost per million tokens (USD)
COST_PER_M_INPUT = {
    "claude-opus-4-6": 15.0,
    "claude-sonnet-4-6": 3.0,
    "claude-haiku-4-5-20251001": 0.25,
}
COST_PER_M_OUTPUT = {
    "claude-opus-4-6": 75.0,
    "claude-sonnet-4-6": 15.0,
    "claude-haiku-4-5-20251001": 1.25,
}


def load_prompt_template(name: str, prompts_path: Path) -> str:
    """Load a prompt template by name from the prompts directory."""
    path = prompts_path / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def build_message(file_content: str, prompt_template: str) -> str:
    """Combine file content and prompt template into a single message."""
    return f"{file_content}\n\n---\n{prompt_template}"


def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Estimate USD cost for a Claude API call."""
    if model not in COST_PER_M_INPUT:
        console.print(f"[yellow]Warning: unknown model '{model}', using Opus pricing for cost estimate[/yellow]")
    in_rate = COST_PER_M_INPUT.get(model, 15.0)
    out_rate = COST_PER_M_OUTPUT.get(model, 75.0)
    return (input_tokens / 1_000_000 * in_rate) + (output_tokens / 1_000_000 * out_rate)


def call_claude(message: str, model: str, max_tokens: int) -> tuple[str, dict]:
    """Send message to Claude API, return (response_text, usage_dict)."""
    # Let the SDK read ANTHROPIC_API_KEY from the environment rather than
    # passing it explicitly, keeping the key out of constructor arguments.
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": message}],
    )
    text = response.content[0].text
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    return text, usage


def write_output(
    response_text: str,
    output_path: Path,
    source_note: str = "",
    prompt_used: str = "",
) -> None:
    """Write Claude response as a markdown file with frontmatter."""
    now = datetime.now(timezone.utc).isoformat()
    # Quote string values to handle paths with colons, backslashes, etc.
    frontmatter = (
        f"---\n"
        f'source_note: "{source_note}"\n'
        f"generated_at: {now}\n"
        f'prompt_used: "{prompt_used}"\n'
        f"---\n\n"
    )
    output_path.write_text(frontmatter + response_text, encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description="Pipe a file through Claude with a named prompt template.")
    parser.add_argument("--file", required=True, help="Path to the input file")
    parser.add_argument("--prompt", required=True, help="Prompt template name (without .txt)")
    parser.add_argument("--output", help="Output file path (prints to stdout if not set)")
    parser.add_argument("--model", choices=["light", "heavy"], default="heavy",
                        help="'light' = Haiku, 'heavy' = Opus (default)")
    parser.add_argument("--dry-run", action="store_true", help="Print message without calling API")
    args = parser.parse_args()

    startup_checks(require_api_key=True)

    model = config.CLAUDE_MODEL_LIGHT if args.model == "light" else config.CLAUDE_MODEL_HEAVY
    file_path = Path(args.file)
    if not file_path.exists():
        console.print(f"[red]File not found:[/red] {file_path}")
        sys.exit(1)

    file_content = file_path.read_text(encoding="utf-8", errors="ignore")
    prompt_template = load_prompt_template(args.prompt, config.PROMPTS_PATH)
    message = build_message(file_content, prompt_template)

    if args.dry_run:
        console.print(f"[yellow]Dry run — message length: {len(message)} chars[/yellow]")
        console.print(message[:500] + "..." if len(message) > 500 else message)
        return

    with console.status(f"Calling Claude ({model})..."):
        response_text, usage = call_claude(message, model=model, max_tokens=config.CLAUDE_MAX_TOKENS)

    cost = estimate_cost(usage["input_tokens"], usage["output_tokens"], model)
    console.print(
        f"[dim]Tokens: {usage['input_tokens']} in / {usage['output_tokens']} out | "
        f"Est. cost: ${cost:.4f}[/dim]"
    )

    if args.output:
        out_path = Path(args.output).resolve()
        vault_resolved = config.VAULT_PATH.resolve()
        if not str(out_path).startswith(str(vault_resolved)):
            console.print(f"[yellow]Warning: output path is outside the vault: {out_path}[/yellow]")
        write_output(response_text, out_path, source_note=str(file_path), prompt_used=args.prompt)
        console.print(f"[green]Output written:[/green] {out_path}")
    else:
        console.print(response_text)


if __name__ == "__main__":
    main()
