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
