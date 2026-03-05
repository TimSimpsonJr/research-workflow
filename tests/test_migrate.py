# tests/test_migrate.py
"""Tests for migrate.py — vault migration script."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch


def test_rename_folder_moves_directory(tmp_path):
    from migrate import rename_folder

    (tmp_path / "Areas" / "Topic").mkdir(parents=True)
    (tmp_path / "Areas" / "Topic" / "note.md").write_text("content")
    count = rename_folder(tmp_path, "Areas", "Projects")
    assert (tmp_path / "Projects" / "Topic" / "note.md").exists()
    assert not (tmp_path / "Areas").exists()


def test_rename_folder_updates_wikilinks(tmp_path):
    from migrate import rename_folder

    (tmp_path / "Areas").mkdir()
    note = tmp_path / "note.md"
    note.write_text("See [[Areas/Topic/Note]] for details")
    rename_folder(tmp_path, "Areas", "Projects")
    assert "[[Projects/Topic/Note]]" in note.read_text()


def test_rename_folder_updates_aliased_wikilinks(tmp_path):
    from migrate import rename_folder

    (tmp_path / "Areas").mkdir()
    note = tmp_path / "note.md"
    note.write_text("See [[Areas/Topic/Note|my alias]] for details")
    rename_folder(tmp_path, "Areas", "Projects")
    assert "[[Projects/Topic/Note|my alias]]" in note.read_text()


def test_rename_folder_updates_multiple_links_in_one_file(tmp_path):
    from migrate import rename_folder

    (tmp_path / "Areas").mkdir()
    note = tmp_path / "note.md"
    note.write_text("Link [[Areas/A]] and [[Areas/B]] here")
    rename_folder(tmp_path, "Areas", "Projects")
    text = note.read_text()
    assert "[[Projects/A]]" in text
    assert "[[Projects/B]]" in text
    assert "Areas" not in text


def test_rename_folder_returns_modified_count(tmp_path):
    from migrate import rename_folder

    (tmp_path / "Areas").mkdir()
    (tmp_path / "a.md").write_text("[[Areas/X]]")
    (tmp_path / "b.md").write_text("[[Areas/Y]]")
    (tmp_path / "c.md").write_text("no links here")
    count = rename_folder(tmp_path, "Areas", "Projects")
    assert count == 2


def test_rename_folder_skips_when_source_missing(tmp_path):
    from migrate import rename_folder

    count = rename_folder(tmp_path, "Areas", "Projects")
    assert count == 0


def test_rename_folder_skips_when_target_exists(tmp_path):
    from migrate import rename_folder

    (tmp_path / "Areas").mkdir()
    (tmp_path / "Projects").mkdir()
    count = rename_folder(tmp_path, "Areas", "Projects")
    assert count == 0
    # Source should not have been removed
    assert (tmp_path / "Areas").exists()


def test_rename_folder_dry_run_does_not_move(tmp_path):
    from migrate import rename_folder

    (tmp_path / "Areas" / "Topic").mkdir(parents=True)
    (tmp_path / "Areas" / "Topic" / "note.md").write_text("content")
    note = tmp_path / "other.md"
    note.write_text("[[Areas/Topic/note]]")
    count = rename_folder(tmp_path, "Areas", "Projects", dry_run=True)
    # Folder should still be in the old location
    assert (tmp_path / "Areas" / "Topic" / "note.md").exists()
    assert not (tmp_path / "Projects").exists()
    # Wikilinks should be unchanged
    assert "[[Areas/Topic/note]]" in note.read_text()
    # But count should still reflect what would change
    assert count == 1


def test_rename_folder_skips_hidden_dirs(tmp_path):
    from migrate import rename_folder

    (tmp_path / "Areas").mkdir()
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    hidden_note = hidden / "note.md"
    hidden_note.write_text("[[Areas/X]]")
    rename_folder(tmp_path, "Areas", "Projects")
    # Hidden dir files should not be modified
    assert "[[Areas/X]]" in hidden_note.read_text()


def test_migrate_env_to_config(tmp_path):
    from migrate import migrate_env_to_config

    env_file = tmp_path / ".env"
    env_file.write_text(
        "VAULT_PATH=" + str(tmp_path) + "\n"
        "INBOX_PATH=" + str(tmp_path / "Inbox") + "\n"
    )
    config = migrate_env_to_config(tmp_path, env_path=env_file)
    assert config["vault_root"] == str(tmp_path)


def test_migrate_env_to_config_extracts_inbox(tmp_path):
    from migrate import migrate_env_to_config

    env_file = tmp_path / ".env"
    env_file.write_text(
        "VAULT_PATH=" + str(tmp_path) + "\n"
        "INBOX_PATH=" + str(tmp_path / "Inbox") + "\n"
    )
    config = migrate_env_to_config(tmp_path, env_path=env_file)
    assert config["inbox"] == "Inbox"


def test_migrate_env_to_config_saves_json(tmp_path):
    from migrate import migrate_env_to_config

    env_file = tmp_path / ".env"
    env_file.write_text("VAULT_PATH=" + str(tmp_path) + "\n")
    migrate_env_to_config(tmp_path, env_path=env_file)
    config_file = tmp_path / ".research-workflow" / "config.json"
    assert config_file.exists()
    data = json.loads(config_file.read_text())
    assert data["vault_root"] == str(tmp_path)


def test_migrate_env_to_config_without_env_file(tmp_path):
    from migrate import migrate_env_to_config

    config = migrate_env_to_config(tmp_path)
    # Should still produce a valid config with defaults
    assert config["vault_root"] == str(tmp_path)
    assert config["inbox"] == "Inbox"


def test_migrate_env_to_config_dry_run(tmp_path):
    from migrate import migrate_env_to_config

    env_file = tmp_path / ".env"
    env_file.write_text("VAULT_PATH=" + str(tmp_path) + "\n")
    config = migrate_env_to_config(tmp_path, env_path=env_file, dry_run=True)
    # Config dict should be returned
    assert config["vault_root"] == str(tmp_path)
    # But no file should have been written
    config_file = tmp_path / ".research-workflow" / "config.json"
    assert not config_file.exists()


def test_migrate_env_to_config_parses_date_and_tag_format(tmp_path):
    from migrate import migrate_env_to_config

    env_file = tmp_path / ".env"
    env_file.write_text(
        "VAULT_PATH=" + str(tmp_path) + "\n"
        "DATE_FORMAT=%d/%m/%Y\n"
        "TAG_FORMAT=inline\n"
    )
    config = migrate_env_to_config(tmp_path, env_path=env_file)
    assert config["date_format"] == "%d/%m/%Y"
    assert config["tag_format"] == "inline"


def test_migrate_env_to_config_parses_frontmatter_fields(tmp_path):
    from migrate import migrate_env_to_config

    env_file = tmp_path / ".env"
    env_file.write_text(
        "VAULT_PATH=" + str(tmp_path) + "\n"
        "FRONTMATTER_FIELDS=title,source,tags,created,author\n"
    )
    config = migrate_env_to_config(tmp_path, env_path=env_file)
    assert config["frontmatter_fields"] == ["title", "source", "tags", "created", "author"]


def test_migrate_env_skips_comments_and_blanks(tmp_path):
    from migrate import migrate_env_to_config

    env_file = tmp_path / ".env"
    env_file.write_text(
        "# This is a comment\n"
        "\n"
        "VAULT_PATH=" + str(tmp_path) + "\n"
        "# Another comment\n"
    )
    config = migrate_env_to_config(tmp_path, env_path=env_file)
    assert config["vault_root"] == str(tmp_path)


def test_cleanup_old_state(tmp_path):
    from migrate import cleanup_old_state

    tmp_dir = tmp_path / ".tmp"
    tmp_dir.mkdir()
    (tmp_dir / "old_file.json").write_text("{}")
    cleaned = cleanup_old_state(tmp_path)
    assert not tmp_dir.exists()


def test_cleanup_old_state_returns_removed_paths(tmp_path):
    from migrate import cleanup_old_state

    tmp_dir = tmp_path / ".tmp"
    tmp_dir.mkdir()
    (tmp_dir / "cache.json").write_text("{}")
    cleaned = cleanup_old_state(tmp_path)
    assert any(".tmp" in p for p in cleaned)


def test_cleanup_old_state_no_tmp_dir(tmp_path):
    from migrate import cleanup_old_state

    cleaned = cleanup_old_state(tmp_path)
    assert cleaned == []


def test_cleanup_old_state_dry_run(tmp_path):
    from migrate import cleanup_old_state

    tmp_dir = tmp_path / ".tmp"
    tmp_dir.mkdir()
    (tmp_dir / "old_file.json").write_text("{}")
    cleaned = cleanup_old_state(tmp_path, dry_run=True)
    # Should report the path
    assert any(".tmp" in p for p in cleaned)
    # But should NOT actually remove it
    assert tmp_dir.exists()


def test_rename_folder_preserves_non_matching_links(tmp_path):
    """Wikilinks that don't reference the old folder should be untouched."""
    from migrate import rename_folder

    (tmp_path / "Areas").mkdir()
    note = tmp_path / "note.md"
    note.write_text("See [[Projects/Other]] and [[Inbox/Draft]]")
    rename_folder(tmp_path, "Areas", "Projects")
    text = note.read_text()
    assert "[[Projects/Other]]" in text
    assert "[[Inbox/Draft]]" in text


def test_full_migration_idempotent(tmp_path):
    """Running migration twice should not fail or double-rename."""
    from migrate import rename_folder, migrate_env_to_config, cleanup_old_state

    # First run
    (tmp_path / "Areas" / "Topic").mkdir(parents=True)
    (tmp_path / "Areas" / "Topic" / "note.md").write_text("content")
    (tmp_path / "link.md").write_text("[[Areas/Topic/note]]")
    rename_folder(tmp_path, "Areas", "Projects")
    migrate_env_to_config(tmp_path)

    # Second run — Areas/ no longer exists, should be a no-op
    count = rename_folder(tmp_path, "Areas", "Projects")
    assert count == 0
    # Config should still be valid
    config = migrate_env_to_config(tmp_path)
    assert config["vault_root"] == str(tmp_path)
