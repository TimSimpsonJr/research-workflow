"""
media_handler.py — Media Extraction, Download, and Citation Tracking

Purpose: Extract embedded media references from markdown, download media files
to the vault attachments folder, rewrite references to vault-local paths,
and track citation metadata for all media assets.

Supports:
- Images (JPG, PNG, GIF, SVG, WebP) from markdown content
- YouTube videos (thumbnail + transcript via yt-dlp)
- Audio files (copy to vault, transcription via whisper)
- Manual attachment of local or web media to existing notes

Usage:
    # Extract and download media from markdown content
    python media_handler.py --extract content.md --attachments-dir /vault/Attachments --slug article-name

    # Download a single media URL to attachments
    python media_handler.py --download "https://example.com/image.png" --attachments-dir /vault/Attachments --slug article-name

    # Process a YouTube URL (thumbnail + transcript)
    python media_handler.py --youtube "https://youtube.com/watch?v=ID" --attachments-dir /vault/Attachments --slug video-name

Dependencies: requests, rich, python-dotenv
Optional: yt-dlp (for YouTube), whisper (for audio transcription)
"""

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urljoin

import requests
from rich.console import Console

console = Console()

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".bmp", ".ico"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}
ALL_MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

YOUTUBE_PATTERNS = [
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([\w-]+)"),
    re.compile(r"(?:https?://)?youtu\.be/([\w-]+)"),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/embed/([\w-]+)"),
]

# Markdown image pattern: ![alt](url) or ![alt](url "title")
MD_IMAGE_PATTERN = re.compile(
    r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)"
)

# HTML img tag pattern (common in Jina Reader output)
HTML_IMG_PATTERN = re.compile(
    r'<img[^>]+src=["\']([^"\']+)["\'][^>]*/?>'
)

# Max file size for download (50 MB)
MAX_DOWNLOAD_SIZE = 50 * 1024 * 1024

# Download timeout in seconds
DOWNLOAD_TIMEOUT = 30


# ──────────────────────────────────────────────
# Citation metadata
# ──────────────────────────────────────────────

def build_citation(
    source_url: str,
    title: str = "",
    author: str = "",
    accessed_at: str | None = None,
    media_type: str = "image",
    local_path: str = "",
) -> dict:
    """Build a structured citation dict for a media asset."""
    return {
        "source_url": source_url,
        "title": title,
        "author": author,
        "accessed_at": accessed_at or datetime.now(timezone.utc).isoformat(),
        "media_type": media_type,
        "local_path": local_path,
    }


def format_citation_inline(citation: dict) -> str:
    """Format a citation as an inline markdown reference.

    Returns something like: [Source](https://example.com/image.png)
    """
    label = citation.get("title") or "Source"
    url = citation.get("source_url", "")
    if url:
        return f"[{label}]({url})"
    return f"*{label}*"


def format_citations_frontmatter(citations: list[dict]) -> str:
    """Format citations list as YAML frontmatter block.

    Returns a string like:
    media_assets:
      - source_url: https://...
        local_path: Attachments/slug/image.png
        media_type: image
        accessed_at: 2026-02-26T...
    """
    if not citations:
        return ""
    lines = ["media_assets:"]
    for c in citations:
        lines.append(f"  - source_url: {c['source_url']}")
        if c.get("local_path"):
            lines.append(f"    local_path: {c['local_path']}")
        lines.append(f"    media_type: {c['media_type']}")
        lines.append(f"    accessed_at: {c['accessed_at']}")
        if c.get("title"):
            safe_title = c["title"].replace('"', '\\"')
            lines.append(f'    title: "{safe_title}"')
        if c.get("author"):
            lines.append(f"    author: {c['author']}")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# URL extraction
# ──────────────────────────────────────────────

def extract_image_urls(markdown: str) -> list[dict]:
    """Extract image URLs from markdown content.

    Returns list of dicts with {url, alt_text, original_syntax}.
    Handles both ![alt](url) and <img src="url"> patterns.
    """
    images = []
    seen_urls = set()

    for match in MD_IMAGE_PATTERN.finditer(markdown):
        alt_text = match.group(1)
        url = match.group(2)
        if url not in seen_urls and _is_downloadable_url(url):
            seen_urls.add(url)
            images.append({
                "url": url,
                "alt_text": alt_text,
                "original_syntax": match.group(0),
            })

    for match in HTML_IMG_PATTERN.finditer(markdown):
        url = match.group(1)
        if url not in seen_urls and _is_downloadable_url(url):
            seen_urls.add(url)
            images.append({
                "url": url,
                "alt_text": "",
                "original_syntax": match.group(0),
            })

    return images


def extract_youtube_urls(markdown: str) -> list[str]:
    """Extract YouTube video URLs from markdown content."""
    urls = []
    seen_ids = set()
    for pattern in YOUTUBE_PATTERNS:
        for match in pattern.finditer(markdown):
            video_id = match.group(1)
            if video_id not in seen_ids:
                seen_ids.add(video_id)
                urls.append(f"https://www.youtube.com/watch?v={video_id}")
    return urls


def _is_downloadable_url(url: str) -> bool:
    """Check if a URL is a downloadable web resource (not data URI, anchor, etc.)."""
    if not url:
        return False
    if url.startswith("data:"):
        return False
    if url.startswith("#"):
        return False
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https")


# ──────────────────────────────────────────────
# SSRF protection (reuse pattern from fetch_and_clean.py)
# ──────────────────────────────────────────────

def _validate_media_url(url: str) -> None:
    """Reject URLs targeting private/internal networks."""
    # Import SSRF check from fetch_and_clean if available, else inline
    try:
        from fetch_and_clean import validate_url
        validate_url(url)
    except ImportError:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Blocked URL scheme '{parsed.scheme}': {url}")
        from ipaddress import ip_address
        import socket
        hostname = parsed.hostname or ""
        blocked = {"localhost", "localhost.localdomain"}
        if hostname in blocked:
            raise ValueError(f"Blocked hostname '{hostname}': {url}")
        try:
            addr = ip_address(hostname)
            if addr.is_private or addr.is_loopback or addr.is_reserved:
                raise ValueError(f"Blocked private IP '{hostname}': {url}")
        except ValueError as orig:
            if "Blocked" in str(orig):
                raise
            try:
                resolved = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
                for _fam, _type, _proto, _canon, sockaddr in resolved:
                    addr = ip_address(sockaddr[0])
                    if addr.is_private or addr.is_loopback or addr.is_reserved:
                        raise ValueError(f"Blocked: '{hostname}' resolves to private IP {addr}")
            except socket.gaierror:
                pass


# ──────────────────────────────────────────────
# Download helpers
# ──────────────────────────────────────────────

def _content_hash(data: bytes) -> str:
    """SHA-256 hash of binary content."""
    return hashlib.sha256(data).hexdigest()[:12]


def _safe_filename(url: str, content: bytes | None = None) -> str:
    """Derive a safe filename from a URL, with content hash for uniqueness."""
    parsed = urlparse(url)
    basename = Path(parsed.path).name or "media"
    # Strip query params from name
    basename = basename.split("?")[0]
    # Sanitize
    basename = re.sub(r"[^\w.\-]", "_", basename)
    # Add content hash prefix for uniqueness
    if content:
        prefix = _content_hash(content)
        name, ext = os.path.splitext(basename)
        basename = f"{prefix}-{name}{ext}"
    # Ensure it has an extension
    if not os.path.splitext(basename)[1]:
        basename += ".bin"
    return basename


def download_media(
    url: str,
    dest_dir: Path,
    filename: str | None = None,
) -> tuple[Path, int]:
    """Download a media file from URL to dest_dir.

    Returns (local_path, file_size_bytes).
    Raises ValueError for SSRF, RuntimeError for download failures.
    """
    _validate_media_url(url)
    dest_dir.mkdir(parents=True, exist_ok=True)

    response = requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True)
    response.raise_for_status()

    # Check content length before downloading
    content_length = response.headers.get("Content-Length")
    if content_length and int(content_length) > MAX_DOWNLOAD_SIZE:
        raise RuntimeError(f"File too large ({int(content_length)} bytes): {url}")

    # Download to memory first (with size limit)
    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=8192):
        total += len(chunk)
        if total > MAX_DOWNLOAD_SIZE:
            raise RuntimeError(f"File exceeded {MAX_DOWNLOAD_SIZE} byte limit: {url}")
        chunks.append(chunk)
    data = b"".join(chunks)

    if not filename:
        filename = _safe_filename(url, data)

    dest_path = dest_dir / filename
    dest_path.write_bytes(data)
    return dest_path, len(data)


def copy_local_media(
    source_path: Path,
    dest_dir: Path,
    filename: str | None = None,
) -> tuple[Path, int]:
    """Copy a local media file to dest_dir.

    Returns (local_path, file_size_bytes).
    """
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    if not filename:
        filename = source_path.name

    dest_path = dest_dir / filename
    if dest_path.resolve() != source_path.resolve():
        shutil.copy2(source_path, dest_path)

    return dest_path, dest_path.stat().st_size


# ──────────────────────────────────────────────
# YouTube handling
# ──────────────────────────────────────────────

def _check_ytdlp() -> bool:
    """Check if yt-dlp is available on PATH."""
    return shutil.which("yt-dlp") is not None


def fetch_youtube_metadata(url: str) -> dict:
    """Fetch YouTube video metadata via yt-dlp.

    Returns dict with title, description, thumbnail_url, duration, uploader,
    upload_date, video_id.
    Raises RuntimeError if yt-dlp is not available.
    """
    if not _check_ytdlp():
        raise RuntimeError(
            "yt-dlp not found. Install it: pip install yt-dlp  (or: brew install yt-dlp)"
        )

    result = subprocess.run(
        [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--no-warnings",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed for {url}: {result.stderr.strip()}")

    info = json.loads(result.stdout)
    return {
        "video_id": info.get("id", ""),
        "title": info.get("title", ""),
        "description": info.get("description", ""),
        "thumbnail_url": info.get("thumbnail", ""),
        "duration": info.get("duration", 0),
        "uploader": info.get("uploader", ""),
        "upload_date": info.get("upload_date", ""),
        "url": url,
    }


def fetch_youtube_transcript(url: str) -> str | None:
    """Fetch auto-generated transcript for a YouTube video via yt-dlp.

    Returns transcript text, or None if unavailable.
    """
    if not _check_ytdlp():
        return None

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [
                "yt-dlp",
                "--write-auto-sub",
                "--sub-lang", "en",
                "--sub-format", "vtt",
                "--skip-download",
                "--no-warnings",
                "-o", f"{tmpdir}/%(id)s.%(ext)s",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return None

        # Find the .vtt file
        vtt_files = list(Path(tmpdir).glob("*.vtt"))
        if not vtt_files:
            return None

        vtt_content = vtt_files[0].read_text(encoding="utf-8", errors="ignore")

        # Strip VTT timestamps (reuse pattern from transcript_processor)
        try:
            from transcript_processor import strip_vtt
            return strip_vtt(vtt_content)
        except ImportError:
            # Inline fallback
            lines = []
            for line in vtt_content.splitlines():
                line = line.strip()
                if not line or line == "WEBVTT":
                    continue
                if re.match(r"\d{2}:\d{2}:\d{2}[\.,]\d{3}\s*-->\s*", line):
                    continue
                if re.match(r"^\d+$", line):
                    continue
                lines.append(line)
            return "\n".join(lines) if lines else None


def download_youtube_thumbnail(
    thumbnail_url: str,
    dest_dir: Path,
    video_id: str,
) -> Path | None:
    """Download a YouTube thumbnail image.

    Returns local path, or None on failure.
    """
    if not thumbnail_url:
        return None
    try:
        path, _ = download_media(
            thumbnail_url,
            dest_dir,
            filename=f"{video_id}-thumbnail.jpg",
        )
        return path
    except Exception as e:
        console.print(f"[yellow]Warning: Could not download thumbnail: {e}[/yellow]")
        return None


def process_youtube(
    url: str,
    attachments_dir: Path,
    slug: str,
) -> dict:
    """Process a YouTube URL: fetch metadata, thumbnail, and transcript.

    Returns dict with metadata, citation, local paths, and transcript text.
    """
    dest_dir = attachments_dir / slug

    metadata = fetch_youtube_metadata(url)
    video_id = metadata["video_id"]

    # Download thumbnail
    thumb_path = download_youtube_thumbnail(
        metadata["thumbnail_url"],
        dest_dir,
        video_id,
    )

    # Fetch transcript
    transcript = fetch_youtube_transcript(url)

    citation = build_citation(
        source_url=url,
        title=metadata["title"],
        author=metadata["uploader"],
        media_type="video",
        local_path=str(thumb_path.relative_to(attachments_dir.parent))
        if thumb_path else "",
    )

    return {
        "metadata": metadata,
        "thumbnail_path": str(thumb_path) if thumb_path else None,
        "transcript": transcript,
        "citation": citation,
    }


# ──────────────────────────────────────────────
# Audio handling
# ──────────────────────────────────────────────

def _check_whisper() -> bool:
    """Check if whisper CLI is available on PATH."""
    return shutil.which("whisper") is not None


def process_audio(
    source_path: Path,
    attachments_dir: Path,
    slug: str,
    whisper_model: str = "base",
) -> dict:
    """Process an audio file: copy to vault and optionally transcribe.

    Returns dict with local_path, transcript (if available), and citation.
    """
    dest_dir = attachments_dir / slug
    local_path, file_size = copy_local_media(source_path, dest_dir)

    transcript = None
    if _check_whisper():
        try:
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subprocess.run(
                    [
                        "whisper",
                        str(source_path),
                        "--model", whisper_model,
                        "--output_dir", tmpdir,
                        "--output_format", "txt",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                if result.returncode == 0:
                    txt_files = list(Path(tmpdir).glob("*.txt"))
                    if txt_files:
                        transcript = txt_files[0].read_text(encoding="utf-8")
        except Exception as e:
            console.print(f"[yellow]Warning: Whisper transcription failed: {e}[/yellow]")

    citation = build_citation(
        source_url=f"file://{source_path.resolve()}",
        title=source_path.stem,
        media_type="audio",
        local_path=str(local_path.relative_to(attachments_dir.parent)),
    )

    return {
        "local_path": str(local_path),
        "file_size": file_size,
        "transcript": transcript,
        "citation": citation,
    }


# ──────────────────────────────────────────────
# Markdown rewriting
# ──────────────────────────────────────────────

def rewrite_markdown_images(
    markdown: str,
    downloaded: dict[str, Path],
    vault_root: Path,
) -> str:
    """Replace external image URLs in markdown with vault-local Obsidian embeds.

    Args:
        markdown: Original markdown content.
        downloaded: Mapping of original URL -> local file path.
        vault_root: Root of the Obsidian vault (for relative path computation).

    Returns:
        Markdown with rewritten image references.
    """
    result = markdown
    for url, local_path in downloaded.items():
        try:
            rel_path = local_path.relative_to(vault_root)
        except ValueError:
            rel_path = local_path.name

        obsidian_embed = f"![[{rel_path}]]"
        # Replace markdown image syntax
        result = re.sub(
            rf"!\[[^\]]*\]\({re.escape(url)}(?:\s+\"[^\"]*\")?\)",
            obsidian_embed,
            result,
        )
        # Replace HTML img tags
        result = re.sub(
            rf'<img[^>]+src=["\']' + re.escape(url) + r'["\'][^>]*/?>',
            obsidian_embed,
            result,
        )

    return result


# ──────────────────────────────────────────────
# High-level extraction pipeline
# ──────────────────────────────────────────────

def extract_and_download_media(
    markdown: str,
    attachments_dir: Path,
    slug: str,
    vault_root: Path,
    source_url: str = "",
) -> tuple[str, list[dict]]:
    """Extract embedded media from markdown, download to vault, rewrite references.

    This is the main entry point for automatic media extraction during ingestion.

    Args:
        markdown: Markdown content (from Jina Reader, local parser, etc.)
        attachments_dir: Vault attachments folder (e.g., Vault/Attachments)
        slug: Slug for organizing media (e.g., article name)
        vault_root: Root of the Obsidian vault
        source_url: URL of the source document (for resolving relative image URLs)

    Returns:
        (rewritten_markdown, citations_list)
    """
    dest_dir = attachments_dir / slug
    images = extract_image_urls(markdown)
    youtube_urls = extract_youtube_urls(markdown)

    downloaded: dict[str, Path] = {}
    citations: list[dict] = []

    # Process images
    for img in images:
        url = img["url"]
        # Resolve relative URLs
        if source_url and not urlparse(url).scheme:
            url = urljoin(source_url, url)

        try:
            local_path, size = download_media(url, dest_dir)
            downloaded[img["url"]] = local_path
            citations.append(build_citation(
                source_url=url,
                title=img["alt_text"] or local_path.stem,
                media_type="image",
                local_path=str(local_path.relative_to(vault_root)),
            ))
        except Exception as e:
            console.print(f"[yellow]Warning: Could not download {url}: {e}[/yellow]")

    # Process YouTube embeds found in content
    for yt_url in youtube_urls:
        try:
            yt_result = process_youtube(yt_url, attachments_dir, slug)
            citations.append(yt_result["citation"])
        except Exception as e:
            console.print(f"[yellow]Warning: Could not process YouTube {yt_url}: {e}[/yellow]")

    # Rewrite markdown
    rewritten = rewrite_markdown_images(markdown, downloaded, vault_root)

    return rewritten, citations


# ──────────────────────────────────────────────
# Frontmatter integration
# ──────────────────────────────────────────────

def inject_citations_into_frontmatter(
    frontmatter: str,
    citations: list[dict],
) -> str:
    """Add media_assets and citation fields to existing YAML frontmatter.

    Expects frontmatter string that starts with '---' and ends with '---'.
    Returns updated frontmatter string.
    """
    if not citations:
        return frontmatter

    citations_yaml = format_citations_frontmatter(citations)

    # Insert before the closing ---
    if frontmatter.rstrip().endswith("---"):
        # Find the last ---
        last_sep = frontmatter.rstrip().rfind("---")
        if last_sep > 0:
            before = frontmatter[:last_sep].rstrip()
            return f"{before}\n{citations_yaml}\n---\n\n"

    return frontmatter


def append_sources_section(
    markdown: str,
    citations: list[dict],
) -> str:
    """Append a ## Sources section to markdown with inline citations for media.

    If a ## Sources section already exists, appends to it.
    """
    if not citations:
        return markdown

    source_lines = []
    for c in citations:
        label = c.get("title") or c.get("media_type", "media")
        url = c.get("source_url", "")
        accessed = c.get("accessed_at", "")[:10]  # Date only
        if url:
            source_lines.append(f"- [{label}]({url}) (accessed {accessed})")

    if not source_lines:
        return markdown

    sources_block = "\n".join(source_lines)

    # Check if ## Sources section exists
    sources_match = re.search(r"^## Sources\s*$", markdown, re.MULTILINE)
    if sources_match:
        # Append to existing section
        insert_pos = sources_match.end()
        return f"{markdown[:insert_pos]}\n{sources_block}\n{markdown[insert_pos:]}"

    # Add new section at the end
    return f"{markdown.rstrip()}\n\n## Sources\n\n{sources_block}\n"


# ──────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract, download, and track media assets for vault notes."
    )
    subparsers = parser.add_subparsers(dest="command")

    # Extract: process markdown content and download embedded media
    extract_parser = subparsers.add_parser("extract", help="Extract media from markdown file")
    extract_parser.add_argument("file", help="Path to markdown file")
    extract_parser.add_argument("--attachments-dir", required=True, help="Vault attachments directory")
    extract_parser.add_argument("--vault-root", required=True, help="Vault root directory")
    extract_parser.add_argument("--slug", required=True, help="Slug for organizing media")
    extract_parser.add_argument("--source-url", default="", help="Original source URL (for relative refs)")
    extract_parser.add_argument("--dry-run", action="store_true")

    # Download: download a single media URL
    dl_parser = subparsers.add_parser("download", help="Download a single media URL")
    dl_parser.add_argument("url", help="URL to download")
    dl_parser.add_argument("--attachments-dir", required=True, help="Vault attachments directory")
    dl_parser.add_argument("--slug", required=True, help="Slug for organizing media")

    # YouTube: process a YouTube URL
    yt_parser = subparsers.add_parser("youtube", help="Process a YouTube URL")
    yt_parser.add_argument("url", help="YouTube URL")
    yt_parser.add_argument("--attachments-dir", required=True, help="Vault attachments directory")
    yt_parser.add_argument("--slug", required=True, help="Slug for organizing media")

    args = parser.parse_args()

    if args.command == "extract":
        file_path = Path(args.file)
        if not file_path.exists():
            console.print(f"[red]File not found: {file_path}[/red]")
            sys.exit(1)

        markdown = file_path.read_text(encoding="utf-8")
        attachments_dir = Path(args.attachments_dir)
        vault_root = Path(args.vault_root)

        if args.dry_run:
            images = extract_image_urls(markdown)
            yt_urls = extract_youtube_urls(markdown)
            console.print(f"Found {len(images)} image(s) and {len(yt_urls)} YouTube URL(s)")
            for img in images:
                console.print(f"  Image: {img['url']}")
            for yt in yt_urls:
                console.print(f"  YouTube: {yt}")
            return

        rewritten, citations = extract_and_download_media(
            markdown, attachments_dir, args.slug, vault_root, args.source_url,
        )

        # Write results
        file_path.write_text(rewritten, encoding="utf-8")
        console.print(f"[green]Processed {len(citations)} media asset(s)[/green]")

        # Output citation JSON for pipeline integration
        if citations:
            print(json.dumps(citations, indent=2))

    elif args.command == "download":
        attachments_dir = Path(args.attachments_dir)
        dest_dir = attachments_dir / args.slug
        local_path, size = download_media(args.url, dest_dir)
        console.print(f"[green]Downloaded:[/green] {local_path} ({size} bytes)")

    elif args.command == "youtube":
        attachments_dir = Path(args.attachments_dir)
        result = process_youtube(args.url, attachments_dir, args.slug)
        console.print(f"[green]Title:[/green] {result['metadata']['title']}")
        if result["thumbnail_path"]:
            console.print(f"[green]Thumbnail:[/green] {result['thumbnail_path']}")
        if result["transcript"]:
            console.print(f"[green]Transcript:[/green] {len(result['transcript'])} chars")
        print(json.dumps(result["citation"], indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
