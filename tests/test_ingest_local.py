# tests/test_ingest_local.py
"""Tests for ingest_local.py"""

import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "C:/Users/tim/OneDrive/Documents/Tim's Vault")
os.environ.setdefault("INBOX_PATH", "C:/Users/tim/OneDrive/Documents/Tim's Vault/+Inbox")


# ──────────────────────────────────────────────
# build_frontmatter
# ──────────────────────────────────────────────

def test_build_frontmatter_inline_tags():
    from ingest_local import build_frontmatter
    fm = build_frontmatter(
        title="My Doc",
        source_path="/path/to/my-doc.docx",
        ingested_at="2026-02-26T10:00:00+00:00",
        file_type="docx",
        source_label=None,
        tag_format="inline",
    )
    assert 'title: "My Doc"' in fm
    assert "source: file:///path/to/my-doc.docx" in fm
    assert "file_type: docx" in fm
    assert "tags: [inbox, unprocessed]" in fm
    assert "source_label" not in fm


def test_build_frontmatter_list_tags():
    from ingest_local import build_frontmatter
    fm = build_frontmatter(
        title="My Doc",
        source_path="/path/to/my-doc.docx",
        ingested_at="2026-02-26T10:00:00+00:00",
        file_type="docx",
        source_label=None,
        tag_format="list",
    )
    assert "  - inbox" in fm
    assert "  - unprocessed" in fm


def test_build_frontmatter_with_source_label():
    from ingest_local import build_frontmatter
    fm = build_frontmatter(
        title="My Doc",
        source_path="/path/to/my-doc.docx",
        ingested_at="2026-02-26T10:00:00+00:00",
        file_type="docx",
        source_label="BJU Dorm Resources",
        tag_format="inline",
    )
    assert 'source_label: "BJU Dorm Resources"' in fm


def test_build_frontmatter_escapes_quotes_in_title():
    from ingest_local import build_frontmatter
    fm = build_frontmatter(
        title='He said "hello"',
        source_path="/path/to/file.docx",
        ingested_at="2026-02-26T10:00:00+00:00",
        file_type="docx",
        source_label=None,
        tag_format="inline",
    )
    assert '\\"hello\\"' in fm


# ──────────────────────────────────────────────
# unique_output_path
# ──────────────────────────────────────────────

def test_unique_output_path_no_conflict(tmp_path):
    from ingest_local import unique_output_path
    result = unique_output_path(tmp_path, "2026-02-26", "my-doc")
    assert result == tmp_path / "2026-02-26-my-doc.md"


def test_unique_output_path_conflict(tmp_path):
    from ingest_local import unique_output_path
    (tmp_path / "2026-02-26-my-doc.md").write_text("existing")
    result = unique_output_path(tmp_path, "2026-02-26", "my-doc")
    assert result == tmp_path / "2026-02-26-my-doc-2.md"


def test_unique_output_path_multiple_conflicts(tmp_path):
    from ingest_local import unique_output_path
    (tmp_path / "2026-02-26-my-doc.md").write_text("existing")
    (tmp_path / "2026-02-26-my-doc-2.md").write_text("existing")
    result = unique_output_path(tmp_path, "2026-02-26", "my-doc")
    assert result == tmp_path / "2026-02-26-my-doc-3.md"


# ──────────────────────────────────────────────
# extract_mp3
# ──────────────────────────────────────────────

def test_extract_mp3_returns_stub():
    from ingest_local import extract_mp3
    path = Path("Addicts Unanimous - Dr. Jim Berg.mp3")
    result = extract_mp3(path)
    assert "AUDIO FILE" in result
    assert "transcription required" in result
    assert "whisper" in result
    assert path.name in result


# ──────────────────────────────────────────────
# extract_text dispatch
# ──────────────────────────────────────────────

def test_extract_text_dispatches_docx():
    from ingest_local import extract_text
    with patch("ingest_local.extract_docx", return_value="docx content") as mock:
        content, method = extract_text(Path("file.docx"))
    mock.assert_called_once()
    assert content == "docx content"
    assert method == "python-docx"


def test_extract_text_dispatches_doc():
    from ingest_local import extract_text
    with patch("ingest_local.extract_doc", return_value="doc content") as mock:
        content, method = extract_text(Path("file.doc"))
    mock.assert_called_once()
    assert content == "doc content"
    assert method == "doc-extracted"


def test_extract_text_dispatches_pdf():
    from ingest_local import extract_text
    with patch("ingest_local.extract_pdf", return_value="pdf content") as mock:
        content, method = extract_text(Path("file.pdf"))
    mock.assert_called_once()
    assert content == "pdf content"
    assert method == "pymupdf"


def test_extract_text_dispatches_mp3():
    from ingest_local import extract_text
    content, method = extract_text(Path("audio.mp3"))
    assert "AUDIO FILE" in content
    assert method == "stub"


def test_extract_text_unsupported_extension():
    from ingest_local import extract_text
    with pytest.raises(RuntimeError, match="Unsupported extension"):
        extract_text(Path("file.xlsx"))


# ──────────────────────────────────────────────
# extract_docx
# ──────────────────────────────────────────────

def test_extract_docx_missing_dependency():
    from ingest_local import extract_docx
    with patch.dict("sys.modules", {"docx": None}):
        with pytest.raises(RuntimeError, match="python-docx not installed"):
            extract_docx(Path("file.docx"))


def test_extract_docx_joins_paragraphs():
    from ingest_local import extract_docx

    mock_para1 = MagicMock()
    mock_para1.text = "First paragraph."
    mock_para2 = MagicMock()
    mock_para2.text = ""  # empty — should be filtered out
    mock_para3 = MagicMock()
    mock_para3.text = "Third paragraph."

    mock_doc = MagicMock()
    mock_doc.paragraphs = [mock_para1, mock_para2, mock_para3]

    mock_docx_module = MagicMock()
    mock_docx_module.Document.return_value = mock_doc

    with patch.dict("sys.modules", {"docx": mock_docx_module}):
        result = extract_docx(Path("file.docx"))

    assert result == "First paragraph.\n\nThird paragraph."


# ──────────────────────────────────────────────
# extract_pdf
# ──────────────────────────────────────────────

def test_extract_pdf_missing_dependency():
    from ingest_local import extract_pdf
    with patch.dict("sys.modules", {"fitz": None}):
        with pytest.raises(RuntimeError, match="pymupdf not installed"):
            extract_pdf(Path("file.pdf"))


def test_extract_pdf_joins_pages():
    from ingest_local import extract_pdf

    mock_page1 = MagicMock()
    mock_page1.get_text.return_value = "Page one content."
    mock_page2 = MagicMock()
    mock_page2.get_text.return_value = "  "  # whitespace only — filtered out
    mock_page3 = MagicMock()
    mock_page3.get_text.return_value = "Page three content."

    mock_fitz_doc = MagicMock()
    mock_fitz_doc.__iter__ = MagicMock(return_value=iter([mock_page1, mock_page2, mock_page3]))

    mock_fitz = MagicMock()
    mock_fitz.open.return_value = mock_fitz_doc

    with patch.dict("sys.modules", {"fitz": mock_fitz}):
        result = extract_pdf(Path("file.pdf"))

    assert "Page one content." in result
    assert "Page three content." in result
    assert "---" in result
    assert "  " not in result


# ──────────────────────────────────────────────
# extract_doc fallback chain
# ──────────────────────────────────────────────

def test_extract_doc_succeeds_via_docx():
    from ingest_local import extract_doc
    with patch("ingest_local.extract_docx", return_value="doc as docx content"):
        result = extract_doc(Path("file.doc"))
    assert result == "doc as docx content"


def test_extract_doc_falls_back_to_soffice():
    from ingest_local import extract_doc
    with patch("ingest_local.extract_docx", side_effect=Exception("not ooxml")):
        with patch("ingest_local._try_soffice_convert", return_value="soffice content"):
            result = extract_doc(Path("file.doc"))
    assert result == "soffice content"


def test_extract_doc_falls_back_to_win32com():
    from ingest_local import extract_doc
    with patch("ingest_local.extract_docx", side_effect=Exception("not ooxml")):
        with patch("ingest_local._try_soffice_convert", return_value=None):
            with patch("ingest_local._try_win32com", return_value="word content"):
                result = extract_doc(Path("file.doc"))
    assert result == "word content"


def test_extract_doc_raises_when_all_fail():
    from ingest_local import extract_doc
    with patch("ingest_local.extract_docx", side_effect=Exception("not ooxml")):
        with patch("ingest_local._try_soffice_convert", return_value=None):
            with patch("ingest_local._try_win32com", return_value=None):
                with pytest.raises(RuntimeError, match="Could not extract .doc"):
                    extract_doc(Path("file.doc"))


# ──────────────────────────────────────────────
# process_file
# ──────────────────────────────────────────────

def test_process_file_writes_note(tmp_path):
    from ingest_local import process_file

    fake_file = tmp_path / "My Document.docx"
    fake_file.write_text("placeholder")

    with patch("ingest_local.extract_text", return_value=("Extracted content.", "python-docx")):
        result = process_file(fake_file, tmp_path, "Test Label", dry_run=False)

    assert result is True
    written = list(tmp_path.glob("*.md"))
    assert len(written) == 1
    note_text = written[0].read_text()
    assert 'title: "My Document"' in note_text
    assert "Extracted content." in note_text
    assert 'source_label: "Test Label"' in note_text


def test_process_file_dry_run_does_not_write(tmp_path):
    from ingest_local import process_file

    fake_file = tmp_path / "My Document.docx"
    fake_file.write_text("placeholder")

    with patch("ingest_local.extract_text", return_value=("content", "python-docx")):
        result = process_file(fake_file, tmp_path, None, dry_run=True)

    assert result is True
    assert list(tmp_path.glob("*.md")) == []


def test_process_file_returns_false_on_extraction_error(tmp_path):
    from ingest_local import process_file

    fake_file = tmp_path / "bad.doc"
    fake_file.write_text("placeholder")

    with patch("ingest_local.extract_text", side_effect=RuntimeError("Could not extract")):
        result = process_file(fake_file, tmp_path, None, dry_run=False)

    assert result is False
    assert list(tmp_path.glob("*.md")) == []
