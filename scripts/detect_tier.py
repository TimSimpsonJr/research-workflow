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
    """Check if SearXNG is reachable and its JSON API is enabled."""
    if not url:
        return {"available": False, "url": None}
    base = url.rstrip("/")
    try:
        resp = requests.get(f"{base}/healthz", timeout=5)
        if resp.status_code != 200:
            return {"available": False, "url": url, "error": f"healthz returned {resp.status_code}"}
    except Exception as e:
        return {"available": False, "url": url, "error": str(e)}
    # Verify JSON format is enabled (SearXNG returns 403 if json not in formats)
    try:
        resp = requests.get(f"{base}/search", params={"q": "test", "format": "json"}, timeout=10)
        if resp.status_code == 403:
            return {"available": False, "url": url, "error": "JSON format disabled in SearXNG settings. Add 'json' to search.formats in settings.yml"}
        return {"available": True, "url": url}
    except Exception:
        return {"available": True, "url": url}  # healthz passed, JSON check inconclusive


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
