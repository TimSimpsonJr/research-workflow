"""
ingest_local.py — Local File Ingestion

Purpose: Extract text from local .docx, .doc, .pdf, and .mp3 files and write
         cleaned markdown notes to the vault inbox.

Usage:
    python ingest_local.py /path/to/folder
    python ingest_local.py /path/to/folder --recursive
    python ingest_local.py /path/to/folder --source-label "BJU Dorm Resources"
    python ingest_local.py /path/to/folder --output-dir /custom/output
    python ingest_local.py /path/to/folder --dry-run

Supported formats:
    .docx   — python-docx (pip install python-docx)
    .doc    — LibreOffice headless ->win32com (MS Word) ->error with instructions
    .pdf    — pymupdf (pip install pymupdf)
    .mp3    — stub note only; marks file as needing Whisper transcription

Dependencies: python-docx, pymupdf
Optional:     pywin32 (Windows .doc support via MS Word COM automation)
"""

import argparse
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

import config
from utils import slugify, startup_checks

console = Console()

SUPPORTED_EXTENSIONS = {".docx", ".doc", ".pdf", ".mp3"}


# ──────────────────────────────────────────────
# Text extraction
# ──────────────────────────────────────────────

def extract_docx(path: Path) -> str:
    """Extract text from .docx via python-docx."""
    try:
        import docx
    except ImportError:
        raise RuntimeError("python-docx not installed — run: pip install python-docx")
    doc = docx.Document(path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def _find_soffice() -> str | None:
    """Return the soffice executable path, checking PATH then common install locations."""
    for cmd in ("soffice", "libreoffice"):
        try:
            subprocess.run([cmd, "--version"], capture_output=True, timeout=5, check=False)
            return cmd
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    # Windows fallback: check standard install locations
    windows_candidates = [
        Path("C:/Program Files/LibreOffice/program/soffice.exe"),
        Path("C:/Program Files (x86)/LibreOffice/program/soffice.exe"),
    ]
    for candidate in windows_candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _try_soffice_convert(path: Path) -> str | None:
    """Try converting .doc ->.docx via LibreOffice headless, then extract text."""
    soffice = _find_soffice()
    if not soffice:
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [soffice, "--headless", "--convert-to", "docx", "--outdir", tmpdir, str(path)],
            capture_output=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            return None
        converted = Path(tmpdir) / (path.stem + ".docx")
        if not converted.exists():
            return None
        try:
            return extract_docx(converted)
        except Exception:
            return None


def _try_win32com(path: Path) -> str | None:
    """Try extracting .doc text via Microsoft Word COM automation (Windows only)."""
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return None
    pythoncom.CoInitialize()
    word = None
    try:
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(str(path.resolve()))
        text = doc.Content.Text
        doc.Close(False)
        return text.strip() if text else None
    except Exception:
        return None
    finally:
        if word:
            word.Quit()
        pythoncom.CoUninitialize()


def extract_doc(path: Path) -> str:
    """Extract text from legacy .doc file using a multi-backend fallback chain.

    Order of attempts:
    1. python-docx (succeeds if file is OOXML mislabeled as .doc)
    2. LibreOffice headless conversion
    3. win32com / MS Word (Windows only)
    """
    try:
        return extract_docx(path)
    except Exception:
        pass

    result = _try_soffice_convert(path)
    if result is not None:
        return result

    result = _try_win32com(path)
    if result is not None:
        return result

    raise RuntimeError(
        "Could not extract .doc — install LibreOffice (https://www.libreoffice.org) "
        "or Microsoft Word, then retry."
    )


def extract_pdf(path: Path) -> str:
    """Extract text from PDF via pymupdf, one section per page."""
    try:
        import fitz
    except ImportError:
        raise RuntimeError("pymupdf not installed — run: pip install pymupdf")
    doc = fitz.open(str(path))
    pages = []
    for page in doc:
        text = page.get_text().strip()
        if text:
            pages.append(text)
    doc.close()
    return "\n\n---\n\n".join(pages)


def extract_mp3(path: Path) -> str:
    """Return a stub for audio files — transcription requires Whisper."""
    return (
        f"> **AUDIO FILE** — transcription required\n\n"
        f"**Filename:** `{path.name}`\n\n"
        f"To generate a transcript, run:\n\n"
        f"```bash\n"
        f'whisper "{path}" --model medium --output_format vtt\n'
        f"```\n\n"
        f"Then process the transcript with `transcript_processor.py`."
    )


def extract_text(path: Path) -> tuple[str, str]:
    """Dispatch text extraction by file extension.

    Returns:
        (content_markdown, extraction_method)

    Raises:
        RuntimeError if extraction fails or extension is unsupported.
    """
    ext = path.suffix.lower()
    if ext == ".docx":
        return extract_docx(path), "python-docx"
    elif ext == ".doc":
        return extract_doc(path), "doc-extracted"
    elif ext == ".pdf":
        return extract_pdf(path), "pymupdf"
    elif ext == ".mp3":
        return extract_mp3(path), "stub"
    else:
        raise RuntimeError(f"Unsupported extension: {ext}")


# ──────────────────────────────────────────────
# Frontmatter
# ──────────────────────────────────────────────

def build_frontmatter(
    title: str,
    source_path: str,
    ingested_at: str,
    file_type: str,
    source_label: str | None,
    tag_format: str,
) -> str:
    """Build YAML frontmatter for a locally ingested file."""
    safe_title = title.replace('"', '\\"')
    if tag_format == "inline":
        tags_line = "tags: [inbox, unprocessed]"
    else:
        tags_line = "tags:\n  - inbox\n  - unprocessed"
    label_line = f'source_label: "{source_label}"\n' if source_label else ""
    return (
        f"---\n"
        f'title: "{safe_title}"\n'
        f"source: file://{source_path}\n"
        f"ingested_at: {ingested_at}\n"
        f"file_type: {file_type}\n"
        f"{label_line}"
        f"{tags_line}\n"
        f"---\n\n"
    )


# ──────────────────────────────────────────────
# Output path
# ──────────────────────────────────────────────

def unique_output_path(inbox_path: Path, date: str, slug: str) -> Path:
    """Return a unique inbox path, appending -2, -3, etc. if needed."""
    base = inbox_path / f"{date}-{slug}.md"
    if not base.exists():
        return base
    counter = 2
    while True:
        candidate = inbox_path / f"{date}-{slug}-{counter}.md"
        if not candidate.exists():
            return candidate
        counter += 1


# ──────────────────────────────────────────────
# Per-file processing
# ──────────────────────────────────────────────

def process_file(
    path: Path,
    inbox_path: Path,
    source_label: str | None,
    dry_run: bool,
) -> bool:
    """Extract, format, and write a single file. Returns True on success."""
    try:
        content, method = extract_text(path)
    except RuntimeError as exc:
        console.print(f"[red]SKIP[/red]  {path.name} — {exc}")
        return False

    title = path.stem
    slug = slugify(title) or "untitled"
    now = datetime.now(timezone.utc)
    date_str = now.strftime(config.DATE_FORMAT)
    ingested_at = now.isoformat()
    file_type = path.suffix.lstrip(".").lower()

    frontmatter = build_frontmatter(
        title=title,
        source_path=str(path.resolve()),
        ingested_at=ingested_at,
        file_type=file_type,
        source_label=source_label,
        tag_format=config.TAG_FORMAT,
    )
    full_content = frontmatter + content

    out_path = unique_output_path(inbox_path, date_str, slug)

    if dry_run:
        console.print(f"[yellow]DRY RUN[/yellow] {path.name} ->{out_path.name} ({method})")
        return True

    out_path.write_text(full_content, encoding="utf-8", newline="\n")
    console.print(f"[green]OK[/green]     {path.name} ->{out_path.name} ({method})")
    return True


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Ingest local .docx, .doc, .pdf, and .mp3 files into the vault inbox."
    )
    parser.add_argument("folder", help="Folder to scan for documents")
    parser.add_argument(
        "--recursive", action="store_true", help="Scan subfolders recursively (default: top-level only)"
    )
    parser.add_argument(
        "--source-label",
        default=None,
        metavar="LABEL",
        help='Label written to frontmatter source_label field (e.g. "BJU Dorm Counseling Resources")',
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        metavar="DIR",
        help="Write notes to this directory instead of the configured vault inbox",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be written without writing any files",
    )
    args = parser.parse_args()

    startup_checks(require_api_key=False, ensure_inbox=True)

    folder = Path(args.folder)
    if not folder.is_dir():
        console.print(f"[red]Error:[/red] Not a directory: {folder}")
        sys.exit(1)

    inbox_path = Path(args.output_dir) if args.output_dir else config.INBOX_PATH
    if args.output_dir:
        inbox_path.mkdir(parents=True, exist_ok=True)

    glob_fn = folder.rglob if args.recursive else folder.glob
    files = sorted(
        f for f in glob_fn("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not files:
        console.print(f"[yellow]No supported files found in {folder}[/yellow]")
        console.print(f"Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
        return

    console.print(f"Found [bold]{len(files)}[/bold] file(s) to process.\n")

    succeeded, failed = 0, 0
    for path in files:
        ok = process_file(path, inbox_path, args.source_label, args.dry_run)
        if ok:
            succeeded += 1
        else:
            failed += 1

    status = "[green]Done.[/green]" if not failed else "[yellow]Done with skips.[/yellow]"
    console.print(f"\n{status} {succeeded} succeeded, {failed} skipped.")
    if failed:
        console.print(
            "[dim]Skipped files need LibreOffice or MS Word. "
            "See error messages above for details.[/dim]"
        )


if __name__ == "__main__":
    main()
