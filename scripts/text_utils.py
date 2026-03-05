"""
text_utils.py — Minimal shared text helpers.

Zero-dependency module (no config, no rich, no requests) that any script
can import safely.
"""

import re


def slugify(text: str, max_length: int = 60) -> str:
    """Convert text to a URL-safe slug."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s]+", "-", text.strip())
    text = re.sub(r"-+", "-", text)
    text = text[:max_length].strip("-")
    return text
