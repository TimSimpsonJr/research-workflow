# Research Workflow Automation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a modular Python toolkit that automates an Obsidian research workflow — ingesting URLs, processing transcripts, synthesizing notes, and producing formatted outputs via the Claude API.

**Architecture:** A flat collection of single-purpose Python scripts that share configuration via `config.py`/`.env`. Each script is independently runnable and composable. No shared mutable state between scripts; all coordination happens via the filesystem (vault notes). `discover_vault.py` runs once to generate `config.py` and `.env`, and all other scripts import from `config.py`.

**Tech Stack:** Python 3.10+, `anthropic` SDK, `python-dotenv`, `requests`, `PyYAML`, `rich`, `pytest`, `pytest-mock`. Optional: `repomix` (Node.js, `npm install -g repomix`).

**Key Paths:**
- Scripts dir: `C:\Users\tim\OneDrive\Documents\Projects\`
- Vault: `C:\Users\tim\OneDrive\Documents\Tim's Vault\`
- All paths via `pathlib.Path` — never string concatenation
- All file writes: `encoding='utf-8'`, `newline='\n'`

---

## Phase 1: Project Scaffold

### Task 1: Create directory structure and requirements.txt

**Files:**
- Create: `requirements.txt`
- Create: `prompts/summarize.txt`
- Create: `prompts/extract_claims.txt`
- Create: `prompts/identify_stakeholders.txt`
- Create: `prompts/synthesize_topic.txt`
- Create: `prompts/extract_transcript.txt`
- Create: `prompts/find_related.txt`
- Create: `prompts/output_formats/web_article.txt`
- Create: `prompts/output_formats/video_script.txt`
- Create: `prompts/output_formats/social_post.txt`
- Create: `prompts/output_formats/briefing.txt`
- Create: `prompts/output_formats/talking_points.txt`
- Create: `prompts/output_formats/email_newsletter.txt`
- Create: `.gitignore`
- Create: `tests/__init__.py`

**Step 1: Create requirements.txt**

```
anthropic>=0.25.0
python-dotenv>=1.0.0
requests>=2.31.0
PyYAML>=6.0
rich>=13.0.0
pytest>=8.0.0
pytest-mock>=3.12.0
```

**Step 2: Create .gitignore**

```
.env
__pycache__/
*.pyc
*.pyo
.pytest_cache/
repomix-output.txt
```

**Step 3: Create tests/__init__.py**

Empty file.

**Step 4: Create all prompt files**

`prompts/summarize.txt`:
```
Summarize the above content concisely. Identify: the main argument or finding, key facts or data points, and the primary significance of this material. Output 3-5 sentences of summary, followed by a "Key Points" section with 3-5 bullet points. Do not editorialize — stay close to what the source actually says.
```

`prompts/extract_claims.txt`:
```
Extract the key factual claims from the above content. For each claim: state it clearly and directly, identify who is making it, and flag whether it is presented as established fact, opinion, or speculation. Format as a numbered list. Include only claims that are substantive and specific — skip boilerplate and filler.
```

`prompts/identify_stakeholders.txt`:
```
Identify all individuals, organizations, government bodies, and companies mentioned in the above content. For each, note: their name, their role or position, and their apparent stance on the primary issue discussed. Format as a markdown table with columns: Name | Type | Role | Stance.
```

`prompts/synthesize_topic.txt`:
```
The following are research notes from multiple sources on a single topic. Synthesize them into a coherent briefing document with these sections: Executive Summary, Key Facts & Timeline, Key Players & Stakeholders, Main Arguments & Counterarguments, Current Status, Open Questions, and Suggested Next Steps. Write in clear direct prose. Do not repeat information across sections. Aim for a document that gives an informed reader a complete picture of the topic without needing to read the source notes.
```

`prompts/extract_transcript.txt`:
```
The following is a transcript. Extract and organize: (1) Key Claims — substantive factual assertions, with speaker attribution if identifiable, (2) Notable Quotes — verbatim quotes worth preserving, with context, (3) Topics Covered — a concise list, (4) Follow-up Questions — specific things worth investigating further based on what was said, (5) Suggested Tags — keywords for an Obsidian note. Format each section with a clear heading.
```

`prompts/find_related.txt`:
```
Extract exactly 10 search keywords or short phrases from the following note that would be most useful for finding related documents in a research database. Prioritize specific nouns, named entities, and domain-specific terms over generic words. Return only the terms, one per line, no explanation, no numbering.
```

`prompts/output_formats/web_article.txt`:
```
Based on the research above, write a complete web article. Include: a compelling headline, a one-paragraph lede that hooks the reader, 4-6 body sections with subheadings, and a brief conclusion. Use clear accessible prose — assume an informed general reader, not a specialist. Include a suggested meta description (150-160 characters) at the end, labeled "Meta:". Do not editorialize beyond what the research supports.
```

`prompts/output_formats/video_script.txt`:
```
Based on the research above, write a documentary-style video script. Structure it with: an opening hook (narration over establishing visuals), 3-5 main segments each with narration text and suggested b-roll descriptions in [brackets], suggested interview questions for potential subjects, and a closing segment. Format clearly with NARRATION, B-ROLL, and INTERVIEW PROMPT labels. Aim for a tone that is informative and compelling without being sensationalist.
```

`prompts/output_formats/social_post.txt`:
```
Based on the research above, draft social media content. If a platform or constraint is specified in the context, follow it exactly. Otherwise, default to a Twitter/X thread of 5-8 posts. Each post should be self-contained but flow as a series. Lead with the most compelling fact or finding. Include a clear call to action in the final post. Do not use hashtags unless the context specifies a platform where they are conventional.
```

`prompts/output_formats/briefing.txt`:
```
Based on the research above, write an executive briefing. Include: a one-paragraph situation summary, key facts as a numbered list (max 7), implications for the reader, and 2-3 concrete recommendations or next steps. Keep total length to approximately 400-500 words. Write in direct declarative sentences — no hedging, no filler.
```

`prompts/output_formats/talking_points.txt`:
```
Based on the research above, generate a talking points brief for verbal delivery. Include: a one-paragraph framing statement to open with, 5-7 numbered key points (each 1-2 sentences, factual and specific — use names, dates, and figures from the research where available), and a one-sentence closing. If context specifies a setting or time limit, calibrate the number and depth of points accordingly.
```

`prompts/output_formats/email_newsletter.txt`:
```
Based on the research above, write an email newsletter entry. Include: a subject line (labeled "Subject:"), a brief intro paragraph (2-3 sentences), the main content in 2-4 short sections with bold subheadings, and a closing call to action. Use a conversational but informed tone. Keep total length under 600 words.
```

**Step 5: Install dependencies**

```
pip install -r requirements.txt
```

Expected: all packages install without error.

**Step 6: Verify pytest works**

```
pytest tests/ -v
```

Expected: "no tests ran" or 0 collected — no errors.

**Step 7: Commit**

```bash
git init
git add requirements.txt .gitignore prompts/ tests/
git commit -m "feat: project scaffold, prompt templates, test harness"
```

---

## Phase 2: Core Foundation — discover_vault.py

### Task 2: discover_vault.py — tests

**Files:**
- Create: `tests/test_discover_vault.py`

**Step 1: Write the failing tests**

```python
# tests/test_discover_vault.py
"""Tests for discover_vault.py"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys
import os


def test_slug_only_import():
    """discover_vault module is importable without side effects."""
    # This will fail until the file exists
    import discover_vault  # noqa: F401


def test_categorize_folders_inbox():
    """Folders named like inbox are categorized correctly."""
    from discover_vault import categorize_folder
    assert categorize_folder("Inbox") == "inbox"
    assert categorize_folder("00 Inbox") == "inbox"
    assert categorize_folder("_Inbox") == "inbox"
    assert categorize_folder("Capture") == "inbox"
    assert categorize_folder("Queue") == "inbox"


def test_categorize_folders_daily():
    from discover_vault import categorize_folder
    assert categorize_folder("Daily") == "daily"
    assert categorize_folder("Daily Notes") == "daily"
    assert categorize_folder("Journal") == "daily"
    assert categorize_folder("Calendar") == "daily"


def test_categorize_folders_mocs():
    from discover_vault import categorize_folder
    assert categorize_folder("MOCs") == "mocs"
    assert categorize_folder("Maps") == "mocs"
    assert categorize_folder("_MOCs") == "mocs"
    assert categorize_folder("Index") == "mocs"


def test_categorize_folders_output():
    from discover_vault import categorize_folder
    assert categorize_folder("Output") == "output"
    assert categorize_folder("Publish") == "output"
    assert categorize_folder("Production") == "output"
    assert categorize_folder("Export") == "output"


def test_categorize_folders_unknown():
    from discover_vault import categorize_folder
    assert categorize_folder("Random Research Notes") is None


def test_find_tagging_note_found(tmp_path):
    """find_tagging_note returns path when a tag-named note exists."""
    from discover_vault import find_tagging_note
    note = tmp_path / "Tagging System.md"
    note.write_text("# Tags\n- #research", encoding="utf-8")
    result = find_tagging_note(tmp_path)
    assert result == note


def test_find_tagging_note_not_found(tmp_path):
    """find_tagging_note returns None when no tag note exists."""
    from discover_vault import find_tagging_note
    (tmp_path / "Some Note.md").write_text("content", encoding="utf-8")
    result = find_tagging_note(tmp_path)
    assert result is None


def test_find_tagging_note_nested(tmp_path):
    """find_tagging_note searches recursively."""
    from discover_vault import find_tagging_note
    sub = tmp_path / "Meta"
    sub.mkdir()
    note = sub / "Tag Methodology.md"
    note.write_text("# Tags", encoding="utf-8")
    result = find_tagging_note(tmp_path)
    assert result == note


def test_generate_env_content():
    """generate_env_content returns a valid .env string."""
    from discover_vault import generate_env_content
    content = generate_env_content(
        vault_path=Path("C:/Users/tim/Documents/Tim's Vault"),
        inbox_path=Path("C:/Users/tim/Documents/Tim's Vault/Inbox"),
        daily_path=Path("C:/Users/tim/Documents/Tim's Vault/Daily"),
        mocs_path=None,
        output_path=None,
        tagging_note_path=None,
        api_key="sk-ant-test123",
        tag_format="list",
        date_format="%Y-%m-%d",
        frontmatter_fields=["title", "source", "tags", "created"],
    )
    assert "VAULT_PATH=" in content
    assert "INBOX_PATH=" in content
    assert "ANTHROPIC_API_KEY=sk-ant-test123" in content
    assert "TAG_FORMAT=list" in content


def test_sample_tag_format_list(tmp_path):
    """sample_tag_format detects list-style tags from sample notes."""
    from discover_vault import sample_tag_format
    note = tmp_path / "note.md"
    note.write_text("---\ntags:\n  - research\n  - ai\n---\n# Title\n", encoding="utf-8")
    result = sample_tag_format(tmp_path)
    assert result == "list"


def test_sample_tag_format_inline(tmp_path):
    """sample_tag_format detects inline-style tags from sample notes."""
    from discover_vault import sample_tag_format
    note = tmp_path / "note.md"
    note.write_text("---\ntags: [research, ai]\n---\n# Title\n", encoding="utf-8")
    result = sample_tag_format(tmp_path)
    assert result == "inline"
```

**Step 2: Run to verify they fail**

```
pytest tests/test_discover_vault.py -v
```

Expected: `ModuleNotFoundError: No module named 'discover_vault'`

**Step 3: Implement discover_vault.py**

```python
"""
discover_vault.py — Vault Setup and Config Generation

Purpose: One-time setup script. Confirms vault location, introspects structure,
         reads tagging methodology note, generates config.py and .env.

Usage: python discover_vault.py

Dependencies: python-dotenv, rich, PyYAML
"""

from pathlib import Path
import os
import sys
import yaml
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm

console = Console()

INBOX_PATTERNS = {"inbox", "capture", "queue"}
DAILY_PATTERNS = {"daily", "journal", "calendar", "daily notes"}
MOCS_PATTERNS = {"mocs", "maps", "index"}
OUTPUT_PATTERNS = {"output", "publish", "production", "export"}


def categorize_folder(name: str) -> str | None:
    """Return the semantic role of a folder name, or None if unknown."""
    lower = name.lower().lstrip("_0123456789 ")
    if lower in INBOX_PATTERNS or any(p in lower for p in INBOX_PATTERNS):
        return "inbox"
    if lower in DAILY_PATTERNS or any(p in lower for p in DAILY_PATTERNS):
        return "daily"
    if lower in MOCS_PATTERNS or any(p in lower for p in MOCS_PATTERNS):
        return "mocs"
    if lower in OUTPUT_PATTERNS or any(p in lower for p in OUTPUT_PATTERNS):
        return "output"
    return None


def find_tagging_note(vault_path: Path) -> Path | None:
    """Search vault recursively for a note with 'tag' in the filename."""
    for md in vault_path.rglob("*.md"):
        if "tag" in md.stem.lower():
            return md
    return None


def sample_tag_format(vault_path: Path, sample_count: int = 10) -> str:
    """Sample up to sample_count notes to detect tag format: 'list' or 'inline'."""
    list_count = 0
    inline_count = 0
    checked = 0
    for md in vault_path.rglob("*.md"):
        if checked >= sample_count:
            break
        text = md.read_text(encoding="utf-8", errors="ignore")
        if not text.startswith("---"):
            continue
        # Find frontmatter end
        end = text.find("---", 3)
        if end == -1:
            continue
        fm_text = text[3:end]
        if "tags:" in fm_text:
            lines = fm_text.splitlines()
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("tags:"):
                    if "[" in stripped:
                        inline_count += 1
                    else:
                        list_count += 1
                    checked += 1
                    break
    return "inline" if inline_count > list_count else "list"


def generate_env_content(
    vault_path: Path,
    inbox_path: Path,
    daily_path: Path | None,
    mocs_path: Path | None,
    output_path: Path | None,
    tagging_note_path: Path | None,
    api_key: str,
    tag_format: str,
    date_format: str,
    frontmatter_fields: list[str],
) -> str:
    """Generate .env file content from discovered configuration."""
    lines = [
        f"VAULT_PATH={vault_path}",
        f"INBOX_PATH={inbox_path}",
        f"DAILY_PATH={daily_path or ''}",
        f"MOCS_PATH={mocs_path or ''}",
        f"OUTPUT_PATH={output_path or ''}",
        f"TAGGING_NOTE_PATH={tagging_note_path or ''}",
        f"ANTHROPIC_API_KEY={api_key}",
        f"TAG_FORMAT={tag_format}",
        f"DATE_FORMAT={date_format}",
        f"FRONTMATTER_FIELDS={','.join(frontmatter_fields)}",
        "CLAUDE_MODEL_HEAVY=claude-opus-4-6",
        "CLAUDE_MODEL_LIGHT=claude-haiku-4-5-20251001",
        "CLAUDE_MAX_TOKENS=4096",
    ]
    return "\n".join(lines) + "\n"


CONFIG_PY_TEMPLATE = '''# config.py — auto-generated by discover_vault.py, do not edit manually
# Edit .env for API keys; re-run discover_vault.py to update paths

from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

# Vault paths — populated by discover_vault.py
VAULT_PATH = Path(os.environ["VAULT_PATH"])
INBOX_PATH = Path(os.environ["INBOX_PATH"])
DAILY_PATH = Path(os.environ.get("DAILY_PATH", "")) if os.environ.get("DAILY_PATH") else None
MOCS_PATH = Path(os.environ.get("MOCS_PATH", "")) if os.environ.get("MOCS_PATH") else None
OUTPUT_PATH = Path(os.environ.get("OUTPUT_PATH", "")) if os.environ.get("OUTPUT_PATH") else None
TAGGING_NOTE_PATH = Path(os.environ["TAGGING_NOTE_PATH"]) if os.environ.get("TAGGING_NOTE_PATH") else None

# Detected frontmatter conventions
DATE_FORMAT = os.environ.get("DATE_FORMAT", "%Y-%m-%d")
TAG_FORMAT = os.environ.get("TAG_FORMAT", "list")  # "list" or "inline"
FRONTMATTER_FIELDS = os.environ.get("FRONTMATTER_FIELDS", "title,source,tags,created").split(",")

# API
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
CLAUDE_MODEL_HEAVY = os.environ.get("CLAUDE_MODEL_HEAVY", "claude-opus-4-6")
CLAUDE_MODEL_LIGHT = os.environ.get("CLAUDE_MODEL_LIGHT", "claude-haiku-4-5-20251001")
CLAUDE_MAX_TOKENS = int(os.environ.get("CLAUDE_MAX_TOKENS", "4096"))

# Jina
JINA_BASE_URL = "https://r.jina.ai"

# Scripts
SCRIPTS_PATH = Path(__file__).parent
PROMPTS_PATH = SCRIPTS_PATH / "prompts"
'''


def main():
    console.rule("[bold blue]Vault Setup — discover_vault.py")

    # Step 1: Confirm vault path
    user_home = Path.home()
    docs_path = user_home / "Documents"
    default_vault = "Tim's Vault"
    vault_name = Prompt.ask(
        "Vault folder name inside %USERPROFILE%\\Documents",
        default=default_vault,
    )
    # Vault is in OneDrive/Documents, not Documents directly
    onedrive_docs = user_home / "OneDrive" / "Documents"
    docs_path = onedrive_docs if onedrive_docs.exists() else user_home / "Documents"
    vault_path = docs_path / vault_name

    if not vault_path.exists():
        console.print(f"[red]Error: {vault_path} does not exist.[/red]")
        sys.exit(1)
    if not (vault_path / ".obsidian").exists():
        console.print(f"[red]Error: {vault_path} does not appear to be an Obsidian vault (.obsidian not found).[/red]")
        sys.exit(1)
    console.print(f"[green]Vault found:[/green] {vault_path}")

    # Step 2: Introspect top-level folders
    top_folders = [f for f in vault_path.iterdir() if f.is_dir() and not f.name.startswith(".")]
    roles = {}
    for folder in top_folders:
        role = categorize_folder(folder.name)
        if role:
            roles[role] = folder

    console.print("\n[bold]Detected folder roles:[/bold]")
    for role in ["inbox", "daily", "mocs", "output"]:
        detected = roles.get(role)
        console.print(f"  {role}: {detected.name if detected else '[not detected]'}")

    # Allow overrides
    for role in ["inbox", "daily", "mocs", "output"]:
        current = roles.get(role)
        prompt_msg = f"Folder for '{role}' (leave blank to skip)"
        default_val = current.name if current else ""
        user_input = Prompt.ask(prompt_msg, default=default_val)
        if user_input:
            candidate = vault_path / user_input
            if candidate.exists():
                roles[role] = candidate
            else:
                if Confirm.ask(f"Create {candidate}?"):
                    candidate.mkdir(parents=True)
                    roles[role] = candidate

    if "inbox" not in roles:
        console.print("[red]Inbox folder is required. Aborting.[/red]")
        sys.exit(1)

    # Step 3: Tagging note
    tagging_note = find_tagging_note(vault_path)
    if tagging_note:
        console.print(f"\n[green]Found tagging note:[/green] {tagging_note}")
        tag_content = tagging_note.read_text(encoding="utf-8", errors="ignore")
        # Detect format from the note content
        tag_format = "list" if "  -" in tag_content or "\n- " in tag_content else "inline"
        console.print(f"  Detected tag format: {tag_format}")
    else:
        console.print("\n[yellow]No tagging note found. Sampling vault to detect format...[/yellow]")
        tag_format = sample_tag_format(vault_path)
        console.print(f"  Detected tag format: {tag_format}")

    # Step 4: API key
    api_key = Prompt.ask("\nAnthropic API key", password=True)

    # Step 5: Write .env
    env_content = generate_env_content(
        vault_path=vault_path,
        inbox_path=roles["inbox"],
        daily_path=roles.get("daily"),
        mocs_path=roles.get("mocs"),
        output_path=roles.get("output"),
        tagging_note_path=tagging_note,
        api_key=api_key,
        tag_format=tag_format,
        date_format="%Y-%m-%d",
        frontmatter_fields=["title", "source", "tags", "created"],
    )
    env_path = Path(__file__).parent / ".env"
    env_path.write_text(env_content, encoding="utf-8", newline="\n")
    console.print(f"\n[green]Written:[/green] {env_path}")

    # Step 6: Write config.py
    config_path = Path(__file__).parent / "config.py"
    config_path.write_text(CONFIG_PY_TEMPLATE, encoding="utf-8", newline="\n")
    console.print(f"[green]Written:[/green] {config_path}")

    # Step 7: Summary table
    table = Table(title="Configuration Summary")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Vault path", str(vault_path))
    table.add_row("Inbox", str(roles["inbox"]))
    table.add_row("Daily notes", str(roles.get("daily", "not set")))
    table.add_row("MOCs", str(roles.get("mocs", "not set")))
    table.add_row("Output", str(roles.get("output", "not set")))
    table.add_row("Tagging note", str(tagging_note or "not found"))
    table.add_row("Tag format", tag_format)
    table.add_row("API key", "***" + api_key[-4:] if api_key else "not set")
    console.print(table)
    console.print("\n[yellow]Reminder: add .env to .gitignore if using version control.[/yellow]")


if __name__ == "__main__":
    main()
```

**Step 4: Run tests to verify they pass**

```
pytest tests/test_discover_vault.py -v
```

Expected: all tests PASS.

**Step 5: Run the script manually**

```
python discover_vault.py
```

Walk through prompts: confirm vault name "Tim's Vault", verify folder roles, enter API key. Confirm `config.py` and `.env` are created. Verify `config.py` loads without error:

```
python -c "import config; print(config.VAULT_PATH)"
```

**Step 6: Commit**

```bash
git add discover_vault.py config.py tests/test_discover_vault.py
git commit -m "feat: discover_vault.py — vault setup and config generation"
```

---

## Phase 3: Core Claude Pipe

### Task 3: claude_pipe.py — tests

**Files:**
- Create: `tests/test_claude_pipe.py`
- Create: `claude_pipe.py`

**Step 1: Write failing tests**

```python
# tests/test_claude_pipe.py
"""Tests for claude_pipe.py"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys
import os

# Set required env vars before importing
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/Users/tim/OneDrive/Documents/Tim's Vault")
os.environ.setdefault("INBOX_PATH", "C:/Users/tim/Documents/Tim's Vault/Inbox")


def test_import():
    import claude_pipe  # noqa: F401


def test_load_prompt_template(tmp_path):
    """load_prompt_template reads a .txt file from PROMPTS_PATH."""
    from claude_pipe import load_prompt_template
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "summarize.txt").write_text("Summarize this.", encoding="utf-8")
    result = load_prompt_template("summarize", prompt_dir)
    assert result == "Summarize this."


def test_load_prompt_template_missing(tmp_path):
    """load_prompt_template raises FileNotFoundError for unknown prompt."""
    from claude_pipe import load_prompt_template
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        load_prompt_template("nonexistent", prompt_dir)


def test_build_message():
    """build_message concatenates file content and prompt with separator."""
    from claude_pipe import build_message
    result = build_message("File content here.", "Summarize this.")
    assert "File content here." in result
    assert "Summarize this." in result
    assert "---" in result


def test_estimate_cost():
    """estimate_cost returns a float for given token counts."""
    from claude_pipe import estimate_cost
    cost = estimate_cost(1000, 500, model="claude-haiku-4-5-20251001")
    assert isinstance(cost, float)
    assert cost > 0


def test_call_claude_returns_text(tmp_path):
    """call_claude returns text response from mocked API."""
    from claude_pipe import call_claude

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Summary result")]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50

    with patch("claude_pipe.anthropic.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.return_value = mock_response
        text, usage = call_claude("test message", model="claude-haiku-4-5-20251001", max_tokens=512)

    assert text == "Summary result"
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 50


def test_write_output_with_frontmatter(tmp_path):
    """write_output writes markdown with frontmatter when output path given."""
    from claude_pipe import write_output
    out_file = tmp_path / "result.md"
    write_output("Response text", out_file, source_note="note.md", prompt_used="summarize")
    content = out_file.read_text(encoding="utf-8")
    assert "---" in content
    assert "source_note: note.md" in content
    assert "prompt_used: summarize" in content
    assert "Response text" in content
```

**Step 2: Run to verify they fail**

```
pytest tests/test_claude_pipe.py -v
```

Expected: `ModuleNotFoundError: No module named 'claude_pipe'`

**Step 3: Implement claude_pipe.py**

```python
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

console = Console()

# Approximate cost per million tokens (USD) — update as pricing changes
COST_PER_M_INPUT = {
    "claude-opus-4-6": 15.0,
    "claude-haiku-4-5-20251001": 0.25,
}
COST_PER_M_OUTPUT = {
    "claude-opus-4-6": 75.0,
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
    in_rate = COST_PER_M_INPUT.get(model, 15.0)
    out_rate = COST_PER_M_OUTPUT.get(model, 75.0)
    return (input_tokens / 1_000_000 * in_rate) + (output_tokens / 1_000_000 * out_rate)


def call_claude(message: str, model: str, max_tokens: int) -> tuple[str, dict]:
    """Send message to Claude API, return (response_text, usage_dict)."""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
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
    frontmatter = (
        f"---\n"
        f"source_note: {source_note}\n"
        f"generated_at: {now}\n"
        f"prompt_used: {prompt_used}\n"
        f"---\n\n"
    )
    output_path.write_text(frontmatter + response_text, encoding="utf-8", newline="\n")


def startup_checks():
    """Verify required config before running."""
    errors = []
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


def main():
    parser = argparse.ArgumentParser(description="Pipe a file through Claude with a named prompt template.")
    parser.add_argument("--file", required=True, help="Path to the input file")
    parser.add_argument("--prompt", required=True, help="Prompt template name (without .txt)")
    parser.add_argument("--output", help="Output file path (prints to stdout if not set)")
    parser.add_argument("--model", choices=["light", "heavy"], default="heavy",
                        help="'light' = Haiku, 'heavy' = Opus (default)")
    parser.add_argument("--dry-run", action="store_true", help="Print message without calling API")
    args = parser.parse_args()

    startup_checks()

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
        out_path = Path(args.output)
        write_output(response_text, out_path, source_note=str(file_path), prompt_used=args.prompt)
        console.print(f"[green]Output written:[/green] {out_path}")
    else:
        console.print(response_text)


if __name__ == "__main__":
    main()
```

**Step 4: Run tests**

```
pytest tests/test_claude_pipe.py -v
```

Expected: all PASS.

**Step 5: Test manually with a real vault note**

```
python claude_pipe.py --file "C:\Users\tim\Documents\Tim's Vault\Inbox\some-note.md" --prompt summarize --model light --dry-run
```

**Step 6: Commit**

```bash
git add claude_pipe.py tests/test_claude_pipe.py
git commit -m "feat: claude_pipe.py — core Claude API building block"
```

---

## Phase 4: Ingestion

### Task 4: ingest.py — tests and implementation

**Files:**
- Create: `tests/test_ingest.py`
- Create: `ingest.py`

**Step 1: Write failing tests**

```python
# tests/test_ingest.py
"""Tests for ingest.py"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/fake/vault")
os.environ.setdefault("INBOX_PATH", "C:/fake/vault/Inbox")


def test_slugify_basic():
    from ingest import slugify
    assert slugify("Hello World") == "hello-world"


def test_slugify_special_chars():
    from ingest import slugify
    assert slugify("Hello, World! (2024)") == "hello-world-2024"


def test_slugify_max_length():
    from ingest import slugify
    long = "a" * 100
    result = slugify(long)
    assert len(result) <= 60


def test_slugify_leading_trailing_hyphens():
    from ingest import slugify
    result = slugify("---hello---")
    assert not result.startswith("-")
    assert not result.endswith("-")


def test_extract_title_from_heading():
    from ingest import extract_title
    content = "# My Article Title\n\nSome content here."
    assert extract_title(content, "https://example.com/article") == "My Article Title"


def test_extract_title_fallback_to_domain():
    from ingest import extract_title
    content = "No heading here, just plain text."
    assert extract_title(content, "https://example.com/article") == "example.com"


def test_build_frontmatter_list_tags():
    from ingest import build_frontmatter
    fm = build_frontmatter(
        title="Test Article",
        source="https://example.com",
        fetched_at="2026-02-25T12:00:00+00:00",
        tag_format="list",
        extra_fields=["summary"],
    )
    assert "title: Test Article" in fm
    assert "source: https://example.com" in fm
    assert "- inbox" in fm
    assert "- unprocessed" in fm


def test_build_frontmatter_inline_tags():
    from ingest import build_frontmatter
    fm = build_frontmatter(
        title="Test Article",
        source="https://example.com",
        fetched_at="2026-02-25T12:00:00+00:00",
        tag_format="inline",
        extra_fields=[],
    )
    assert "tags: [inbox, unprocessed]" in fm


def test_unique_output_path(tmp_path):
    from ingest import unique_output_path
    slug = "my-article"
    date = "2026-02-25"
    path1 = unique_output_path(tmp_path, date, slug)
    assert path1 == tmp_path / "2026-02-25-my-article.md"
    # Create first file
    path1.write_text("content", encoding="utf-8")
    path2 = unique_output_path(tmp_path, date, slug)
    assert path2 == tmp_path / "2026-02-25-my-article-2.md"


def test_fetch_url_success():
    from ingest import fetch_url
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "# Article\n\nContent here."
    with patch("ingest.requests.get", return_value=mock_response):
        result = fetch_url("https://example.com/article")
    assert "Article" in result


def test_fetch_url_failure():
    from ingest import fetch_url
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = Exception("404")
    with patch("ingest.requests.get", return_value=mock_response):
        with pytest.raises(Exception):
            fetch_url("https://example.com/404")
```

**Step 2: Run to verify they fail**

```
pytest tests/test_ingest.py -v
```

**Step 3: Implement ingest.py**

```python
"""
ingest.py — URL to Vault Inbox

Purpose: Fetch a URL via Jina Reader, write a clean markdown note to the vault inbox.

Usage: python ingest.py "https://example.com/article"
       python ingest.py "https://example.com/article" --dry-run

Dependencies: requests, rich, python-dotenv
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from rich.console import Console

import config

console = Console()


def slugify(text: str, max_length: int = 60) -> str:
    """Convert text to a URL-safe slug."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s]+", "-", text.strip())
    text = re.sub(r"-+", "-", text)
    text = text[:max_length].strip("-")
    return text


def extract_title(content: str, url: str) -> str:
    """Extract title from first # heading, fall back to domain."""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return urlparse(url).netloc


def build_frontmatter(
    title: str,
    source: str,
    fetched_at: str,
    tag_format: str,
    extra_fields: list[str],
) -> str:
    """Build YAML frontmatter matching vault conventions."""
    if tag_format == "inline":
        tags_line = "tags: [inbox, unprocessed]"
    else:
        tags_line = "tags:\n  - inbox\n  - unprocessed"

    extras = "\n".join(f"{field}: " for field in extra_fields if field not in
                       {"title", "source", "fetched_at", "tags"})
    extras_block = f"\n{extras}" if extras else ""

    return (
        f"---\n"
        f"title: {title}\n"
        f"source: {source}\n"
        f"fetched_at: {fetched_at}\n"
        f"{tags_line}{extras_block}\n"
        f"---\n\n"
    )


def unique_output_path(inbox_path: Path, date: str, slug: str) -> Path:
    """Return a unique file path, appending -2, -3, etc. if needed."""
    base = inbox_path / f"{date}-{slug}.md"
    if not base.exists():
        return base
    counter = 2
    while True:
        candidate = inbox_path / f"{date}-{slug}-{counter}.md"
        if not candidate.exists():
            return candidate
        counter += 1


def fetch_url(url: str) -> str:
    """Fetch URL via Jina Reader and return markdown content."""
    jina_url = f"{config.JINA_BASE_URL}/{url}"
    response = requests.get(jina_url, timeout=30)
    response.raise_for_status()
    return response.text


def startup_checks():
    errors = []
    if not config.ANTHROPIC_API_KEY:
        errors.append("ANTHROPIC_API_KEY not set in .env")
    if not config.VAULT_PATH.exists():
        errors.append(f"VAULT_PATH does not exist: {config.VAULT_PATH}")
    inbox = config.INBOX_PATH
    if not inbox.exists():
        console.print(f"[yellow]Inbox not found, creating: {inbox}[/yellow]")
        inbox.mkdir(parents=True)
    if errors:
        for e in errors:
            console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


def ingest_url(url: str, dry_run: bool = False) -> Path | None:
    """Core ingestion logic. Returns output path or None on dry run."""
    console.print(f"Fetching: {url}")
    with console.status("Fetching via Jina Reader..."):
        content = fetch_url(url)

    title = extract_title(content, url)
    slug = slugify(title)
    now = datetime.now(timezone.utc)
    date_str = now.strftime(config.DATE_FORMAT)
    fetched_at = now.isoformat()

    frontmatter = build_frontmatter(
        title=title,
        source=url,
        fetched_at=fetched_at,
        tag_format=config.TAG_FORMAT,
        extra_fields=config.FRONTMATTER_FIELDS,
    )
    full_content = frontmatter + content

    if dry_run:
        console.print(f"[yellow]Dry run — would write to: {config.INBOX_PATH / f'{date_str}-{slug}.md'}[/yellow]")
        console.print(full_content[:300] + "...")
        return None

    out_path = unique_output_path(config.INBOX_PATH, date_str, slug)
    out_path.write_text(full_content, encoding="utf-8", newline="\n")
    console.print(f"[green]Written:[/green] {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Fetch a URL and save to vault inbox.")
    parser.add_argument("url", help="URL to fetch")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    startup_checks()
    ingest_url(args.url, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
```

**Step 4: Run tests**

```
pytest tests/test_ingest.py -v
```

**Step 5: Integration test with real URL**

```
python ingest.py "https://en.wikipedia.org/wiki/Obsidian_(software)" --dry-run
```

**Step 6: Commit**

```bash
git add ingest.py tests/test_ingest.py
git commit -m "feat: ingest.py — URL to vault inbox via Jina Reader"
```

---

### Task 5: ingest_batch.py — tests and implementation

**Files:**
- Create: `tests/test_ingest_batch.py`
- Create: `ingest_batch.py`

**Step 1: Write failing tests**

```python
# tests/test_ingest_batch.py
"""Tests for ingest_batch.py"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/fake/vault")
os.environ.setdefault("INBOX_PATH", "C:/fake/vault/Inbox")


def test_parse_url_file(tmp_path):
    """parse_url_file skips blank lines and comments."""
    from ingest_batch import parse_url_file
    url_file = tmp_path / "urls.txt"
    url_file.write_text(
        "https://example.com/1\n"
        "\n"
        "# This is a comment\n"
        "https://example.com/2\n",
        encoding="utf-8",
    )
    urls = parse_url_file(url_file)
    assert urls == ["https://example.com/1", "https://example.com/2"]


def test_parse_url_file_missing(tmp_path):
    """parse_url_file raises FileNotFoundError for missing file."""
    from ingest_batch import parse_url_file
    with pytest.raises(FileNotFoundError):
        parse_url_file(tmp_path / "nonexistent.txt")


def test_write_failed_urls(tmp_path):
    """write_failed_urls creates a file with failed URLs."""
    from ingest_batch import write_failed_urls
    failed = ["https://example.com/failed1", "https://example.com/failed2"]
    out = tmp_path / "failed_urls.txt"
    write_failed_urls(failed, out)
    content = out.read_text(encoding="utf-8")
    assert "https://example.com/failed1" in content
    assert "https://example.com/failed2" in content
```

**Step 2: Run to verify they fail**

```
pytest tests/test_ingest_batch.py -v
```

**Step 3: Implement ingest_batch.py**

```python
"""
ingest_batch.py — Batch URL Ingestion

Purpose: Process a list of URLs from a text file.

Usage: python ingest_batch.py urls.txt
       python ingest_batch.py urls.txt --dry-run

Dependencies: rich, python-dotenv (ingest.py for core logic)
"""

import argparse
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.progress import track

import config
from ingest import ingest_url, startup_checks

console = Console()


def parse_url_file(url_file: Path) -> list[str]:
    """Parse URLs from file, skipping blank lines and # comments."""
    if not url_file.exists():
        raise FileNotFoundError(f"URL file not found: {url_file}")
    urls = []
    for line in url_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            urls.append(stripped)
    return urls


def write_failed_urls(failed: list[str], out_path: Path) -> None:
    """Write list of failed URLs to a file."""
    out_path.write_text("\n".join(failed) + "\n", encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description="Batch ingest URLs from a file.")
    parser.add_argument("url_file", help="Path to text file with one URL per line")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    startup_checks()

    url_file = Path(args.url_file)
    urls = parse_url_file(url_file)
    console.print(f"Found {len(urls)} URLs to process.")

    succeeded = 0
    failed = []

    for url in track(urls, description="Ingesting URLs..."):
        try:
            ingest_url(url, dry_run=args.dry_run)
            succeeded += 1
        except Exception as e:
            console.print(f"[red]Failed:[/red] {url} — {e}")
            failed.append(url)
        time.sleep(2)

    console.print(f"\n[green]Succeeded:[/green] {succeeded} / {len(urls)}")
    if failed:
        failed_path = Path("failed_urls.txt")
        write_failed_urls(failed, failed_path)
        console.print(f"[yellow]Failed URLs written to:[/yellow] {failed_path}")


if __name__ == "__main__":
    main()
```

**Step 4: Run tests**

```
pytest tests/test_ingest_batch.py -v
```

**Step 5: Commit**

```bash
git add ingest_batch.py tests/test_ingest_batch.py
git commit -m "feat: ingest_batch.py — batch URL ingestion"
```

---

## Phase 5: Vault Tools

### Task 6: vault_lint.py — tests and implementation

**Files:**
- Create: `tests/test_vault_lint.py`
- Create: `vault_lint.py`

**Step 1: Write failing tests**

```python
# tests/test_vault_lint.py
"""Tests for vault_lint.py"""

import pytest
from pathlib import Path
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/fake/vault")
os.environ.setdefault("INBOX_PATH", "C:/fake/vault/Inbox")
os.environ.setdefault("FRONTMATTER_FIELDS", "title,source,tags,created")


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
```

**Step 2: Run to verify they fail**

```
pytest tests/test_vault_lint.py -v
```

**Step 3: Implement vault_lint.py**

```python
"""
vault_lint.py — Frontmatter Validator

Purpose: Find notes missing required frontmatter fields.

Usage:
    python vault_lint.py
    python vault_lint.py --folder Campaigns
    python vault_lint.py --fix

Dependencies: PyYAML, rich, python-dotenv
"""

import argparse
import sys
from pathlib import Path

import yaml
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

import config

console = Console()


def parse_frontmatter(note_path: Path) -> dict:
    """Parse YAML frontmatter from a markdown note. Returns empty dict if none."""
    text = note_path.read_text(encoding="utf-8", errors="ignore")
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    try:
        return yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        return {}


def find_missing_fields(frontmatter: dict, required: list[str]) -> list[str]:
    """Return list of required fields missing or empty in frontmatter."""
    return [f for f in required if not frontmatter.get(f)]


def lint_vault(vault_path: Path, required_fields: list[str]) -> list[dict]:
    """Walk vault, return list of {file, missing} dicts for notes with issues."""
    issues = []
    for md in sorted(vault_path.rglob("*.md")):
        fm = parse_frontmatter(md)
        missing = find_missing_fields(fm, required_fields)
        if missing:
            issues.append({"file": md, "missing": missing, "frontmatter": fm})
    return issues


def fix_issue(note_path: Path, missing_fields: list[str]) -> None:
    """Interactively prompt for missing field values and write them back."""
    text = note_path.read_text(encoding="utf-8", errors="ignore")
    if text.startswith("---"):
        end = text.find("---", 3)
        fm_text = text[3:end]
        rest = text[end + 3:]
    else:
        fm_text = ""
        rest = text

    additions = []
    for field in missing_fields:
        value = Prompt.ask(f"  Value for '{field}' in {note_path.name}")
        additions.append(f"{field}: {value}")

    new_fm = fm_text.rstrip() + "\n" + "\n".join(additions) + "\n"
    note_path.write_text(f"---{new_fm}---{rest}", encoding="utf-8", newline="\n")


def startup_checks():
    if not config.VAULT_PATH.exists():
        console.print(f"[red]VAULT_PATH does not exist: {config.VAULT_PATH}[/red]")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Find notes missing required frontmatter.")
    parser.add_argument("--folder", help="Subfolder within vault to lint (default: whole vault)")
    parser.add_argument("--fix", action="store_true", help="Interactively fix missing fields")
    args = parser.parse_args()

    startup_checks()

    target = config.VAULT_PATH / args.folder if args.folder else config.VAULT_PATH
    if not target.exists():
        console.print(f"[red]Folder not found: {target}[/red]")
        sys.exit(1)

    issues = lint_vault(target, config.FRONTMATTER_FIELDS)

    if not issues:
        console.print("[green]No issues found.[/green]")
        sys.exit(0)

    table = Table(title=f"Frontmatter Issues ({len(issues)} notes)")
    table.add_column("File", style="cyan")
    table.add_column("Missing Fields", style="red")
    for issue in issues:
        rel = issue["file"].relative_to(config.VAULT_PATH)
        table.add_row(str(rel), ", ".join(issue["missing"]))
    console.print(table)

    if args.fix:
        for issue in issues:
            console.print(f"\n[bold]{issue['file'].name}[/bold]")
            fix_issue(issue["file"], issue["missing"])
        console.print("[green]Done fixing issues.[/green]")

    sys.exit(1)


if __name__ == "__main__":
    main()
```

**Step 4: Run tests**

```
pytest tests/test_vault_lint.py -v
```

**Step 5: Commit**

```bash
git add vault_lint.py tests/test_vault_lint.py
git commit -m "feat: vault_lint.py — frontmatter validator"
```

---

### Task 7: find_broken_links.py — tests and implementation

**Files:**
- Create: `tests/test_find_broken_links.py`
- Create: `find_broken_links.py`

**Step 1: Write failing tests**

```python
# tests/test_find_broken_links.py
"""Tests for find_broken_links.py"""

import pytest
from pathlib import Path
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/fake/vault")
os.environ.setdefault("INBOX_PATH", "C:/fake/vault/Inbox")


def test_extract_links_basic():
    from find_broken_links import extract_links
    content = "See [[My Note]] and [[Other Note|alias]]."
    links = extract_links(content)
    assert "My Note" in links
    assert "Other Note" in links
    assert "alias" not in links


def test_extract_links_heading_ref():
    from find_broken_links import extract_links
    links = extract_links("See [[Note#Section]].")
    assert "Note" in links


def test_normalize_link():
    from find_broken_links import normalize_link
    assert normalize_link("My Note") == "my note"
    assert normalize_link("My%20Note") == "my note"
    assert normalize_link("Note#Section") == "note"


def test_build_note_index(tmp_path):
    from find_broken_links import build_note_index
    (tmp_path / "My Note.md").write_text("", encoding="utf-8")
    (tmp_path / "Other.md").write_text("", encoding="utf-8")
    index = build_note_index(tmp_path)
    assert "my note" in index
    assert "other" in index


def test_find_broken_links_detects_broken(tmp_path):
    from find_broken_links import find_broken_links
    note = tmp_path / "note.md"
    note.write_text("See [[Nonexistent Note]] and [[note]].", encoding="utf-8")
    broken = find_broken_links(tmp_path)
    assert any(b["link"] == "Nonexistent Note" for b in broken)
    # note itself should not be broken (it exists)
    assert not any(b["link"] == "note" for b in broken)


def test_find_broken_links_none_broken(tmp_path):
    from find_broken_links import find_broken_links
    (tmp_path / "Target.md").write_text("", encoding="utf-8")
    (tmp_path / "source.md").write_text("See [[Target]].", encoding="utf-8")
    broken = find_broken_links(tmp_path)
    assert broken == []
```

**Step 2: Run to verify they fail**

```
pytest tests/test_find_broken_links.py -v
```

**Step 3: Implement find_broken_links.py**

```python
"""
find_broken_links.py — Wiki-Link Checker

Purpose: Find [[wiki-links]] that don't resolve to existing files.

Usage: python find_broken_links.py

Dependencies: rich, python-dotenv
"""

import re
import sys
from pathlib import Path
from urllib.parse import unquote

from rich.console import Console
from rich.table import Table

import config

console = Console()


def extract_links(content: str) -> list[str]:
    """Extract all [[link]] and [[link|alias]] targets from content."""
    matches = re.findall(r"\[\[([^\]]+)\]\]", content)
    links = []
    for match in matches:
        # Strip alias
        target = match.split("|")[0]
        # Strip heading reference
        target = target.split("#")[0].strip()
        if target:
            links.append(target)
    return links


def normalize_link(link: str) -> str:
    """Normalize a link for comparison: strip heading, URL-decode, lowercase."""
    link = link.split("#")[0]
    link = unquote(link).strip().lower()
    return link


def build_note_index(vault_path: Path) -> set[str]:
    """Build a set of normalized note stems for fast lookup."""
    return {md.stem.lower() for md in vault_path.rglob("*.md")}


def find_broken_links(vault_path: Path) -> list[dict]:
    """Return list of {file, link} dicts for broken wiki-links."""
    index = build_note_index(vault_path)
    broken = []
    for md in sorted(vault_path.rglob("*.md")):
        content = md.read_text(encoding="utf-8", errors="ignore")
        for link in extract_links(content):
            if normalize_link(link) not in index:
                broken.append({"file": md, "link": link})
    return broken


def startup_checks():
    if not config.VAULT_PATH.exists():
        console.print(f"[red]VAULT_PATH does not exist: {config.VAULT_PATH}[/red]")
        sys.exit(1)


def main():
    startup_checks()
    broken = find_broken_links(config.VAULT_PATH)

    if not broken:
        console.print("[green]No broken links found.[/green]")
        sys.exit(0)

    table = Table(title=f"Broken Wiki-Links ({len(broken)} found)")
    table.add_column("File", style="cyan")
    table.add_column("Broken Link", style="red")
    for item in broken:
        rel = item["file"].relative_to(config.VAULT_PATH)
        table.add_row(str(rel), item["link"])
    console.print(table)
    sys.exit(1)


if __name__ == "__main__":
    main()
```

**Step 4: Run tests**

```
pytest tests/test_find_broken_links.py -v
```

**Step 5: Commit**

```bash
git add find_broken_links.py tests/test_find_broken_links.py
git commit -m "feat: find_broken_links.py — wiki-link checker"
```

---

### Task 8: find_related.py — tests and implementation

**Files:**
- Create: `tests/test_find_related.py`
- Create: `find_related.py`

**Step 1: Write failing tests**

```python
# tests/test_find_related.py
"""Tests for find_related.py"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/fake/vault")
os.environ.setdefault("INBOX_PATH", "C:/fake/vault/Inbox")


def test_parse_keywords():
    from find_related import parse_keywords
    text = "machine learning\nneural networks\ntransformers\n"
    result = parse_keywords(text)
    assert result == ["machine learning", "neural networks", "transformers"]


def test_parse_keywords_strips_empty():
    from find_related import parse_keywords
    text = "term one\n\n   \nterm two\n"
    result = parse_keywords(text)
    assert result == ["term one", "term two"]


def test_search_vault_python(tmp_path):
    """search_vault_python returns scored notes matching keywords."""
    from find_related import search_vault_python
    note1 = tmp_path / "machine-learning.md"
    note1.write_text("Machine learning and neural networks.", encoding="utf-8")
    note2 = tmp_path / "cooking.md"
    note2.write_text("Recipes and ingredients.", encoding="utf-8")
    note3 = tmp_path / "transformers.md"
    note3.write_text("Transformers are neural network architectures.", encoding="utf-8")

    results = search_vault_python(
        tmp_path,
        keywords=["machine learning", "neural networks", "transformers"],
        source_path=None,
    )
    # machine-learning.md and transformers.md should score higher than cooking.md
    scored = {r["file"].name: r["score"] for r in results}
    assert scored.get("machine-learning.md", 0) > scored.get("cooking.md", 0)
    assert "cooking.md" not in [r["file"].name for r in results[:2]]


def test_search_vault_excludes_source(tmp_path):
    """search_vault_python excludes the source note from results."""
    from find_related import search_vault_python
    source = tmp_path / "source.md"
    source.write_text("Machine learning content.", encoding="utf-8")
    results = search_vault_python(tmp_path, keywords=["machine learning"], source_path=source)
    assert all(r["file"] != source for r in results)
```

**Step 2: Run to verify they fail**

```
pytest tests/test_find_related.py -v
```

**Step 3: Implement find_related.py**

```python
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
```

**Step 4: Run tests**

```
pytest tests/test_find_related.py -v
```

**Step 5: Commit**

```bash
git add find_related.py tests/test_find_related.py
git commit -m "feat: find_related.py — related notes finder"
```

---

## Phase 6: Synthesis and Production

### Task 9: synthesize_folder.py — tests and implementation

**Files:**
- Create: `tests/test_synthesize_folder.py`
- Create: `synthesize_folder.py`
- Create: `repomix.config.json`

**Step 1: Write failing tests**

```python
# tests/test_synthesize_folder.py
"""Tests for synthesize_folder.py"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/fake/vault")
os.environ.setdefault("INBOX_PATH", "C:/fake/vault/Inbox")


def test_collect_markdown_files(tmp_path):
    from synthesize_folder import collect_markdown_files
    (tmp_path / "note1.md").write_text("Content 1", encoding="utf-8")
    (tmp_path / "note2.md").write_text("Content 2", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "note3.md").write_text("Content 3", encoding="utf-8")

    files_non_recursive = collect_markdown_files(tmp_path, recursive=False)
    assert len(files_non_recursive) == 2

    files_recursive = collect_markdown_files(tmp_path, recursive=True)
    assert len(files_recursive) == 3


def test_concatenate_files(tmp_path):
    from synthesize_folder import concatenate_files
    note1 = tmp_path / "alpha.md"
    note1.write_text("Alpha content", encoding="utf-8")
    note2 = tmp_path / "beta.md"
    note2.write_text("Beta content", encoding="utf-8")

    result = concatenate_files([note1, note2])
    assert "Alpha content" in result
    assert "Beta content" in result
    assert "# Source: alpha.md" in result
    assert "# Source: beta.md" in result


def test_estimate_tokens():
    from synthesize_folder import estimate_tokens
    text = "word " * 1000
    tokens = estimate_tokens(text)
    # Rough estimate: ~750 tokens per 1000 words (4 chars/token)
    assert 200 < tokens < 2000


def test_repomix_available_check():
    from synthesize_folder import check_repomix
    # Just verify it returns a bool
    result = check_repomix()
    assert isinstance(result, bool)
```

**Step 2: Run to verify they fail**

```
pytest tests/test_synthesize_folder.py -v
```

**Step 3: Create repomix.config.json**

```json
{
  "output": {
    "filePath": "repomix-output.txt",
    "style": "markdown",
    "headerText": "Research notes for synthesis. Each file is separated by a horizontal rule and labeled with its filename.",
    "removeComments": false,
    "removeEmptyLines": false,
    "showLineNumbers": false,
    "copyToClipboard": false
  },
  "ignore": {
    "useGitignore": false,
    "useDefaultPatterns": true,
    "customPatterns": [
      "*.canvas",
      ".obsidian/**",
      "_templates/**",
      "Daily/**",
      "daily/**",
      "Journal/**",
      "Calendar/**"
    ]
  },
  "security": {
    "enableSecurityCheck": false
  }
}
```

**Note:** Update `customPatterns` to match whichever folder was identified as daily notes during vault discovery.

**Step 4: Implement synthesize_folder.py**

```python
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


def check_repomix() -> bool:
    """Return True if repomix is available on PATH."""
    return shutil.which("repomix") is not None


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
    subprocess.run(
        ["repomix", "--config", str(config_path), "--output-file", str(output_path), str(folder)],
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
    out_path = out_dir / args.output
    out_path.write_text(full_output, encoding="utf-8", newline="\n")
    console.print(f"[green]MOC written:[/green] {out_path}")


if __name__ == "__main__":
    main()
```

**Step 5: Run tests**

```
pytest tests/test_synthesize_folder.py -v
```

**Step 6: Commit**

```bash
git add synthesize_folder.py repomix.config.json tests/test_synthesize_folder.py
git commit -m "feat: synthesize_folder.py — folder synthesis to MOC"
```

---

### Task 10: produce_output.py — tests and implementation

**Files:**
- Create: `tests/test_produce_output.py`
- Create: `produce_output.py`

**Step 1: Write failing tests**

```python
# tests/test_produce_output.py
"""Tests for produce_output.py"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/fake/vault")
os.environ.setdefault("INBOX_PATH", "C:/fake/vault/Inbox")


def test_list_formats(tmp_path):
    from produce_output import list_formats
    (tmp_path / "web_article.txt").write_text("prompt", encoding="utf-8")
    (tmp_path / "briefing.txt").write_text("prompt", encoding="utf-8")
    formats = list_formats(tmp_path)
    assert "web_article" in formats
    assert "briefing" in formats


def test_list_formats_empty(tmp_path):
    from produce_output import list_formats
    formats = list_formats(tmp_path)
    assert formats == []


def test_build_output_path_with_output_path(tmp_path):
    from produce_output import build_output_path
    result = build_output_path(
        output_dir=tmp_path,
        date_str="2026-02-25",
        source_slug="my-research",
        fmt="web_article",
    )
    assert result == tmp_path / "2026-02-25-my-research-web_article.md"


def test_load_format_prompt(tmp_path):
    from produce_output import load_format_prompt
    (tmp_path / "web_article.txt").write_text("Write an article.", encoding="utf-8")
    result = load_format_prompt("web_article", tmp_path)
    assert result == "Write an article."


def test_load_format_prompt_missing(tmp_path):
    from produce_output import load_format_prompt
    with pytest.raises(FileNotFoundError):
        load_format_prompt("nonexistent", tmp_path)
```

**Step 2: Run to verify they fail**

```
pytest tests/test_produce_output.py -v
```

**Step 3: Implement produce_output.py**

```python
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
from claude_pipe import call_claude, estimate_cost
from ingest import slugify

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
    """Build the output file path."""
    return output_dir / f"{date_str}-{source_slug}-{fmt}.md"


def startup_checks():
    if not config.VAULT_PATH.exists():
        console.print(f"[red]VAULT_PATH does not exist: {config.VAULT_PATH}[/red]")
        sys.exit(1)


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
    message = f"{content}\n\n---\n{format_prompt}"

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
```

**Step 4: Run tests**

```
pytest tests/test_produce_output.py -v
```

**Step 5: Commit**

```bash
git add produce_output.py tests/test_produce_output.py
git commit -m "feat: produce_output.py — research to production format"
```

---

## Phase 7: Specialty Scripts

### Task 11: transcript_processor.py — tests and implementation

**Files:**
- Create: `tests/test_transcript_processor.py`
- Create: `transcript_processor.py`

**Step 1: Write failing tests**

```python
# tests/test_transcript_processor.py
"""Tests for transcript_processor.py"""

import pytest
from pathlib import Path
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/fake/vault")
os.environ.setdefault("INBOX_PATH", "C:/fake/vault/Inbox")


def test_strip_vtt_timestamps():
    from transcript_processor import strip_vtt
    vtt = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:05.000\n"
        "Hello, this is the first line.\n\n"
        "00:00:06.000 --> 00:00:10.000\n"
        "And this is the second.\n"
    )
    result = strip_vtt(vtt)
    assert "WEBVTT" not in result
    assert "00:00" not in result
    assert "Hello, this is the first line." in result
    assert "And this is the second." in result


def test_strip_vtt_plain_text_passthrough():
    from transcript_processor import strip_vtt
    text = "This is a plain text transcript."
    result = strip_vtt(text)
    assert result == text


def test_detect_format_vtt():
    from transcript_processor import detect_format
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nHello."
    assert detect_format(vtt) == "vtt"


def test_detect_format_txt():
    from transcript_processor import detect_format
    txt = "Speaker: Hello, welcome to the interview."
    assert detect_format(txt) == "txt"


def test_build_output_paths(tmp_path):
    from transcript_processor import build_output_paths
    notes_path, quotes_path = build_output_paths(tmp_path, "2026-02-25", "my-interview")
    assert notes_path == tmp_path / "2026-02-25-my-interview-notes.md"
    assert quotes_path == tmp_path / "2026-02-25-my-interview-quotes.md"
```

**Step 2: Run to verify they fail**

```
pytest tests/test_transcript_processor.py -v
```

**Step 3: Implement transcript_processor.py**

```python
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
from claude_pipe import call_claude, load_prompt_template
from ingest import slugify

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


def startup_checks():
    if not config.VAULT_PATH.exists():
        console.print(f"[red]VAULT_PATH does not exist: {config.VAULT_PATH}[/red]")
        sys.exit(1)


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

    output_dir = Path(args.output_dir) if args.output_dir else config.INBOX_PATH
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

    from claude_pipe import estimate_cost
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
```

**Step 4: Run tests**

```
pytest tests/test_transcript_processor.py -v
```

**Step 5: Commit**

```bash
git add transcript_processor.py tests/test_transcript_processor.py
git commit -m "feat: transcript_processor.py — transcript to research notes"
```

---

### Task 12: daily_digest.py — tests and implementation

**Files:**
- Create: `tests/test_daily_digest.py`
- Create: `daily_digest.py`

**Step 1: Write failing tests**

```python
# tests/test_daily_digest.py
"""Tests for daily_digest.py"""

import pytest
from pathlib import Path
from unittest.mock import patch
import os
import time

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/fake/vault")
os.environ.setdefault("INBOX_PATH", "C:/fake/vault/Inbox")
os.environ.setdefault("DAILY_PATH", "C:/fake/vault/Daily")


def test_find_recent_notes(tmp_path):
    from daily_digest import find_recent_notes
    recent = tmp_path / "recent.md"
    recent.write_text("Recent content", encoding="utf-8")
    # old file: modify mtime to 48 hours ago
    old = tmp_path / "old.md"
    old.write_text("Old content", encoding="utf-8")
    old_time = time.time() - (48 * 3600)
    import os as _os
    _os.utime(old, (old_time, old_time))

    results = find_recent_notes(tmp_path, hours=24, exclude_paths=set())
    names = [r.name for r in results]
    assert "recent.md" in names
    assert "old.md" not in names


def test_find_recent_notes_excludes(tmp_path):
    from daily_digest import find_recent_notes
    note = tmp_path / "note.md"
    note.write_text("Content", encoding="utf-8")
    results = find_recent_notes(tmp_path, hours=24, exclude_paths={note})
    assert note not in results


def test_extract_note_preview():
    from daily_digest import extract_note_preview
    content = "---\ntitle: Test\n---\n\n# Heading\n\nLorem ipsum dolor sit amet, consectetur adipiscing elit. " * 10
    preview = extract_note_preview(content, max_chars=500)
    assert len(preview) <= 510  # small buffer for truncation marker


def test_format_digest_entry():
    from daily_digest import format_digest_entry
    entry = format_digest_entry("My Note.md", "Preview of content here.")
    assert "My Note.md" in entry
    assert "Preview of content here." in entry


def test_build_daily_note_template():
    from daily_digest import build_daily_note_template
    result = build_daily_note_template("2026-02-25")
    assert "2026-02-25" in result
    assert "---" in result


def test_append_digest_section(tmp_path):
    from daily_digest import append_digest_section
    daily_note = tmp_path / "2026-02-25.md"
    daily_note.write_text("---\ndate: 2026-02-25\n---\n\n# Daily Note\n", encoding="utf-8")
    append_digest_section(daily_note, "## Research Digest\n\nSome content here.")
    content = daily_note.read_text(encoding="utf-8")
    assert "## Research Digest" in content
    assert "Some content here." in content
```

**Step 2: Run to verify they fail**

```
pytest tests/test_daily_digest.py -v
```

**Step 3: Implement daily_digest.py**

```python
"""
daily_digest.py — Daily Vault Summary

Purpose: Summarize today's new/modified notes, append to daily note.

Usage:
    python daily_digest.py
    python daily_digest.py --setup-scheduler

Dependencies: anthropic, rich, python-dotenv
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

import config
from claude_pipe import call_claude, estimate_cost

console = Console()

SCHEDULER_INSTRUCTIONS = """
To run daily_digest.py automatically each morning:
1. Open Task Scheduler (search "Task Scheduler" in Start menu)
2. Action → Create Basic Task → name it "Vault Daily Digest"
3. Trigger: Daily, at your preferred time
4. Action: Start a Program
   Program/script: python
   Arguments:      {scripts_path}\\daily_digest.py
   Start in:       {scripts_path}
5. Finish
"""


def find_recent_notes(vault_path: Path, hours: int, exclude_paths: set) -> list[Path]:
    """Find .md files modified in the last `hours` hours."""
    cutoff = time.time() - (hours * 3600)
    return [
        md for md in vault_path.rglob("*.md")
        if md.stat().st_mtime > cutoff and md not in exclude_paths
    ]


def extract_note_preview(content: str, max_chars: int = 500) -> str:
    """Extract first max_chars characters, skipping frontmatter."""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:].lstrip()
    preview = content[:max_chars]
    if len(content) > max_chars:
        preview += "..."
    return preview.strip()


def format_digest_entry(filename: str, preview: str) -> str:
    """Format a single note entry for the digest."""
    return f"**{filename}**\n{preview}\n"


def build_daily_note_template(date_str: str) -> str:
    """Build a minimal daily note when one doesn't exist."""
    return f"---\ndate: {date_str}\ntags: [daily]\n---\n\n# {date_str}\n\n"


def append_digest_section(daily_note_path: Path, digest_content: str) -> None:
    """Append digest content to the daily note."""
    existing = daily_note_path.read_text(encoding="utf-8", errors="ignore")
    updated = existing.rstrip() + "\n\n" + digest_content + "\n"
    daily_note_path.write_text(updated, encoding="utf-8", newline="\n")


def startup_checks():
    if not config.VAULT_PATH.exists():
        console.print(f"[red]VAULT_PATH does not exist: {config.VAULT_PATH}[/red]")
        sys.exit(1)
    if not config.ANTHROPIC_API_KEY:
        console.print("[red]ANTHROPIC_API_KEY not set in .env[/red]")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Summarize today's vault activity to daily note.")
    parser.add_argument("--setup-scheduler", action="store_true", help="Print Windows Task Scheduler setup instructions")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.setup_scheduler:
        scripts_path = Path(__file__).parent
        console.print(SCHEDULER_INSTRUCTIONS.format(scripts_path=scripts_path))
        return

    startup_checks()

    now = datetime.now(timezone.utc)
    date_str = now.strftime(config.DATE_FORMAT)

    # Determine daily note path
    daily_dir = config.DAILY_PATH if config.DAILY_PATH and config.DAILY_PATH.exists() else config.VAULT_PATH
    daily_note_path = daily_dir / f"{date_str}.md"

    # Collect excluded paths
    exclude_paths = set()
    if config.DAILY_PATH:
        exclude_paths.update(config.DAILY_PATH.rglob("*.md"))
    if daily_note_path.exists():
        exclude_paths.add(daily_note_path)

    recent_notes = find_recent_notes(config.VAULT_PATH, hours=24, exclude_paths=exclude_paths)
    if not recent_notes:
        console.print("[yellow]No notes modified in the last 24 hours.[/yellow]")
        return

    console.print(f"Found {len(recent_notes)} recently modified notes.")

    # Build digest entries
    entries = []
    for note in sorted(recent_notes, key=lambda p: p.stat().st_mtime, reverse=True):
        content = note.read_text(encoding="utf-8", errors="ignore")
        preview = extract_note_preview(content)
        entries.append(format_digest_entry(note.name, preview))

    combined = "\n".join(entries)
    summarize_prompt = (
        "The following are recent research notes from today. "
        "Write a brief digest (3-5 sentences) summarizing the key themes and new information added today. "
        "Be concise and factual."
    )
    message = f"{combined}\n\n---\n{summarize_prompt}"

    if args.dry_run:
        console.print(f"[yellow]Dry run — {len(recent_notes)} notes, would append to {daily_note_path}[/yellow]")
        return

    with console.status("Generating digest with Claude..."):
        response_text, usage = call_claude(message, model=config.CLAUDE_MODEL_LIGHT, max_tokens=512)

    cost = estimate_cost(usage["input_tokens"], usage["output_tokens"], config.CLAUDE_MODEL_LIGHT)
    console.print(f"[dim]Tokens: {usage['input_tokens']} in / {usage['output_tokens']} out | Est. cost: ${cost:.4f}[/dim]")

    digest_content = f"## Research Digest\n\n{response_text}\n\n### Notes Updated\n\n"
    digest_content += "\n".join(f"- [[{n.stem}]]" for n in recent_notes)

    # Create daily note if missing
    if not daily_note_path.exists():
        daily_note_path.write_text(build_daily_note_template(date_str), encoding="utf-8", newline="\n")
        console.print(f"[green]Created daily note:[/green] {daily_note_path}")

    append_digest_section(daily_note_path, digest_content)
    console.print(f"[green]Digest appended to:[/green] {daily_note_path}")


if __name__ == "__main__":
    main()
```

**Step 4: Run tests**

```
pytest tests/test_daily_digest.py -v
```

**Step 5: Commit**

```bash
git add daily_digest.py tests/test_daily_digest.py
git commit -m "feat: daily_digest.py — daily vault summary"
```

---

## Phase 8: Final Verification

### Task 13: Full test suite + README

**Files:**
- Create: `README.md`

**Step 1: Run full test suite**

```
pytest tests/ -v
```

Expected: all tests pass. Fix any failures before continuing.

**Step 2: Run discover_vault.py end-to-end**

```
python discover_vault.py
```

Verify `config.py` and `.env` are generated correctly. Check:
```
python -c "import config; print(config.VAULT_PATH, config.INBOX_PATH)"
```

**Step 3: Test ingest with real URL**

```
python ingest.py "https://en.wikipedia.org/wiki/Obsidian_(software)"
```

Verify note appears in vault inbox with correct frontmatter.

**Step 4: Test claude_pipe with real note**

Find the ingested note and run:
```
python claude_pipe.py --file "C:\Users\tim\Documents\Tim's Vault\Inbox\<note>.md" --prompt summarize --model light
```

**Step 5: Test vault_lint against real vault**

```
python vault_lint.py
```

**Step 6: Test find_broken_links against real vault**

```
python find_broken_links.py
```

**Step 7: Test produce_output --list-formats**

```
python produce_output.py --list-formats
```

Expected: lists all 6 format names.

**Step 8: Write README.md**

Create a brief README with: purpose, prerequisites, quick start (discover_vault.py → pip install → usage examples for key scripts), and a link to the implementation plan.

**Step 9: Final commit**

```bash
git add README.md
git commit -m "docs: README and final verification"
```

---

## Quick Reference: Test Commands

```bash
# All tests
pytest tests/ -v

# Individual scripts
pytest tests/test_discover_vault.py -v
pytest tests/test_claude_pipe.py -v
pytest tests/test_ingest.py -v
pytest tests/test_ingest_batch.py -v
pytest tests/test_vault_lint.py -v
pytest tests/test_find_broken_links.py -v
pytest tests/test_find_related.py -v
pytest tests/test_synthesize_folder.py -v
pytest tests/test_produce_output.py -v
pytest tests/test_transcript_processor.py -v
pytest tests/test_daily_digest.py -v

# Manual smoke tests (after discover_vault.py run)
python ingest.py "https://en.wikipedia.org/wiki/Obsidian_(software)" --dry-run
python vault_lint.py
python find_broken_links.py
python produce_output.py --list-formats
python daily_digest.py --dry-run
python daily_digest.py --setup-scheduler
```
