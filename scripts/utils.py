"""
utils.py — Shared Utilities

Common functions used across multiple scripts: startup validation,
text slugification, and other helpers.
"""

import re
import sys
from pathlib import Path

from rich.console import Console

import config

console = Console()


def startup_checks(require_api_key: bool = False, ensure_inbox: bool = False):
    """Verify required config before running.

    Args:
        require_api_key: Also check that ANTHROPIC_API_KEY is set.
        ensure_inbox: Create INBOX_PATH if it doesn't exist.
    """
    errors = []
    if require_api_key:
        try:
            import anthropic as _anthropic  # noqa: F401
        except ImportError:
            errors.append("anthropic package not installed — run: pip install anthropic")
        if not config.ANTHROPIC_API_KEY:
            errors.append("ANTHROPIC_API_KEY is not set in .env")
    if not config.VAULT_PATH.exists():
        errors.append(f"VAULT_PATH does not exist: {config.VAULT_PATH}")
    if errors:
        for e in errors:
            console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
    if ensure_inbox:
        inbox = config.INBOX_PATH
        if not inbox.exists():
            console.print(f"[yellow]Inbox not found, creating: {inbox}[/yellow]")
            inbox.mkdir(parents=True)


def slugify(text: str, max_length: int = 60) -> str:
    """Convert text to a URL-safe slug."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s]+", "-", text.strip())
    text = re.sub(r"-+", "-", text)
    text = text[:max_length].strip("-")
    return text
