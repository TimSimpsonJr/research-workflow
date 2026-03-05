# Research Pipeline Rework — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rework the research pipeline into a portable Claude Code plugin with batch mode, thread-pulling, tiered infrastructure (Claude Code / Ollama / SearXNG), media capture, and vault-agnostic configuration.

**Architecture:** 8-stage pipeline (resolve → search → fetch → media → summarize → classify → write → discover) with state checkpoints. All AI routes through Claude Code subagents or local Ollama — zero paid API calls. Python scripts handle I/O only.

**Tech Stack:** Python 3.10+, SQLite FTS5, pytest, yt-dlp, Whisper, Ollama (optional), SearXNG (optional)

**Design doc:** `docs/plans/2026-03-05-pipeline-rework-design.md`

---

## Phase 1: Foundation

New config system, state management, and vault index. Everything else builds on these.

### Task 1: New Config System

Replace the current `config.py` (auto-generated, reads `.env`, requires `ANTHROPIC_API_KEY`) with a JSON-based config that lives in the vault and has no API key requirement.

**Files:**
- Create: `scripts/config_manager.py`
- Test: `tests/test_config_manager.py`
- Keep (don't modify yet): `scripts/config.py` — removed in Phase 5 when setup wizard replaces it

**Step 1: Write the failing tests**

```python
# tests/test_config_manager.py
"""Tests for config_manager.py — JSON-based vault config."""

import json
import pytest
from pathlib import Path


def test_load_config_reads_json(tmp_path):
    from config_manager import load_config
    config_dir = tmp_path / ".research-workflow"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps({
        "vault_root": str(tmp_path),
        "inbox": "Inbox",
        "assets": "assets",
        "tier": "base",
    }))
    cfg = load_config(tmp_path)
    assert cfg["vault_root"] == str(tmp_path)
    assert cfg["tier"] == "base"


def test_load_config_returns_none_when_missing(tmp_path):
    from config_manager import load_config
    assert load_config(tmp_path) is None


def test_save_config_creates_directory(tmp_path):
    from config_manager import save_config
    cfg = {"vault_root": str(tmp_path), "inbox": "Inbox", "tier": "base"}
    save_config(tmp_path, cfg)
    config_file = tmp_path / ".research-workflow" / "config.json"
    assert config_file.exists()
    loaded = json.loads(config_file.read_text())
    assert loaded["tier"] == "base"


def test_save_config_overwrites_existing(tmp_path):
    from config_manager import save_config, load_config
    save_config(tmp_path, {"vault_root": str(tmp_path), "tier": "base"})
    save_config(tmp_path, {"vault_root": str(tmp_path), "tier": "mid"})
    cfg = load_config(tmp_path)
    assert cfg["tier"] == "mid"


def test_default_config_has_required_fields():
    from config_manager import default_config
    cfg = default_config("/fake/vault")
    required = ["vault_root", "inbox", "assets", "moc_pattern", "tag_format",
                 "date_format", "frontmatter_fields", "ollama_enabled",
                 "ollama_model", "searxng_url", "tier"]
    for field in required:
        assert field in cfg, f"Missing required field: {field}"


def test_get_state_dir_creates_if_missing(tmp_path):
    from config_manager import get_state_dir
    state_dir = get_state_dir(tmp_path)
    assert state_dir == tmp_path / ".research-workflow" / "state"
    assert state_dir.exists()


def test_get_assets_dir(tmp_path):
    from config_manager import load_config, save_config, get_assets_dir
    save_config(tmp_path, {"vault_root": str(tmp_path), "assets": "assets"})
    cfg = load_config(tmp_path)
    assert get_assets_dir(cfg) == Path(cfg["vault_root"]) / "assets"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'config_manager'`

**Step 3: Write minimal implementation**

```python
# scripts/config_manager.py
"""
config_manager.py — JSON-based vault configuration.

Replaces the old config.py + .env pattern. Config lives in the vault
at {vault}/.research-workflow/config.json. No API keys required.
"""

import json
from pathlib import Path

CONFIG_DIR_NAME = ".research-workflow"
CONFIG_FILE_NAME = "config.json"


def default_config(vault_root: str) -> dict:
    """Return a default config dict for a new vault."""
    return {
        "vault_root": vault_root,
        "inbox": "Inbox",
        "assets": "assets",
        "moc_pattern": "^_|MOC|Index|Hub",
        "tag_format": "list",
        "date_format": "%Y-%m-%d",
        "frontmatter_fields": ["title", "tags", "source", "created"],
        "ollama_enabled": False,
        "ollama_model": None,
        "ollama_benchmark_ms": None,
        "searxng_url": None,
        "whisper_available": False,
        "ytdlp_available": False,
        "tier": "base",
    }


def _config_path(vault_root: Path) -> Path:
    return vault_root / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def load_config(vault_root: Path) -> dict | None:
    """Load config from vault. Returns None if not found."""
    path = _config_path(vault_root)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(vault_root: Path, config: dict) -> None:
    """Save config to vault. Creates .research-workflow/ if needed."""
    path = _config_path(vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def get_state_dir(vault_root: Path) -> Path:
    """Return state directory path, creating it if needed."""
    state_dir = vault_root / CONFIG_DIR_NAME / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_assets_dir(config: dict) -> Path:
    """Return the assets directory path from config."""
    return Path(config["vault_root"]) / config["assets"]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config_manager.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add scripts/config_manager.py tests/test_config_manager.py
git commit -m "feat: add JSON-based config manager (replaces .env pattern)"
```

---

### Task 2: State Management

Checkpoint system for crash/compaction recovery. Atomic writes, per-stage tracking, resume/restart/abandon.

**Files:**
- Create: `scripts/state.py`
- Test: `tests/test_state.py`

**Step 1: Write the failing tests**

```python
# tests/test_state.py
"""Tests for state.py — pipeline state management."""

import json
import pytest
from pathlib import Path
from datetime import datetime, timezone


def test_create_run_writes_current_run(tmp_path):
    from state import create_run
    run = create_run(tmp_path, "sc-alpr", "mid")
    assert (tmp_path / "current_run.json").exists()
    assert run["run_id"] == "sc-alpr"
    assert run["stage"] == "resolve"
    assert run["tier_detected"] == "mid"


def test_create_run_fails_if_run_exists(tmp_path):
    from state import create_run
    create_run(tmp_path, "run1", "base")
    with pytest.raises(FileExistsError):
        create_run(tmp_path, "run2", "base")


def test_load_run_returns_none_when_no_run(tmp_path):
    from state import load_run
    assert load_run(tmp_path) is None


def test_load_run_returns_current_run(tmp_path):
    from state import create_run, load_run
    create_run(tmp_path, "test-run", "base")
    run = load_run(tmp_path)
    assert run["run_id"] == "test-run"


def test_update_stage_changes_stage(tmp_path):
    from state import create_run, update_stage, load_run
    create_run(tmp_path, "test", "base")
    update_stage(tmp_path, "search")
    run = load_run(tmp_path)
    assert run["stage"] == "search"


def test_save_stage_output_writes_atomically(tmp_path):
    from state import create_run, save_stage_output
    create_run(tmp_path, "test", "base")
    data = {"results": [1, 2, 3]}
    save_stage_output(tmp_path, "search_results", data)
    output_file = tmp_path / "search_results.json"
    assert output_file.exists()
    assert json.loads(output_file.read_text())["results"] == [1, 2, 3]


def test_load_stage_output_returns_none_when_missing(tmp_path):
    from state import load_stage_output
    assert load_stage_output(tmp_path, "search_results") is None


def test_load_stage_output_returns_data(tmp_path):
    from state import create_run, save_stage_output, load_stage_output
    create_run(tmp_path, "test", "base")
    save_stage_output(tmp_path, "fetch_results", {"data": "yes"})
    loaded = load_stage_output(tmp_path, "fetch_results")
    assert loaded["data"] == "yes"


def test_append_written_note(tmp_path):
    from state import create_run, append_written_note, load_stage_output
    create_run(tmp_path, "test", "base")
    append_written_note(tmp_path, "Greenville ALPR", "Projects/Surveillance/Greenville.md", "sonnet")
    append_written_note(tmp_path, "Charleston ALPR", "Projects/Surveillance/Charleston.md", "sonnet")
    written = load_stage_output(tmp_path, "written_notes")
    assert len(written["completed"]) == 2
    assert written["completed"][0]["topic"] == "Greenville ALPR"


def test_abandon_run_archives_state(tmp_path):
    from state import create_run, save_stage_output, abandon_run, load_run
    create_run(tmp_path, "old-run", "base")
    save_stage_output(tmp_path, "search_results", {"data": True})
    abandon_run(tmp_path)
    assert load_run(tmp_path) is None
    history_dir = tmp_path / "history" / "old-run"
    assert history_dir.exists()
    assert (history_dir / "current_run.json").exists()
    assert (history_dir / "search_results.json").exists()


def test_complete_run_archives_state(tmp_path):
    from state import create_run, complete_run, load_run
    create_run(tmp_path, "done-run", "base")
    complete_run(tmp_path)
    assert load_run(tmp_path) is None
    history_dir = tmp_path / "history" / "done-run"
    assert history_dir.exists()


def test_is_stale_run(tmp_path):
    from state import create_run, is_stale_run
    create_run(tmp_path, "test", "base")
    assert is_stale_run(tmp_path, max_age_hours=24) is False
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'state'`

**Step 3: Write minimal implementation**

```python
# scripts/state.py
"""
state.py — Pipeline state management with crash recovery.

Tracks pipeline progress via JSON checkpoints. Supports resume,
restart, and abandon flows. State lives in the vault at
{vault}/.research-workflow/state/.
"""

import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

CURRENT_RUN_FILE = "current_run.json"


def _atomic_write(path: Path, data: dict) -> None:
    """Write JSON atomically via temp file + rename."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def create_run(state_dir: Path, run_id: str, tier: str) -> dict:
    """Create a new run. Raises FileExistsError if a run is active."""
    run_file = state_dir / CURRENT_RUN_FILE
    if run_file.exists():
        raise FileExistsError(f"Active run exists: {run_file}")
    state_dir.mkdir(parents=True, exist_ok=True)
    run = {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "stage": "resolve",
        "stage_progress": {},
        "tier_detected": tier,
        "plan_approved": False,
    }
    _atomic_write(run_file, run)
    return run


def load_run(state_dir: Path) -> dict | None:
    """Load current run, or None if no active run."""
    run_file = state_dir / CURRENT_RUN_FILE
    if not run_file.exists():
        return None
    return json.loads(run_file.read_text(encoding="utf-8"))


def update_stage(state_dir: Path, stage: str, progress: dict | None = None) -> None:
    """Update the current run's stage and optional progress."""
    run = load_run(state_dir)
    if run is None:
        raise RuntimeError("No active run")
    run["stage"] = stage
    if progress is not None:
        run["stage_progress"] = progress
    _atomic_write(state_dir / CURRENT_RUN_FILE, run)


def save_stage_output(state_dir: Path, name: str, data: dict) -> None:
    """Save a stage's output file atomically."""
    _atomic_write(state_dir / f"{name}.json", data)


def load_stage_output(state_dir: Path, name: str) -> dict | None:
    """Load a stage's output file, or None if missing."""
    path = state_dir / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def append_written_note(state_dir: Path, topic: str, path: str, model: str) -> None:
    """Append a completed note to written_notes.json."""
    written = load_stage_output(state_dir, "written_notes") or {"completed": []}
    written["completed"].append({
        "topic": topic,
        "path": path,
        "model": model,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })
    save_stage_output(state_dir, "written_notes", written)


def _archive_run(state_dir: Path) -> None:
    """Move all state files to history/{run_id}/."""
    run = load_run(state_dir)
    if run is None:
        return
    history_dir = state_dir / "history" / run["run_id"]
    history_dir.mkdir(parents=True, exist_ok=True)
    for f in state_dir.glob("*.json"):
        shutil.move(str(f), str(history_dir / f.name))


def abandon_run(state_dir: Path) -> None:
    """Archive incomplete run to history."""
    _archive_run(state_dir)


def complete_run(state_dir: Path) -> None:
    """Archive completed run to history."""
    run = load_run(state_dir)
    if run:
        run["completed_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_write(state_dir / CURRENT_RUN_FILE, run)
    _archive_run(state_dir)


def is_stale_run(state_dir: Path, max_age_hours: int = 24) -> bool:
    """Check if the current run is older than max_age_hours."""
    run = load_run(state_dir)
    if run is None:
        return False
    started = datetime.fromisoformat(run["started_at"])
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - started > timedelta(hours=max_age_hours)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_state.py -v`
Expected: All 12 tests PASS

**Step 5: Commit**

```bash
git add scripts/state.py tests/test_state.py
git commit -m "feat: add pipeline state management with crash recovery"
```

---

### Task 3: Vault Index (SQLite FTS5)

Replaces glob-all-markdown with a fast, incrementally-updated search index.

**Files:**
- Create: `scripts/vault_index.py`
- Test: `tests/test_vault_index.py`

**Step 1: Write the failing tests**

```python
# tests/test_vault_index.py
"""Tests for vault_index.py — SQLite FTS5 vault index."""

import pytest
from pathlib import Path


def _create_note(vault: Path, rel_path: str, content: str, frontmatter: str = "") -> Path:
    """Helper: create a markdown note in the test vault."""
    full = vault / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    text = f"---\n{frontmatter}\n---\n{content}" if frontmatter else content
    full.write_text(text, encoding="utf-8")
    return full


def test_build_index_creates_db(tmp_path):
    from vault_index import build_index
    _create_note(tmp_path, "note1.md", "Some content about ALPR")
    db_path = build_index(tmp_path)
    assert db_path.exists()
    assert db_path.name == "vault_index.db"


def test_build_index_indexes_all_md_files(tmp_path):
    from vault_index import build_index, search
    _create_note(tmp_path, "Projects/note1.md", "ALPR surveillance")
    _create_note(tmp_path, "Projects/note2.md", "City council meeting")
    _create_note(tmp_path, "Inbox/note3.md", "Draft note")
    build_index(tmp_path)
    results = search(tmp_path, "surveillance")
    assert len(results) == 1
    assert "note1.md" in results[0]["path"]


def test_build_index_extracts_frontmatter_tags(tmp_path):
    from vault_index import build_index, search
    _create_note(tmp_path, "note.md", "Content here",
                 frontmatter="title: Test Note\ntags: [research, surveillance]")
    build_index(tmp_path)
    results = search(tmp_path, "surveillance")
    assert len(results) == 1
    assert "surveillance" in results[0]["tags"]


def test_search_returns_empty_for_no_match(tmp_path):
    from vault_index import build_index, search
    _create_note(tmp_path, "note.md", "Nothing relevant here")
    build_index(tmp_path)
    results = search(tmp_path, "quantum physics")
    assert len(results) == 0


def test_update_index_only_reindexes_changed_files(tmp_path):
    from vault_index import build_index, update_index, search
    _create_note(tmp_path, "note1.md", "Original content")
    build_index(tmp_path)
    # Modify one file, add another
    _create_note(tmp_path, "note1.md", "Updated content about ALPR")
    _create_note(tmp_path, "note2.md", "New note about surveillance")
    stats = update_index(tmp_path)
    assert stats["updated"] >= 1
    assert stats["added"] >= 1
    results = search(tmp_path, "ALPR")
    assert len(results) == 1


def test_search_by_title(tmp_path):
    from vault_index import build_index, search
    _create_note(tmp_path, "Greenville ALPR.md", "Content",
                 frontmatter="title: Greenville County ALPR Surveillance")
    build_index(tmp_path)
    results = search(tmp_path, "Greenville")
    assert len(results) == 1


def test_list_all_notes(tmp_path):
    from vault_index import build_index, list_notes
    _create_note(tmp_path, "a.md", "Note A")
    _create_note(tmp_path, "b.md", "Note B")
    _create_note(tmp_path, "sub/c.md", "Note C")
    build_index(tmp_path)
    notes = list_notes(tmp_path)
    assert len(notes) == 3


def test_index_skips_research_workflow_dir(tmp_path):
    from vault_index import build_index, list_notes
    _create_note(tmp_path, "real-note.md", "Keep me")
    _create_note(tmp_path, ".research-workflow/config.json", '{"test": true}')
    _create_note(tmp_path, ".research-workflow/state/run.json", '{}')
    build_index(tmp_path)
    notes = list_notes(tmp_path)
    paths = [n["path"] for n in notes]
    assert any("real-note" in p for p in paths)
    assert not any(".research-workflow" in p for p in paths)


def test_note_exists_by_title(tmp_path):
    from vault_index import build_index, note_exists
    _create_note(tmp_path, "ALPR.md", "Content",
                 frontmatter="title: Automatic License Plate Readers")
    build_index(tmp_path)
    assert note_exists(tmp_path, "Automatic License Plate Readers") is True
    assert note_exists(tmp_path, "Quantum Computing") is False
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_vault_index.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vault_index'`

**Step 3: Write minimal implementation**

```python
# scripts/vault_index.py
"""
vault_index.py — SQLite FTS5 index for the Obsidian vault.

Provides fast full-text search over vault notes. Built incrementally
by checking file mtimes. Used by classify, write, and thread-discover
stages instead of globbing the entire vault.
"""

import re
import sqlite3
from pathlib import Path

CONFIG_DIR = ".research-workflow"
DB_NAME = "vault_index.db"
EXCERPT_LENGTH = 500


def _db_path(vault_root: Path) -> Path:
    return vault_root / CONFIG_DIR / DB_NAME


def _connect(vault_root: Path) -> sqlite3.Connection:
    db = _db_path(vault_root)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    return conn


def _init_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS notes (
            path TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '',
            excerpt TEXT NOT NULL DEFAULT '',
            mtime REAL NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
            title, tags, excerpt, content=notes, content_rowid=rowid
        );
        CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
            INSERT INTO notes_fts(rowid, title, tags, excerpt)
            VALUES (new.rowid, new.title, new.tags, new.excerpt);
        END;
        CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
            INSERT INTO notes_fts(notes_fts, rowid, title, tags, excerpt)
            VALUES ('delete', old.rowid, old.title, old.tags, old.excerpt);
        END;
        CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
            INSERT INTO notes_fts(notes_fts, rowid, title, tags, excerpt)
            VALUES ('delete', old.rowid, old.title, old.tags, old.excerpt);
            INSERT INTO notes_fts(rowid, title, tags, excerpt)
            VALUES (new.rowid, new.title, new.tags, new.excerpt);
        END;
    """)


def _parse_frontmatter(text: str) -> tuple[str, str]:
    """Extract title and tags from YAML frontmatter. Returns (title, tags_csv)."""
    title = ""
    tags = ""
    fm_match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return title, tags
    fm = fm_match.group(1)
    for line in fm.splitlines():
        if line.startswith("title:"):
            title = line.split(":", 1)[1].strip().strip("'\"")
        if line.startswith("tags:"):
            # Handle both [a, b] and multi-line - a formats
            rest = line.split(":", 1)[1].strip()
            if rest.startswith("["):
                tags = rest.strip("[]").replace(",", ", ")
            else:
                tags = rest
    return title, tags


def _body_text(text: str) -> str:
    """Strip frontmatter, return body text."""
    stripped = re.sub(r"^---\n.*?\n---\n?", "", text, count=1, flags=re.DOTALL)
    return stripped.strip()


def _index_file(conn: sqlite3.Connection, vault_root: Path, rel_path: str, mtime: float) -> None:
    """Index or update a single file."""
    full = vault_root / rel_path
    try:
        text = full.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    title, tags = _parse_frontmatter(text)
    if not title:
        title = full.stem
    body = _body_text(text)
    excerpt = body[:EXCERPT_LENGTH]
    conn.execute(
        "INSERT OR REPLACE INTO notes (path, title, tags, excerpt, mtime) VALUES (?, ?, ?, ?, ?)",
        (rel_path, title, tags, excerpt, mtime),
    )


def _should_skip(rel_path: str) -> bool:
    """Skip hidden dirs, .research-workflow, and non-.md files."""
    parts = Path(rel_path).parts
    for part in parts:
        if part.startswith("."):
            return True
    return not rel_path.endswith(".md")


def build_index(vault_root: Path) -> Path:
    """Build the full index from scratch. Returns the db path."""
    db = _db_path(vault_root)
    if db.exists():
        db.unlink()
    conn = _connect(vault_root)
    _init_tables(conn)
    for md in vault_root.rglob("*.md"):
        rel = str(md.relative_to(vault_root)).replace("\\", "/")
        if _should_skip(rel):
            continue
        _index_file(conn, vault_root, rel, md.stat().st_mtime)
    conn.commit()
    conn.close()
    return db


def update_index(vault_root: Path) -> dict:
    """Incrementally update the index. Returns stats dict."""
    conn = _connect(vault_root)
    _init_tables(conn)
    stats = {"added": 0, "updated": 0, "removed": 0}

    # Get current indexed files
    indexed = {}
    for row in conn.execute("SELECT path, mtime FROM notes"):
        indexed[row["path"]] = row["mtime"]

    # Scan vault
    on_disk = set()
    for md in vault_root.rglob("*.md"):
        rel = str(md.relative_to(vault_root)).replace("\\", "/")
        if _should_skip(rel):
            continue
        on_disk.add(rel)
        mtime = md.stat().st_mtime
        if rel not in indexed:
            _index_file(conn, vault_root, rel, mtime)
            stats["added"] += 1
        elif mtime > indexed[rel]:
            _index_file(conn, vault_root, rel, mtime)
            stats["updated"] += 1

    # Remove deleted files
    for path in indexed:
        if path not in on_disk:
            conn.execute("DELETE FROM notes WHERE path = ?", (path,))
            stats["removed"] += 1

    conn.commit()
    conn.close()
    return stats


def search(vault_root: Path, query: str, limit: int = 20) -> list[dict]:
    """Full-text search. Returns list of {path, title, tags, excerpt, rank}."""
    conn = _connect(vault_root)
    rows = conn.execute(
        """SELECT n.path, n.title, n.tags, n.excerpt, rank
           FROM notes_fts f
           JOIN notes n ON n.rowid = f.rowid
           WHERE notes_fts MATCH ?
           ORDER BY rank
           LIMIT ?""",
        (query, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_notes(vault_root: Path) -> list[dict]:
    """List all indexed notes."""
    conn = _connect(vault_root)
    rows = conn.execute("SELECT path, title, tags FROM notes ORDER BY path").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def note_exists(vault_root: Path, title: str) -> bool:
    """Check if a note with this title exists in the index."""
    conn = _connect(vault_root)
    row = conn.execute(
        "SELECT 1 FROM notes WHERE title = ? LIMIT 1", (title,)
    ).fetchone()
    conn.close()
    return row is not None
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_vault_index.py -v`
Expected: All 9 tests PASS

**Step 5: Commit**

```bash
git add scripts/vault_index.py tests/test_vault_index.py
git commit -m "feat: add SQLite FTS5 vault index (replaces glob-all-markdown)"
```

---

### Task 4: Tier Detection

Detect available infrastructure: Ollama, SearXNG, yt-dlp, Whisper. Hardware-aware recommendations.

**Files:**
- Create: `scripts/detect_tier.py`
- Test: `tests/test_detect_tier.py`

**Step 1: Write the failing tests**

```python
# tests/test_detect_tier.py
"""Tests for detect_tier.py — infrastructure detection."""

import pytest
from unittest.mock import patch, MagicMock


def test_check_ollama_not_installed():
    from detect_tier import check_ollama
    with patch("detect_tier.shutil.which", return_value=None):
        result = check_ollama()
    assert result["installed"] is False
    assert result["recommended_model"] is None


def test_check_ollama_installed_but_not_running():
    from detect_tier import check_ollama
    with patch("detect_tier.shutil.which", return_value="/usr/bin/ollama"):
        with patch("detect_tier.subprocess.run", side_effect=Exception("connection refused")):
            result = check_ollama()
    assert result["installed"] is True
    assert result["running"] is False


def test_recommend_model_low_ram():
    from detect_tier import recommend_model
    result = recommend_model(ram_gb=6, vram_gb=0)
    assert result["recommendation"] == "skip"


def test_recommend_model_medium_ram():
    from detect_tier import recommend_model
    result = recommend_model(ram_gb=16, vram_gb=0)
    assert result["recommendation"] == "use"
    assert "7b" in result["model"] or "8b" in result["model"]


def test_recommend_model_high_vram():
    from detect_tier import recommend_model
    result = recommend_model(ram_gb=32, vram_gb=12)
    assert result["recommendation"] == "use"
    assert "14b" in result["model"] or "32b" in result["model"]


def test_check_searxng_not_available():
    from detect_tier import check_searxng
    result = check_searxng(url=None)
    assert result["available"] is False


def test_check_searxng_url_unreachable():
    from detect_tier import check_searxng
    with patch("detect_tier.requests.get", side_effect=Exception("connection refused")):
        result = check_searxng(url="http://localhost:8888")
    assert result["available"] is False


def test_check_ytdlp_installed():
    from detect_tier import check_ytdlp
    with patch("detect_tier.shutil.which", return_value="/usr/bin/yt-dlp"):
        result = check_ytdlp()
    assert result["installed"] is True


def test_check_ytdlp_not_installed():
    from detect_tier import check_ytdlp
    with patch("detect_tier.shutil.which", return_value=None):
        result = check_ytdlp()
    assert result["installed"] is False


def test_detect_tier_base():
    from detect_tier import detect_tier
    with patch("detect_tier.check_ollama", return_value={"installed": False, "running": False, "recommended_model": None}):
        with patch("detect_tier.check_searxng", return_value={"available": False}):
            tier = detect_tier(searxng_url=None)
    assert tier == "base"


def test_detect_tier_mid():
    from detect_tier import detect_tier
    with patch("detect_tier.check_ollama", return_value={"installed": True, "running": True, "recommended_model": "qwen2.5:14b"}):
        with patch("detect_tier.check_searxng", return_value={"available": False}):
            tier = detect_tier(searxng_url=None)
    assert tier == "mid"


def test_detect_tier_full():
    from detect_tier import detect_tier
    with patch("detect_tier.check_ollama", return_value={"installed": True, "running": True, "recommended_model": "qwen2.5:14b"}):
        with patch("detect_tier.check_searxng", return_value={"available": True}):
            tier = detect_tier(searxng_url="http://localhost:8888")
    assert tier == "full"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_detect_tier.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# scripts/detect_tier.py
"""
detect_tier.py — Detect available infrastructure and recommend tier.

Checks for Ollama, SearXNG, yt-dlp, Whisper. Provides hardware-aware
model recommendations for Ollama.
"""

import shutil
import subprocess
import platform
from pathlib import Path

import requests


def check_ollama() -> dict:
    """Check if Ollama is installed and running."""
    result = {"installed": False, "running": False, "recommended_model": None, "models": []}
    if shutil.which("ollama") is None:
        return result
    result["installed"] = True
    try:
        proc = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=10
        )
        if proc.returncode == 0:
            result["running"] = True
            lines = proc.stdout.strip().splitlines()[1:]  # skip header
            result["models"] = [line.split()[0] for line in lines if line.strip()]
    except Exception:
        result["running"] = False
    return result


def recommend_model(ram_gb: float, vram_gb: float) -> dict:
    """Recommend an Ollama model based on hardware."""
    if ram_gb < 8 and vram_gb < 4:
        return {"recommendation": "skip", "model": None,
                "reason": "Insufficient RAM/VRAM for useful local models"}
    if vram_gb >= 12:
        return {"recommendation": "use", "model": "qwen2.5:14b",
                "reason": f"Strong fit — {vram_gb}GB VRAM handles 14B models well"}
    if vram_gb >= 6:
        return {"recommendation": "use", "model": "qwen2.5:7b",
                "reason": f"{vram_gb}GB VRAM suits 7B models"}
    if ram_gb >= 16:
        return {"recommendation": "use", "model": "qwen2.5:7b",
                "reason": f"{ram_gb}GB RAM can run 7B models on CPU (slower than GPU)"}
    if ram_gb >= 8:
        return {"recommendation": "use", "model": "qwen2.5:7b",
                "reason": f"{ram_gb}GB RAM is minimal — expect slow inference"}
    return {"recommendation": "skip", "model": None,
            "reason": "Hardware below minimum for useful local inference"}


def check_searxng(url: str | None) -> dict:
    """Check if SearXNG is reachable at the given URL."""
    if not url:
        return {"available": False, "url": None}
    try:
        resp = requests.get(f"{url.rstrip('/')}/healthz", timeout=5)
        return {"available": resp.status_code == 200, "url": url}
    except Exception:
        return {"available": False, "url": url}


def check_ytdlp() -> dict:
    """Check if yt-dlp is installed."""
    return {"installed": shutil.which("yt-dlp") is not None}


def check_whisper() -> dict:
    """Check if Whisper is available (via whisper CLI or Python module)."""
    if shutil.which("whisper") is not None:
        return {"installed": True, "backend": "cli"}
    try:
        import whisper as _w  # noqa: F401
        return {"installed": True, "backend": "python"}
    except ImportError:
        return {"installed": False, "backend": None}


def get_platform_info() -> dict:
    """Get basic platform info for install recommendations."""
    return {
        "os": platform.system().lower(),
        "arch": platform.machine(),
        "is_wsl": "microsoft" in platform.uname().release.lower()
                  if platform.system() == "Linux" else False,
    }


def detect_tier(searxng_url: str | None) -> str:
    """Detect the highest available tier."""
    ollama = check_ollama()
    searxng = check_searxng(searxng_url)
    if ollama.get("running") and searxng.get("available"):
        return "full"
    if ollama.get("running"):
        return "mid"
    return "base"
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_detect_tier.py -v`
Expected: All 12 tests PASS

**Step 5: Commit**

```bash
git add scripts/detect_tier.py tests/test_detect_tier.py
git commit -m "feat: add tier detection (Ollama, SearXNG, yt-dlp, Whisper)"
```

---

## Phase 2: Core Pipeline Scripts

The Python I/O scripts that form the pipeline backbone. These are called by Claude Code skills via Bash — they do no AI work themselves (except Ollama calls when available).

### Task 5: Parallel Fetch

Upgrade `fetch_and_clean.py` from sequential to parallel async fetching.

**Files:**
- Modify: `scripts/fetch_and_clean.py` — add `process_urls_parallel()` using `concurrent.futures`
- Modify: `tests/test_fetch_and_clean.py` — add parallel fetch tests

**Step 1: Write the failing tests**

Add to `tests/test_fetch_and_clean.py`:

```python
def test_process_urls_parallel_fetches_concurrently(tmp_path):
    from fetch_and_clean import process_urls_parallel
    urls = [{"url": f"https://example.com/{i}"} for i in range(5)]
    with patch("fetch_and_clean.fetch_url", return_value=("content", "title", "jina")):
        fetched, failed = process_urls_parallel(
            urls=urls, cache_dir=tmp_path, ttl_days=7,
            jina_api_key=None, max_workers=3,
        )
    assert len(fetched) == 5
    assert len(failed) == 0


def test_process_urls_parallel_handles_mixed_success_failure(tmp_path):
    from fetch_and_clean import process_urls_parallel
    urls = [{"url": "https://good.com"}, {"url": "https://bad.com"}]

    def mock_fetch(url, key=None):
        if "bad" in url:
            raise RuntimeError("fail")
        return ("content", "title", "jina")

    with patch("fetch_and_clean.fetch_url", side_effect=mock_fetch):
        fetched, failed = process_urls_parallel(
            urls=urls, cache_dir=tmp_path, ttl_days=7,
            jina_api_key=None, max_workers=2,
        )
    assert len(fetched) == 1
    assert len(failed) == 1


def test_process_urls_parallel_respects_cache(tmp_path):
    from fetch_and_clean import process_urls_parallel, save_cache, url_cache_key
    from datetime import datetime, timezone
    url = "https://cached.com/article"
    cache_key = url_cache_key(url)
    save_cache(tmp_path, cache_key, {
        "url": url, "content": "cached", "title": "Cached",
        "fetch_method": "jina", "fetched_at": datetime.now(timezone.utc).isoformat(),
    })
    with patch("fetch_and_clean.fetch_url") as mock:
        fetched, _ = process_urls_parallel(
            urls=[{"url": url}], cache_dir=tmp_path, ttl_days=7,
            jina_api_key=None, max_workers=2,
        )
    mock.assert_not_called()
    assert fetched[0]["cache_hit"] is True
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fetch_and_clean.py::test_process_urls_parallel_fetches_concurrently -v`
Expected: FAIL — `ImportError: cannot import name 'process_urls_parallel'`

**Step 3: Add `process_urls_parallel` to `fetch_and_clean.py`**

Add after the existing `process_urls` function:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed


def _fetch_single(url_item: dict, cache_dir: Path, ttl_days: int,
                  jina_api_key: str | None) -> tuple[dict | None, dict | None]:
    """Fetch a single URL. Returns (fetched_dict, None) or (None, failed_dict)."""
    url = url_item["url"]
    cache_key = url_cache_key(url)

    cached = load_cache(cache_dir, cache_key)
    if cached is not None and not is_expired(cached, ttl_days):
        truncated = cached["content"][:MAX_CONTENT_CHARS]
        return {
            "url": url, "title": cached.get("title", ""),
            "content": truncated, "fetch_method": cached.get("fetch_method", "cached"),
            "cache_hit": True, "fetched_at": cached["fetched_at"],
            "word_count": len(truncated.split()),
        }, None

    try:
        content, title, method = fetch_url(url, jina_api_key)
        content = content[:MAX_CONTENT_CHARS]
        now = datetime.now(timezone.utc).isoformat()
        save_cache(cache_dir, cache_key, {
            "url": url, "title": title, "content": content,
            "fetch_method": method, "fetched_at": now,
        })
        return {
            "url": url, "title": title, "content": content,
            "fetch_method": method, "cache_hit": False,
            "fetched_at": now, "word_count": len(content.split()),
        }, None
    except Exception as exc:
        return None, {"url": url, "error": str(exc), "attempts": ["jina", "wayback"]}


def process_urls_parallel(
    urls: list[dict], cache_dir: Path, ttl_days: int,
    jina_api_key: str | None, max_workers: int = 3,
) -> tuple[list[dict], list[dict]]:
    """Fetch URLs in parallel using ThreadPoolExecutor."""
    fetched: list[dict] = []
    failed: list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_fetch_single, item, cache_dir, ttl_days, jina_api_key): item
            for item in urls
        }
        for future in as_completed(futures):
            result, error = future.result()
            if result:
                fetched.append(result)
            if error:
                failed.append(error)

    return fetched, failed
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fetch_and_clean.py -v`
Expected: All tests PASS (old sequential + new parallel)

**Step 5: Commit**

```bash
git add scripts/fetch_and_clean.py tests/test_fetch_and_clean.py
git commit -m "feat: add parallel URL fetching (process_urls_parallel)"
```

---

### Task 6: Media Downloader

Download images, PDFs, and video/audio from fetched content into vault assets.

**Files:**
- Create: `scripts/fetch_media.py`
- Test: `tests/test_fetch_media.py`

**Step 1: Write the failing tests**

```python
# tests/test_fetch_media.py
"""Tests for fetch_media.py — media download and asset management."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


ALLOWED_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf"}


def test_extract_media_refs_finds_images():
    from fetch_media import extract_media_refs
    content = "Some text ![img](https://example.com/photo.jpg) and more"
    refs = extract_media_refs(content)
    assert len(refs) == 1
    assert refs[0]["url"] == "https://example.com/photo.jpg"
    assert refs[0]["type"] == "image"


def test_extract_media_refs_finds_pdfs():
    from fetch_media import extract_media_refs
    content = "See the [report](https://example.com/report.pdf) for details"
    refs = extract_media_refs(content)
    assert len(refs) == 1
    assert refs[0]["type"] == "document"


def test_extract_media_refs_finds_youtube():
    from fetch_media import extract_media_refs
    content = "Watch [video](https://www.youtube.com/watch?v=abc123)"
    refs = extract_media_refs(content)
    assert len(refs) == 1
    assert refs[0]["type"] == "video"


def test_extract_media_refs_skips_blocked_types():
    from fetch_media import extract_media_refs
    content = "Download [file](https://example.com/malware.exe)"
    refs = extract_media_refs(content)
    assert len(refs) == 0


def test_download_media_saves_file_and_meta(tmp_path):
    from fetch_media import download_media_file
    mock_resp = MagicMock()
    mock_resp.headers = {"content-length": "1000", "content-type": "image/png"}
    mock_resp.iter_content = MagicMock(return_value=[b"fake image data"])
    mock_resp.raise_for_status = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("fetch_media.requests.get", return_value=mock_resp):
        result = download_media_file(
            url="https://example.com/photo.png",
            assets_dir=tmp_path / "assets",
            topic_slug="test-topic",
            run_id="test-run",
        )
    assert result is not None
    assert (tmp_path / "assets" / "test-topic" / "photo.png").exists()
    meta_file = tmp_path / "assets" / "test-topic" / "photo.png.meta"
    assert meta_file.exists()
    meta = json.loads(meta_file.read_text())
    assert meta["source_url"] == "https://example.com/photo.png"


def test_download_media_skips_oversized(tmp_path):
    from fetch_media import download_media_file
    mock_resp = MagicMock()
    mock_resp.headers = {"content-length": str(20 * 1024 * 1024), "content-type": "image/png"}
    mock_resp.raise_for_status = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("fetch_media.requests.get", return_value=mock_resp):
        result = download_media_file(
            url="https://example.com/huge.png",
            assets_dir=tmp_path / "assets",
            topic_slug="test",
            run_id="test-run",
            max_size_bytes=10 * 1024 * 1024,
        )
    assert result is None


def test_rewrite_media_refs_updates_content():
    from fetch_media import rewrite_media_refs
    content = "See ![img](https://example.com/photo.png) here"
    manifest = [{"url": "https://example.com/photo.png",
                 "local_path": "assets/topic/photo.png"}]
    updated = rewrite_media_refs(content, manifest)
    assert "![[assets/topic/photo.png]]" in updated
    assert "https://example.com/photo.png" not in updated
```

**Step 2: Run tests, verify failure, implement, verify pass, commit**

Run: `pytest tests/test_fetch_media.py -v`

Implementation: `scripts/fetch_media.py` — regex-based media URL extraction, requests-based download with size check, `.meta` sidecar writing, content rewriting for Obsidian embeds.

```bash
git add scripts/fetch_media.py tests/test_fetch_media.py
git commit -m "feat: add media downloader with asset management"
```

---

### Task 7: Summarize Script

Distill fetched articles to ~500 tokens via Ollama (or produce file-based output for Claude Code to summarize).

**Files:**
- Create: `scripts/summarize.py`
- Create: `scripts/prompts/summarize_fetch.txt`
- Test: `tests/test_summarize.py`

**Step 1: Write the failing tests**

```python
# tests/test_summarize.py
"""Tests for summarize.py — article summarization via Ollama or file output."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_summarize_single_with_ollama():
    from summarize import summarize_article
    mock_response = {"message": {"content": json.dumps({
        "summary": "ALPR cameras capture plates automatically.",
        "source_type": "journalism",
        "key_entities": ["Flock Safety"],
        "key_claims": ["422M reads in 2024"],
    })}}
    with patch("summarize.requests.post", return_value=MagicMock(
        json=MagicMock(return_value=mock_response), status_code=200,
        raise_for_status=MagicMock()
    )):
        result = summarize_article(
            content="Long article about ALPR surveillance...",
            title="ALPR Report",
            url="https://example.com",
            model="qwen2.5:14b",
        )
    assert "summary" in result
    assert isinstance(result["key_entities"], list)


def test_summarize_batch_writes_output(tmp_path):
    from summarize import summarize_batch
    fetch_results = {
        "fetched": [
            {"url": "https://a.com", "title": "Article A", "content": "Content A about ALPR"},
            {"url": "https://b.com", "title": "Article B", "content": "Content B about surveillance"},
        ]
    }
    mock_response = {"message": {"content": json.dumps({
        "summary": "Summary", "source_type": "journalism",
        "key_entities": [], "key_claims": [],
    })}}
    with patch("summarize.requests.post", return_value=MagicMock(
        json=MagicMock(return_value=mock_response), status_code=200,
        raise_for_status=MagicMock()
    )):
        summaries = summarize_batch(fetch_results, model="qwen2.5:14b")
    assert len(summaries) == 2


def test_prepare_for_claude_code_writes_files(tmp_path):
    from summarize import prepare_for_claude_code
    fetch_results = {
        "fetched": [
            {"url": "https://a.com", "title": "A", "content": "Content A"},
        ]
    }
    output = prepare_for_claude_code(fetch_results, tmp_path)
    assert len(output) == 1
    assert (tmp_path / output[0]["file"]).exists()


def test_summarize_article_handles_ollama_failure():
    from summarize import summarize_article
    with patch("summarize.requests.post", side_effect=Exception("connection refused")):
        result = summarize_article(
            content="Content", title="Title", url="https://x.com",
            model="qwen2.5:14b",
        )
    assert result is None
```

**Step 2: Run tests, verify failure, implement, verify pass, commit**

Implementation notes:
- `summarize_article()` calls Ollama's `/api/generate` endpoint with the prompt from `summarize_fetch.txt`
- `summarize_batch()` runs multiple articles through Ollama
- `prepare_for_claude_code()` writes individual article files to a temp dir for Haiku subagents to summarize (used when Ollama is not available)
- Ollama failures return None — the pipeline continues with unsummarized content

```bash
git add scripts/summarize.py scripts/prompts/summarize_fetch.txt tests/test_summarize.py
git commit -m "feat: add summarize step (Ollama with Claude Code fallback)"
```

---

### Task 8: Local File Extraction

Extract text from .pdf, .docx, .doc, .mp3 files for the local ingestion path.

**Files:**
- Create: `scripts/extract_local.py` (refactored from `ingest_local.py`, strips vault-writing logic — pure extraction only)
- Test: `tests/test_extract_local.py`

**Step 1: Write the failing tests**

```python
# tests/test_extract_local.py
"""Tests for extract_local.py — local file text extraction."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_extract_pdf(tmp_path):
    from extract_local import extract_file
    pdf_path = tmp_path / "test.pdf"
    # Create a minimal PDF mock
    with patch("extract_local.fitz") as mock_fitz:
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Page 1 content about surveillance"
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_fitz.open.return_value = mock_doc
        pdf_path.write_bytes(b"fake pdf")
        result = extract_file(pdf_path)
    assert result["content"] == "Page 1 content about surveillance"
    assert result["file_type"] == "pdf"


def test_extract_docx(tmp_path):
    from extract_local import extract_file
    docx_path = tmp_path / "test.docx"
    with patch("extract_local.docx") as mock_docx:
        mock_doc = MagicMock()
        mock_doc.paragraphs = [MagicMock(text="Paragraph one"), MagicMock(text="Paragraph two")]
        mock_docx.Document.return_value = mock_doc
        docx_path.write_bytes(b"fake docx")
        result = extract_file(docx_path)
    assert "Paragraph one" in result["content"]
    assert result["file_type"] == "docx"


def test_extract_unsupported_type(tmp_path):
    from extract_local import extract_file
    bad_path = tmp_path / "test.xyz"
    bad_path.write_text("content")
    result = extract_file(bad_path)
    assert result is None


def test_extract_folder_processes_all_supported(tmp_path):
    from extract_local import extract_folder
    (tmp_path / "a.pdf").write_bytes(b"fake")
    (tmp_path / "b.docx").write_bytes(b"fake")
    (tmp_path / "c.txt").write_text("ignored")
    with patch("extract_local.extract_file") as mock_extract:
        mock_extract.return_value = {"content": "text", "file_type": "pdf", "title": "test"}
        results = extract_folder(tmp_path, recursive=False)
    # Should attempt a.pdf and b.docx, skip c.txt
    assert mock_extract.call_count == 2


def test_extract_folder_recursive(tmp_path):
    from extract_local import extract_folder
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "a.pdf").write_bytes(b"fake")
    (sub / "b.pdf").write_bytes(b"fake")
    with patch("extract_local.extract_file") as mock_extract:
        mock_extract.return_value = {"content": "text", "file_type": "pdf", "title": "test"}
        results = extract_folder(tmp_path, recursive=True)
    assert mock_extract.call_count == 2
```

**Step 2: Run tests, verify failure, implement, verify pass, commit**

Implementation: Refactor text extraction logic from existing `ingest_local.py` into pure functions. No vault writing, no frontmatter — just `file → {content, title, file_type, source_path}`.

```bash
git add scripts/extract_local.py tests/test_extract_local.py
git commit -m "feat: add extract_local.py (pure text extraction from pdf/docx/doc)"
```

---

## Phase 3: Skills & Agents

The Claude Code skill and agent definitions. These are markdown files that define how Claude Code orchestrates the pipeline.

### Task 9: Plugin Manifest

Create `plugin.json` so this repo can be used as a Claude Code plugin.

**Files:**
- Create: `plugin.json`

**Step 1: Write plugin.json**

```json
{
  "name": "research-workflow",
  "description": "Deep research pipeline for Obsidian vaults. Batch research, thread-pulling, media capture, vault-aware classification.",
  "version": "2.0.0",
  "skills": [
    "skills/research/SKILL.md",
    "skills/research-setup/SKILL.md"
  ],
  "agents": [
    "agents/topic-resolver.md",
    "agents/search-agent.md",
    "agents/classify-agent.md",
    "agents/thread-discoverer.md"
  ]
}
```

**Step 2: Commit**

```bash
git add plugin.json
git commit -m "feat: add plugin.json manifest for Claude Code plugin distribution"
```

---

### Task 10: Agent Definitions

Write the agent markdown files that define Haiku subagents.

**Files:**
- Create: `agents/topic-resolver.md`
- Create: `agents/search-agent.md`
- Create: `agents/classify-agent.md`
- Create: `agents/thread-discoverer.md`

Each agent file follows the Claude Code agent format with YAML frontmatter defining name, description, model, and tools. The body is the system prompt.

**Step 1: Write `agents/search-agent.md`**

Refactored from current `skills/research-search/SKILL.md`. Key changes:
- Agent frontmatter instead of skill frontmatter
- Model explicitly set to `haiku`
- Prompt updated to prioritize primary sources (`.gov`, `.edu`, court records)
- Source quality scoring (primary/secondary/tertiary)
- Output format unchanged (JSON with selected_urls, rejected_urls)

**Step 2: Write `agents/classify-agent.md`**

Refactored from current `skills/research-classify/SKILL.md`. Key changes:
- Reads vault index query results instead of globbing
- Accepts summaries instead of full article text
- Includes `write_model` field in output (sonnet default, opus for synthesis)
- Batch-aware: classifies all topics consistently when given multiple summaries

**Step 3: Write `agents/topic-resolver.md`**

New agent. Parses natural language prompts into structured plans:
- Detects file paths in input → local extraction mode
- Detects vault note references → thread-pull mode
- Everything else → web research
- Reads referenced vault notes for shared context
- Outputs `research_plan.json` with topics, tiers, estimated usage

**Step 4: Write `agents/thread-discoverer.md`**

New agent. Scans batch results for leads:
- Input: all summaries + key_entities + key_claims from a completed run
- Queries vault index to check what already exists
- Scores leads by frequency, novelty, connectedness, specificity
- Outputs ranked thread proposals

**Step 5: Commit**

```bash
git add agents/
git commit -m "feat: add agent definitions (resolver, search, classify, discover)"
```

---

### Task 11: Research Skill (Main Orchestrator)

The main `/research` skill that ties everything together. Replaces the current `skills/research/SKILL.md`.

**Files:**
- Rewrite: `skills/research/SKILL.md`

**Step 1: Write the new skill**

This is the largest single file. It orchestrates all 8 stages:

1. **Detect tier** — run `detect_tier.py`, set capabilities
2. **Check for active run** — if `current_run.json` exists, offer resume/restart/abandon
3. **Resolve** — dispatch topic-resolver agent, present plan for approval
4. **Search** — dispatch search-agent(s) in parallel (Haiku subagents, or SearXNG via Python)
5. **Fetch** — run `fetch_and_clean.py --parallel` with all URLs
6. **Media** — run `fetch_media.py` to download images/PDFs/video
7. **Summarize** — run `summarize.py` (Ollama) or dispatch Haiku subagents
8. **Classify** — dispatch classify-agent with summaries + vault index query
9. **Write** — iterate notes in tier order. Sonnet for standard, Opus for synthesis. Read shared context from files, not prompt.
10. **Discover** — dispatch thread-discoverer agent, present leads
11. **Complete** — archive run to history, print summary

Key patterns:
- State checkpoint after every stage
- Shared context referenced by file path, never duplicated in prompts
- Error collection — failures don't stop the pipeline
- Write stage checks file mtime before overwriting

**Step 2: Commit**

```bash
git add skills/research/SKILL.md
git commit -m "feat: rewrite research skill as 8-stage orchestrator"
```

---

### Task 12: Setup Skill

The `/research-setup` wizard for first-run configuration.

**Files:**
- Create: `skills/research-setup/SKILL.md`

**Step 1: Write the setup skill**

Interactive wizard that:
1. Asks for vault path (or offers template vault)
2. Scans vault conventions (folders, tags, frontmatter, MOC patterns)
3. Detects platform (Linux/Mac/Windows/WSL)
4. Offers Ollama installation:
   - Linux/Mac: auto-install with confirmation
   - Windows: guide to download page
   - WSL: use Linux install path
5. Hardware check → model recommendation → offer to pull model → benchmark
6. Detect/install yt-dlp (same platform-aware pattern)
7. Check for SearXNG
8. Generate `config.json` + `vault_rules.txt`
9. Build vault index

**Step 2: Commit**

```bash
git add skills/research-setup/SKILL.md
git commit -m "feat: add research-setup wizard skill"
```

---

## Phase 4: Extensions

### Task 13: Video Handling

Add yt-dlp audio extraction + Whisper transcription to the media pipeline.

**Files:**
- Modify: `scripts/fetch_media.py` — add `download_video()` and `transcribe_audio()`
- Modify: `tests/test_fetch_media.py` — add video tests

**Step 1: Write tests for video extraction and transcription**

```python
def test_download_video_extracts_audio(tmp_path):
    from fetch_media import download_video
    with patch("fetch_media.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = download_video(
            url="https://youtube.com/watch?v=abc123",
            assets_dir=tmp_path / "assets",
            topic_slug="test",
        )
    assert mock_run.called
    # yt-dlp should be called with audio-only flags
    call_args = mock_run.call_args[0][0]
    assert "yt-dlp" in call_args[0] or "yt-dlp" in str(call_args)


def test_transcribe_audio_calls_whisper(tmp_path):
    from fetch_media import transcribe_audio
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake audio")
    with patch("fetch_media.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Transcribed text here")
        result = transcribe_audio(audio_file)
    assert result is not None
```

**Step 2: Implement, test, commit**

```bash
git add scripts/fetch_media.py tests/test_fetch_media.py
git commit -m "feat: add video extraction (yt-dlp) and transcription (Whisper)"
```

---

### Task 14: SearXNG Integration

Add SearXNG as an alternative search backend for full tier.

**Files:**
- Create: `scripts/search_searxng.py`
- Create: `docker/docker-compose.yml`
- Create: `docker/searxng/settings.yml`
- Test: `tests/test_search_searxng.py`

**Step 1: Write tests**

```python
# tests/test_search_searxng.py
def test_search_returns_scored_results():
    from search_searxng import search
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": [
        {"url": "https://gov.sc.gov/doc", "title": "Gov Doc", "engine": "google"},
        {"url": "https://news.com/article", "title": "News", "engine": "google"},
    ]}
    mock_resp.raise_for_status = MagicMock()
    with patch("search_searxng.requests.get", return_value=mock_resp):
        results = search("ALPR surveillance SC", searxng_url="http://localhost:8888")
    assert len(results) == 2
    # Gov source should score higher
    gov = [r for r in results if "gov" in r["url"]][0]
    news = [r for r in results if "news" in r["url"]][0]
    assert gov["source_score"] > news["source_score"]
```

**Step 2: Implement, test, commit**

```bash
git add scripts/search_searxng.py docker/ tests/test_search_searxng.py
git commit -m "feat: add SearXNG search backend with source quality scoring"
```

---

### Task 15: Produce Output Integration

Keep `produce_output.py` but remove the `claude_pipe.py` dependency. Route through Ollama or prepare files for Claude Code.

**Files:**
- Modify: `scripts/produce_output.py` — replace `claude_pipe` import with Ollama call or file-based output
- Modify: `tests/test_produce_output.py` — update mocks

**Step 1: Refactor, test, commit**

```bash
git add scripts/produce_output.py tests/test_produce_output.py
git commit -m "refactor: decouple produce_output from claude_pipe (use Ollama or file output)"
```

---

## Phase 5: Cleanup & Distribution

### Task 16: Template Vault

Create the starter vault for new users.

**Files:**
- Create: `template-vault/Inbox/.gitkeep`
- Create: `template-vault/Projects/Example Topic/_MOC.md`
- Create: `template-vault/Resources/.gitkeep`
- Create: `template-vault/Meta/Tags.md`
- Create: `template-vault/assets/.gitkeep`
- Create: `template-vault/.research-workflow/config.json`

**Step 1: Create template files, commit**

```bash
git add template-vault/
git commit -m "feat: add starter template vault for new users"
```

---

### Task 17: Remove Dead Code

Remove scripts that have been absorbed or replaced.

**Files:**
- Delete: `scripts/claude_pipe.py`, `tests/test_claude_pipe.py`
- Delete: `scripts/ingest.py`, `tests/test_ingest.py`
- Delete: `scripts/ingest_batch.py`, `tests/test_ingest_batch.py`
- Delete: `scripts/ingest_local.py`, `tests/test_ingest_local.py`
- Delete: `scripts/find_related.py`, `tests/test_find_related.py`
- Delete: `scripts/synthesize_folder.py`, `tests/test_synthesize_folder.py`
- Delete: `scripts/daily_digest.py`, `tests/test_daily_digest.py`
- Delete: `scripts/discover_vault.py`, `tests/test_discover_vault.py`
- Delete: `skills/research-search/SKILL.md` (replaced by `agents/search-agent.md`)
- Delete: `skills/research-classify/SKILL.md` (replaced by `agents/classify-agent.md`)

**Step 1: Delete files, run remaining tests to confirm nothing breaks**

Run: `pytest tests/ -v`
Expected: All remaining tests PASS

**Step 2: Commit**

```bash
git add -A
git commit -m "chore: remove dead code (absorbed into new pipeline)"
```

---

### Task 18: Migration Script

One-time script to migrate an existing vault from the old system.

**Files:**
- Create: `scripts/migrate.py`
- Test: `tests/test_migrate.py`

Handles:
- Rename `Areas/` → `Projects/` (with wikilink + frontmatter path updates)
- Generate new `config.json` from old `.env`
- Build vault index
- Clean up old `.tmp/` state files

**Step 1: Write tests, implement, commit**

```bash
git add scripts/migrate.py tests/test_migrate.py
git commit -m "feat: add migration script (Areas→Projects, old config→new config)"
```

---

### Task 19: Update Requirements & README

**Files:**
- Modify: `requirements.txt` — remove `anthropic`, add `yt-dlp` as optional
- Modify: `README.md` — rewrite for plugin distribution, tier explanations, setup guide
- Modify: `MANIFEST.md` — regenerate for new structure
- Modify: `CLAUDE.md` — update project guide for new architecture

**Step 1: Update all docs, commit**

```bash
git add requirements.txt README.md MANIFEST.md CLAUDE.md
git commit -m "docs: update requirements, README, MANIFEST, CLAUDE.md for v2"
```

---

### Task 20: Full Integration Test

Run the complete test suite, verify everything works together.

**Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 2: Verify plugin loads**

Test that `plugin.json` references valid files:
```bash
python -c "import json; p=json.load(open('plugin.json')); [open(f).close() for f in p['skills']+p['agents']]"
```

**Step 3: Final commit and tag**

```bash
git tag v2.0.0-alpha
```

---

## Execution Order Summary

```
Phase 1 (Foundation):     Tasks 1-4   — config, state, vault index, tier detection
Phase 2 (Core Pipeline):  Tasks 5-8   — parallel fetch, media, summarize, extract
Phase 3 (Skills/Agents):  Tasks 9-12  — plugin.json, agents, research skill, setup skill
Phase 4 (Extensions):     Tasks 13-15 — video, SearXNG, produce_output
Phase 5 (Cleanup):        Tasks 16-20 — template vault, dead code removal, migration, docs
```

Each phase depends on the previous one. Tasks within a phase can sometimes be parallelized (e.g., Tasks 5-8 are independent of each other).
