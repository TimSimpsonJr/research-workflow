"""
attach_media.py — Manual Media Attachment to Vault Notes

Purpose: Attach a media file (local or web) to an existing Obsidian note.
Downloads/copies the file to the vault attachments folder, adds an Obsidian
embed to the note, and updates frontmatter with citation metadata.

Usage:
    # Attach a local image to a note
    python attach_media.py "path/to/note.md" --file "path/to/image.png"

    # Attach a web image to a note
    python attach_media.py "path/to/note.md" --url "https://example.com/image.png"

    # Attach a YouTube video (thumbnail + transcript)
    python attach_media.py "path/to/note.md" --youtube "https://youtube.com/watch?v=ID"

    # Attach a local audio file (copy + optional transcription)
    python attach_media.py "path/to/note.md" --audio "path/to/recording.mp3"

    # Dry run
    python attach_media.py "path/to/note.md" --url "https://example.com/image.png" --dry-run

Dependencies: requests, rich, python-dotenv
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

import config
from media_handler import (
    append_sources_section,
    build_citation,
    copy_local_media,
    download_media,
    format_citations_frontmatter,
    inject_citations_into_frontmatter,
    process_audio,
    process_youtube,
)
from utils import slugify, startup_checks

console = Console()


def _note_slug(note_path: Path) -> str:
    """Derive a slug from a note filename for organizing attachments."""
    return slugify(note_path.stem) or "attachment"


def _split_frontmatter(content: str) -> tuple[str, str]:
    """Split note content into frontmatter and body.

    Returns (frontmatter_with_delimiters, body).
    If no frontmatter, returns ("", full_content).
    """
    if not content.startswith("---"):
        return "", content
    end = content.find("---", 3)
    if end == -1:
        return "", content
    # Include the closing --- and any trailing newlines
    fm_end = end + 3
    # Skip newlines after frontmatter
    while fm_end < len(content) and content[fm_end] == "\n":
        fm_end += 1
    return content[:fm_end], content[fm_end:]


def _make_embed(
    local_path: Path,
    vault_root: Path,
    alt_text: str = "",
) -> str:
    """Create an Obsidian embed syntax for a media file."""
    try:
        rel_path = local_path.relative_to(vault_root)
    except ValueError:
        rel_path = local_path.name
    return f"![[{rel_path}]]"


def _make_inline_citation(citation: dict) -> str:
    """Create an inline citation link."""
    label = citation.get("title") or "Source"
    url = citation.get("source_url", "")
    accessed = citation.get("accessed_at", "")[:10]
    if url:
        return f"*{label}* — [source]({url}) (accessed {accessed})"
    return f"*{label}*"


def attach_file(
    note_path: Path,
    source_path: Path,
    attachments_dir: Path,
    vault_root: Path,
    dry_run: bool = False,
) -> None:
    """Attach a local file to a note."""
    slug = _note_slug(note_path)
    dest_dir = attachments_dir / slug

    if dry_run:
        console.print(f"[yellow]Dry run — would copy {source_path} to {dest_dir}/[/yellow]")
        return

    local_path, size = copy_local_media(source_path, dest_dir)
    citation = build_citation(
        source_url=f"file://{source_path.resolve()}",
        title=source_path.stem,
        media_type=_detect_media_type(source_path),
        local_path=str(local_path.relative_to(vault_root)),
    )

    _update_note(note_path, local_path, citation, vault_root)
    console.print(f"[green]Attached:[/green] {local_path.name} ({size} bytes)")


def attach_url(
    note_path: Path,
    url: str,
    attachments_dir: Path,
    vault_root: Path,
    title: str = "",
    dry_run: bool = False,
) -> None:
    """Download and attach a web media file to a note."""
    slug = _note_slug(note_path)
    dest_dir = attachments_dir / slug

    if dry_run:
        console.print(f"[yellow]Dry run — would download {url} to {dest_dir}/[/yellow]")
        return

    local_path, size = download_media(url, dest_dir)
    citation = build_citation(
        source_url=url,
        title=title or local_path.stem,
        media_type=_detect_media_type(local_path),
        local_path=str(local_path.relative_to(vault_root)),
    )

    _update_note(note_path, local_path, citation, vault_root)
    console.print(f"[green]Downloaded and attached:[/green] {local_path.name} ({size} bytes)")


def attach_youtube(
    note_path: Path,
    url: str,
    attachments_dir: Path,
    vault_root: Path,
    dry_run: bool = False,
) -> None:
    """Process and attach a YouTube video to a note."""
    slug = _note_slug(note_path)

    if dry_run:
        console.print(f"[yellow]Dry run — would process YouTube URL: {url}[/yellow]")
        return

    result = process_youtube(url, attachments_dir, slug)
    metadata = result["metadata"]

    # Build the embed section
    content = note_path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(content)

    # Build YouTube section to insert
    sections = []
    sections.append(f"\n### {metadata['title']}")

    if result["thumbnail_path"]:
        thumb_path = Path(result["thumbnail_path"])
        embed = _make_embed(thumb_path, vault_root)
        sections.append(embed)

    sections.append(f"\n**Channel:** {metadata['uploader']}")
    if metadata["duration"]:
        mins = metadata["duration"] // 60
        secs = metadata["duration"] % 60
        sections.append(f"**Duration:** {mins}:{secs:02d}")
    sections.append(f"**URL:** {url}")

    if result["transcript"]:
        # Truncate long transcripts
        transcript = result["transcript"]
        if len(transcript) > 5000:
            transcript = transcript[:5000] + "\n\n*[transcript truncated]*"
        sections.append(f"\n<details><summary>Transcript</summary>\n\n{transcript}\n\n</details>")

    insert_block = "\n".join(sections) + "\n"

    # Update frontmatter with citation
    updated_fm = inject_citations_into_frontmatter(frontmatter, [result["citation"]])
    updated_body = append_sources_section(body + insert_block, [result["citation"]])

    note_path.write_text(updated_fm + updated_body, encoding="utf-8", newline="\n")
    console.print(f"[green]Attached YouTube video:[/green] {metadata['title']}")
    if result["transcript"]:
        console.print(f"[green]Transcript:[/green] {len(result['transcript'])} chars")


def attach_audio(
    note_path: Path,
    source_path: Path,
    attachments_dir: Path,
    vault_root: Path,
    whisper_model: str = "base",
    dry_run: bool = False,
) -> None:
    """Copy and optionally transcribe an audio file, then attach to note."""
    slug = _note_slug(note_path)

    if dry_run:
        console.print(f"[yellow]Dry run — would process audio: {source_path}[/yellow]")
        return

    result = process_audio(source_path, attachments_dir, slug, whisper_model)

    local_path = Path(result["local_path"])
    content = note_path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(content)

    # Build audio section
    sections = []
    embed = _make_embed(local_path, vault_root)
    sections.append(f"\n{embed}")

    if result["transcript"]:
        transcript = result["transcript"]
        if len(transcript) > 5000:
            transcript = transcript[:5000] + "\n\n*[transcript truncated]*"
        sections.append(f"\n<details><summary>Transcript</summary>\n\n{transcript}\n\n</details>")

    insert_block = "\n".join(sections) + "\n"

    updated_fm = inject_citations_into_frontmatter(frontmatter, [result["citation"]])
    updated_body = append_sources_section(body + insert_block, [result["citation"]])

    note_path.write_text(updated_fm + updated_body, encoding="utf-8", newline="\n")
    console.print(f"[green]Attached audio:[/green] {local_path.name} ({result['file_size']} bytes)")
    if result["transcript"]:
        console.print(f"[green]Transcript:[/green] {len(result['transcript'])} chars")


def _update_note(
    note_path: Path,
    local_path: Path,
    citation: dict,
    vault_root: Path,
) -> None:
    """Update a note with an embed and citation for attached media."""
    content = note_path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(content)

    embed = _make_embed(local_path, vault_root)
    inline_cite = _make_inline_citation(citation)
    insert = f"\n{embed}\n{inline_cite}\n"

    updated_fm = inject_citations_into_frontmatter(frontmatter, [citation])
    updated_body = append_sources_section(body + insert, [citation])

    note_path.write_text(updated_fm + updated_body, encoding="utf-8", newline="\n")


def _detect_media_type(path: Path) -> str:
    """Detect media type from file extension."""
    from media_handler import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, AUDIO_EXTENSIONS
    ext = path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    return "file"


def main():
    parser = argparse.ArgumentParser(
        description="Attach media to an existing Obsidian vault note."
    )
    parser.add_argument("note", help="Path to the vault note (.md file)")
    parser.add_argument("--dry-run", action="store_true")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Path to local media file to attach")
    group.add_argument("--url", help="URL of web media to download and attach")
    group.add_argument("--youtube", help="YouTube URL to process and attach")
    group.add_argument("--audio", help="Path to local audio file to attach (with optional transcription)")

    parser.add_argument("--title", default="", help="Title/label for the media (used in citations)")
    parser.add_argument("--whisper-model", default="base", help="Whisper model for audio transcription")

    args = parser.parse_args()

    startup_checks()

    note_path = Path(args.note)
    if not note_path.exists():
        # Try relative to vault root
        note_path = config.VAULT_PATH / args.note
    if not note_path.exists():
        console.print(f"[red]Note not found: {args.note}[/red]")
        sys.exit(1)

    # Determine attachments directory
    attachments_dir = getattr(config, "ATTACHMENTS_PATH", None)
    if not attachments_dir:
        attachments_dir = config.VAULT_PATH / "Attachments"
    vault_root = config.VAULT_PATH

    if args.file:
        attach_file(note_path, Path(args.file), attachments_dir, vault_root, args.dry_run)
    elif args.url:
        attach_url(note_path, args.url, attachments_dir, vault_root, args.title, args.dry_run)
    elif args.youtube:
        attach_youtube(note_path, args.youtube, attachments_dir, vault_root, args.dry_run)
    elif args.audio:
        attach_audio(
            note_path, Path(args.audio), attachments_dir, vault_root,
            args.whisper_model, args.dry_run,
        )


if __name__ == "__main__":
    main()
