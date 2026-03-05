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
                 "ollama_model", "ollama_benchmark_ms", "searxng_url",
                 "whisper_available", "ytdlp_available", "tier"]
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
