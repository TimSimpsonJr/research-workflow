"""
fetch_media.py — Media Download and Asset Management

Purpose: Pipeline Stage 4 (MEDIA). Scans fetched markdown content for media
references (images, PDFs, video URLs), downloads files to the vault's assets
directory, and rewrites content to use Obsidian embed syntax.

Usage:
    python fetch_media.py --content note.md --assets-dir /vault/assets --topic my-topic --run-id run-001
    python fetch_media.py --content note.md --assets-dir /vault/assets --topic my-topic --run-id run-001 --max-size 5242880

Dependencies: requests

Note: Video download (yt-dlp + Whisper) is deferred to Task 13. This script
detects video URLs in extract_media_refs but does not download them.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote

import requests

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
DOCUMENT_EXTENSIONS = {".pdf"}
VIDEO_EXTENSIONS = {".mp4", ".webm"}
BLOCKED_EXTENSIONS = {".exe", ".zip", ".docx", ".msi", ".dmg", ".tar", ".gz",
                      ".rar", ".7z", ".iso", ".bat", ".sh", ".dll", ".so",
                      ".deb", ".rpm", ".cab", ".com", ".scr"}

VIDEO_DOMAINS = {"youtube.com", "www.youtube.com", "youtu.be",
                 "vimeo.com", "www.vimeo.com"}

DEFAULT_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


# ──────────────────────────────────────────────
# URL classification helpers
# ──────────────────────────────────────────────

def _get_extension(url: str) -> str:
    """Extract lowercase file extension from URL path."""
    parsed = urlparse(url)
    path = unquote(parsed.path)
    ext = Path(path).suffix.lower()
    return ext


def _is_video_domain(url: str) -> bool:
    """Check if URL belongs to a known video hosting domain."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return hostname in VIDEO_DOMAINS


def _classify_url(url: str) -> str | None:
    """
    Classify a URL as 'image', 'document', 'video', or None (blocked/unknown).

    Returns None for blocked extensions or unrecognized URLs.
    """
    ext = _get_extension(url)

    # Check blocked first
    if ext in BLOCKED_EXTENSIONS:
        return None

    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if _is_video_domain(url):
        return "video"

    return None


# ──────────────────────────────────────────────
# extract_media_refs
# ──────────────────────────────────────────────

def extract_media_refs(content: str) -> list[dict]:
    """
    Regex scan of markdown content for media URLs.

    Finds:
    - Images: markdown image syntax ![...](url) and bare URLs ending in
      .png, .jpg, .jpeg, .gif, .svg, .webp
    - Documents: links ending in .pdf
    - Video: YouTube URLs (youtube.com/watch, youtu.be/), Vimeo URLs,
      links ending in .mp4, .webm

    Skips: .exe, .zip, .docx, .msi, etc.

    Returns list of {"url": "...", "type": "image"|"document"|"video"}.
    Deduplicates by URL.
    """
    seen: set[str] = set()
    refs: list[dict] = []

    def _add(url: str, media_type: str) -> None:
        if url not in seen:
            seen.add(url)
            refs.append({"url": url, "type": media_type})

    # Pattern 1: Markdown images ![alt](url)
    for match in re.finditer(r'!\[[^\]]*\]\(([^)]+)\)', content):
        url = match.group(1).strip()
        media_type = _classify_url(url)
        if media_type:
            _add(url, media_type)

    # Pattern 2: Markdown links [text](url)
    for match in re.finditer(r'(?<!!)\[[^\]]*\]\(([^)]+)\)', content):
        url = match.group(1).strip()
        media_type = _classify_url(url)
        if media_type:
            _add(url, media_type)

    # Pattern 3: Bare URLs (https://... ending in media extension)
    for match in re.finditer(r'(?<!\()(https?://[^\s\)]+)', content):
        url = match.group(1).strip()
        # Only match bare URLs that have a recognized media extension
        # (video domains without extensions are caught in markdown link patterns)
        ext = _get_extension(url)
        if ext in IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS | VIDEO_EXTENSIONS:
            media_type = _classify_url(url)
            if media_type:
                _add(url, media_type)

    return refs


# ──────────────────────────────────────────────
# download_media_file
# ──────────────────────────────────────────────

def download_media_file(
    url: str,
    assets_dir: Path,
    topic_slug: str,
    run_id: str,
    max_size_bytes: int = DEFAULT_MAX_SIZE_BYTES,
) -> dict | None:
    """
    Download a media file via requests.get with streaming.

    Checks Content-Length header first — skips if exceeds max_size_bytes.
    Saves to {assets_dir}/{topic_slug}/{filename}.
    Writes .meta sidecar JSON with source_url, downloaded_at, research_run,
    size_bytes, content_type.

    Returns {"url", "local_path", "type", "size_bytes"} or None if skipped/failed.
    """
    try:
        with requests.get(url, stream=True, timeout=30) as resp:
            resp.raise_for_status()

            # Check Content-Length if available
            content_length = resp.headers.get("content-length")
            if content_length is not None:
                size = int(content_length)
                if size > max_size_bytes:
                    print(f"[fetch_media] Skipping {url}: size {size} exceeds max {max_size_bytes}",
                          file=sys.stderr)
                    return None

            content_type = resp.headers.get("content-type", "application/octet-stream")

            # Determine filename from URL
            parsed = urlparse(url)
            path = unquote(parsed.path)
            filename = Path(path).name or "download"

            # Create target directory
            target_dir = Path(assets_dir) / topic_slug
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / filename

            # Stream to file
            total_bytes = 0
            with open(target_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_bytes += len(chunk)
                        if total_bytes > max_size_bytes:
                            print(f"[fetch_media] Aborting {url}: exceeded max size during download",
                                  file=sys.stderr)
                            f.close()
                            target_path.unlink(missing_ok=True)
                            return None

            # Write .meta sidecar JSON
            meta = {
                "source_url": url,
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "research_run": run_id,
                "size_bytes": total_bytes,
                "content_type": content_type,
            }
            meta_path = target_dir / f"{filename}.meta"
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

            # Classify file type
            media_type = _classify_url(url) or "unknown"

            return {
                "url": url,
                "local_path": str(target_path),
                "type": media_type,
                "size_bytes": total_bytes,
            }

    except Exception as exc:
        print(f"[fetch_media] Failed to download {url}: {exc}", file=sys.stderr)
        return None


# ──────────────────────────────────────────────
# rewrite_media_refs
# ──────────────────────────────────────────────

def rewrite_media_refs(content: str, manifest: list[dict]) -> str:
    """
    Replace markdown image/link references with Obsidian embed syntax.

    Takes original content and a list of {"url": "...", "local_path": "..."} entries.
    Replaces markdown image/link references with ![[local_path]].
    Returns updated content.
    """
    if not manifest:
        return content

    # Build URL -> local_path mapping
    url_map: dict[str, str] = {entry["url"]: entry["local_path"] for entry in manifest}

    result = content

    for url, local_path in url_map.items():
        # Replace ![alt](url) with ![[local_path]]
        result = re.sub(
            r'!\[[^\]]*\]\(' + re.escape(url) + r'\)',
            f'![[{local_path}]]',
            result,
        )
        # Replace [text](url) with ![[local_path]]
        result = re.sub(
            r'(?<!!)\[[^\]]*\]\(' + re.escape(url) + r'\)',
            f'![[{local_path}]]',
            result,
        )
        # Replace bare URLs
        result = result.replace(url, f'![[{local_path}]]')

    return result


# ──────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download media from fetched content and rewrite references (Stage 4)."
    )
    parser.add_argument("--content", required=True, help="Path to markdown content file")
    parser.add_argument("--assets-dir", required=True, help="Path to vault assets directory")
    parser.add_argument("--topic", required=True, help="Topic slug for asset subdirectory")
    parser.add_argument("--run-id", required=True, help="Research run identifier")
    parser.add_argument("--max-size", type=int, default=DEFAULT_MAX_SIZE_BYTES,
                        help=f"Max file size in bytes (default: {DEFAULT_MAX_SIZE_BYTES})")
    parser.add_argument("--output", help="Output path for rewritten content (stdout if omitted)")
    parser.add_argument("--dry-run", action="store_true", help="List media refs; do not download")
    args = parser.parse_args()

    content_path = Path(args.content)
    if not content_path.exists():
        print(f"[fetch_media] ERROR: Content file not found: {content_path}", file=sys.stderr)
        sys.exit(1)

    content = content_path.read_text(encoding="utf-8")
    refs = extract_media_refs(content)

    if args.dry_run:
        print(f"[fetch_media] Dry run — {len(refs)} media ref(s) found:", file=sys.stderr)
        for ref in refs:
            print(f"  [{ref['type']}] {ref['url']}", file=sys.stderr)
        return

    # Download media (skip video — deferred to Task 13)
    assets_dir = Path(args.assets_dir)
    manifest: list[dict] = []
    for ref in refs:
        if ref["type"] == "video":
            print(f"[fetch_media] Skipping video (not yet supported): {ref['url']}",
                  file=sys.stderr)
            continue
        result = download_media_file(
            url=ref["url"],
            assets_dir=assets_dir,
            topic_slug=args.topic,
            run_id=args.run_id,
            max_size_bytes=args.max_size,
        )
        if result:
            manifest.append(result)

    # Rewrite content
    updated = rewrite_media_refs(content, manifest)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(updated, encoding="utf-8")
        print(f"[fetch_media] Rewritten content saved to {output_path}", file=sys.stderr)
    else:
        print(updated)

    # Print summary
    print(f"[fetch_media] Downloaded {len(manifest)}/{len(refs)} media file(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
