# tests/test_vault_lint.py
"""Tests for vault_lint.py"""

import pytest
from pathlib import Path


def test_parse_frontmatter_valid(tmp_path):
    """parse_frontmatter returns dict for valid YAML frontmatter."""
    from vault_lint import parse_frontmatter
    note = tmp_path / "note.md"
    note.write_text("---\ntitle: Test\nsource: http://example.com\n---\n\n# Content", encoding="utf-8")
    result = parse_frontmatter(note)
    assert result["title"] == "Test"
    assert result["source"] == "http://example.com"


def test_parse_frontmatter_missing(tmp_path):
    """parse_frontmatter returns empty dict for notes without frontmatter."""
    from vault_lint import parse_frontmatter
    note = tmp_path / "note.md"
    note.write_text("# Just a heading\n\nNo frontmatter.", encoding="utf-8")
    result = parse_frontmatter(note)
    assert result == {}


def test_find_missing_fields():
    """find_missing_fields returns list of required fields not in frontmatter."""
    from vault_lint import find_missing_fields
    fm = {"title": "Test", "source": "http://x.com"}
    required = ["title", "source", "tags", "created"]
    missing = find_missing_fields(fm, required)
    assert "tags" in missing
    assert "created" in missing
    assert "title" not in missing


def test_lint_vault_finds_issues(tmp_path):
    """lint_vault returns issues for notes missing required fields."""
    from vault_lint import lint_vault
    note = tmp_path / "note.md"
    note.write_text("---\ntitle: Test\n---\n# Content", encoding="utf-8")
    issues = lint_vault(tmp_path, required_fields=["title", "source", "tags"])
    assert len(issues) == 1
    assert issues[0]["file"] == note
    assert "source" in issues[0]["missing"]


def test_lint_vault_no_issues(tmp_path):
    """lint_vault returns no issues for complete notes."""
    from vault_lint import lint_vault
    note = tmp_path / "note.md"
    note.write_text(
        "---\ntitle: T\nsource: http://x.com\ntags: [a]\n---\n# Content",
        encoding="utf-8",
    )
    issues = lint_vault(tmp_path, required_fields=["title", "source", "tags"])
    assert issues == []


def test_vault_lint_rejects_sibling_folder(tmp_path, capsys):
    """A sibling path that shares a string prefix with the vault root must be rejected."""
    import sys
    import subprocess
    vault = tmp_path / "vault"
    sibling = tmp_path / "vault2"
    vault.mkdir()
    sibling.mkdir()
    (vault / ".researcher").mkdir()
    (vault / ".researcher" / "config.json").write_text(
        '{"vault_root": "' + str(vault).replace("\\", "/") + '", '
        '"frontmatter_fields": ["title"], "assets": "assets"}'
    )

    repo_root = Path(__file__).parent.parent
    script = repo_root / "scripts" / "vault_lint.py"
    result = subprocess.run(
        [sys.executable, str(script), "--vault", str(vault), "--folder", "../vault2"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "escapes vault" in (result.stdout + result.stderr).lower()
