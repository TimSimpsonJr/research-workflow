# tests/test_media_handler.py
"""Tests for media_handler.py — media extraction, download, and citation tracking."""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VAULT_PATH", "/tmp/test-vault")
os.environ.setdefault("INBOX_PATH", "/tmp/test-vault/Inbox")


# ──────────────────────────────────────────────
# Citation metadata
# ──────────────────────────────────────────────

def test_build_citation():
    from media_handler import build_citation
    c = build_citation(
        source_url="https://example.com/photo.jpg",
        title="Test Photo",
        author="Jane Doe",
        media_type="image",
        local_path="Attachments/slug/photo.jpg",
    )
    assert c["source_url"] == "https://example.com/photo.jpg"
    assert c["title"] == "Test Photo"
    assert c["author"] == "Jane Doe"
    assert c["media_type"] == "image"
    assert c["local_path"] == "Attachments/slug/photo.jpg"
    assert "accessed_at" in c


def test_build_citation_defaults():
    from media_handler import build_citation
    c = build_citation(source_url="https://example.com/img.png")
    assert c["title"] == ""
    assert c["author"] == ""
    assert c["media_type"] == "image"


def test_format_citation_inline():
    from media_handler import format_citation_inline
    c = {"title": "Chart", "source_url": "https://example.com/chart.png"}
    result = format_citation_inline(c)
    assert "[Chart](https://example.com/chart.png)" == result


def test_format_citation_inline_no_url():
    from media_handler import format_citation_inline
    c = {"title": "Chart", "source_url": ""}
    result = format_citation_inline(c)
    assert "*Chart*" == result


def test_format_citations_frontmatter_empty():
    from media_handler import format_citations_frontmatter
    assert format_citations_frontmatter([]) == ""


def test_format_citations_frontmatter():
    from media_handler import format_citations_frontmatter
    citations = [{
        "source_url": "https://example.com/img.png",
        "local_path": "Attachments/slug/img.png",
        "media_type": "image",
        "accessed_at": "2026-02-26T12:00:00+00:00",
        "title": "Test Image",
        "author": "",
    }]
    result = format_citations_frontmatter(citations)
    assert "media_assets:" in result
    assert "source_url: https://example.com/img.png" in result
    assert "local_path: Attachments/slug/img.png" in result
    assert "media_type: image" in result
    assert 'title: "Test Image"' in result


# ──────────────────────────────────────────────
# URL extraction
# ──────────────────────────────────────────────

def test_extract_image_urls_markdown():
    from media_handler import extract_image_urls
    md = "Some text ![alt text](https://example.com/image.png) more text"
    images = extract_image_urls(md)
    assert len(images) == 1
    assert images[0]["url"] == "https://example.com/image.png"
    assert images[0]["alt_text"] == "alt text"


def test_extract_image_urls_html():
    from media_handler import extract_image_urls
    md = 'Some text <img src="https://example.com/photo.jpg" alt="photo" /> more text'
    images = extract_image_urls(md)
    assert len(images) == 1
    assert images[0]["url"] == "https://example.com/photo.jpg"


def test_extract_image_urls_deduplicates():
    from media_handler import extract_image_urls
    md = (
        "![a](https://example.com/img.png)\n"
        "![b](https://example.com/img.png)\n"
    )
    images = extract_image_urls(md)
    assert len(images) == 1


def test_extract_image_urls_skips_data_uris():
    from media_handler import extract_image_urls
    md = "![icon](data:image/png;base64,abc123)"
    images = extract_image_urls(md)
    assert len(images) == 0


def test_extract_image_urls_skips_anchors():
    from media_handler import extract_image_urls
    md = "![](#section)"
    images = extract_image_urls(md)
    assert len(images) == 0


def test_extract_image_urls_with_title():
    from media_handler import extract_image_urls
    md = '![alt](https://example.com/img.png "image title")'
    images = extract_image_urls(md)
    assert len(images) == 1
    assert images[0]["url"] == "https://example.com/img.png"


def test_extract_image_urls_multiple():
    from media_handler import extract_image_urls
    md = (
        "![a](https://example.com/a.png)\n"
        "text\n"
        '<img src="https://example.com/b.jpg" />\n'
        "![c](https://example.com/c.webp)\n"
    )
    images = extract_image_urls(md)
    assert len(images) == 3
    urls = {i["url"] for i in images}
    assert "https://example.com/a.png" in urls
    assert "https://example.com/b.jpg" in urls
    assert "https://example.com/c.webp" in urls


def test_extract_youtube_urls():
    from media_handler import extract_youtube_urls
    md = (
        "Check out https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
        "Also https://youtu.be/abcdefghijk\n"
        "And https://www.youtube.com/embed/xyz123abcde\n"
    )
    urls = extract_youtube_urls(md)
    assert len(urls) == 3


def test_extract_youtube_urls_deduplicates():
    from media_handler import extract_youtube_urls
    md = (
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
        "https://youtu.be/dQw4w9WgXcQ\n"
    )
    urls = extract_youtube_urls(md)
    assert len(urls) == 1


def test_extract_youtube_urls_no_match():
    from media_handler import extract_youtube_urls
    md = "No videos here, just https://example.com"
    urls = extract_youtube_urls(md)
    assert len(urls) == 0


# ──────────────────────────────────────────────
# Download helpers
# ──────────────────────────────────────────────

def test_safe_filename_basic():
    from media_handler import _safe_filename
    name = _safe_filename("https://example.com/path/image.png")
    assert name == "image.png"  # No content hash when content is None


def test_safe_filename_with_hash():
    from media_handler import _safe_filename
    name = _safe_filename("https://example.com/image.png", b"content")
    assert name.endswith("-image.png")
    assert len(name) > len("image.png")


def test_safe_filename_no_extension():
    from media_handler import _safe_filename
    name = _safe_filename("https://example.com/path/media")
    assert name.endswith(".bin")


def test_safe_filename_strips_query():
    from media_handler import _safe_filename
    name = _safe_filename("https://example.com/img.jpg?w=800&h=600")
    assert "?" not in name
    assert name == "img.jpg"


def test_download_media_success(tmp_path):
    from media_handler import download_media
    mock_response = MagicMock()
    mock_response.headers = {"Content-Length": "100"}
    mock_response.iter_content.return_value = [b"fake image data"]
    mock_response.raise_for_status = MagicMock()

    with patch("media_handler.requests.get", return_value=mock_response), \
         patch("media_handler._validate_media_url"):
        path, size = download_media(
            "https://example.com/photo.jpg",
            tmp_path / "attachments",
        )
    assert path.exists()
    assert size == len(b"fake image data")
    assert path.suffix == ".jpg"


def test_download_media_too_large(tmp_path):
    from media_handler import download_media
    mock_response = MagicMock()
    mock_response.headers = {"Content-Length": str(100 * 1024 * 1024)}
    mock_response.raise_for_status = MagicMock()

    with patch("media_handler.requests.get", return_value=mock_response), \
         patch("media_handler._validate_media_url"):
        with pytest.raises(RuntimeError, match="too large"):
            download_media("https://example.com/huge.zip", tmp_path)


def test_copy_local_media(tmp_path):
    from media_handler import copy_local_media
    source = tmp_path / "source" / "photo.png"
    source.parent.mkdir()
    source.write_bytes(b"PNG data here")

    dest_dir = tmp_path / "attachments"
    path, size = copy_local_media(source, dest_dir)
    assert path.exists()
    assert path.name == "photo.png"
    assert size == 13


def test_copy_local_media_not_found(tmp_path):
    from media_handler import copy_local_media
    with pytest.raises(FileNotFoundError):
        copy_local_media(tmp_path / "nonexistent.png", tmp_path / "dest")


# ──────────────────────────────────────────────
# Markdown rewriting
# ──────────────────────────────────────────────

def test_rewrite_markdown_images(tmp_path):
    from media_handler import rewrite_markdown_images
    vault_root = tmp_path / "vault"
    local = vault_root / "Attachments" / "slug" / "img.png"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"PNG")

    md = "Text ![alt](https://example.com/img.png) more text"
    downloaded = {"https://example.com/img.png": local}

    result = rewrite_markdown_images(md, downloaded, vault_root)
    assert "![[Attachments/slug/img.png]]" in result
    assert "https://example.com/img.png" not in result


def test_rewrite_markdown_html_img(tmp_path):
    from media_handler import rewrite_markdown_images
    vault_root = tmp_path / "vault"
    local = vault_root / "Attachments" / "slug" / "img.jpg"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"JPEG")

    md = 'Text <img src="https://example.com/img.jpg" alt="photo" /> more'
    downloaded = {"https://example.com/img.jpg": local}

    result = rewrite_markdown_images(md, downloaded, vault_root)
    assert "![[Attachments/slug/img.jpg]]" in result


def test_rewrite_preserves_non_downloaded_images():
    from media_handler import rewrite_markdown_images
    md = "![keep](https://other.com/keep.png) and ![gone](https://example.com/gone.png)"
    downloaded = {}  # Nothing downloaded

    result = rewrite_markdown_images(md, downloaded, Path("/vault"))
    assert result == md


# ──────────────────────────────────────────────
# Frontmatter integration
# ──────────────────────────────────────────────

def test_inject_citations_into_frontmatter():
    from media_handler import inject_citations_into_frontmatter
    fm = '---\ntitle: "Test"\nsource: https://example.com\n---\n\n'
    citations = [{
        "source_url": "https://example.com/img.png",
        "local_path": "Attachments/slug/img.png",
        "media_type": "image",
        "accessed_at": "2026-02-26T12:00:00+00:00",
        "title": "Photo",
        "author": "",
    }]
    result = inject_citations_into_frontmatter(fm, citations)
    assert "media_assets:" in result
    assert "source_url: https://example.com/img.png" in result
    assert result.strip().endswith("---")


def test_inject_citations_empty():
    from media_handler import inject_citations_into_frontmatter
    fm = '---\ntitle: "Test"\n---\n\n'
    result = inject_citations_into_frontmatter(fm, [])
    assert result == fm


def test_append_sources_section_new():
    from media_handler import append_sources_section
    md = "# Article\n\nSome content here."
    citations = [{
        "source_url": "https://example.com/photo.jpg",
        "title": "Photo",
        "accessed_at": "2026-02-26T12:00:00+00:00",
    }]
    result = append_sources_section(md, citations)
    assert "## Sources" in result
    assert "[Photo](https://example.com/photo.jpg)" in result
    assert "accessed 2026-02-26" in result


def test_append_sources_section_existing():
    from media_handler import append_sources_section
    md = "# Article\n\nContent.\n\n## Sources\n\n- [Old](https://old.com)"
    citations = [{
        "source_url": "https://example.com/new.jpg",
        "title": "New",
        "accessed_at": "2026-02-26T12:00:00+00:00",
    }]
    result = append_sources_section(md, citations)
    # Should have both old and new sources
    assert "[Old](https://old.com)" in result
    assert "[New](https://example.com/new.jpg)" in result
    # Should not create a duplicate ## Sources header
    assert result.count("## Sources") == 1


def test_append_sources_empty():
    from media_handler import append_sources_section
    md = "# Article\n\nContent."
    result = append_sources_section(md, [])
    assert result == md


# ──────────────────────────────────────────────
# YouTube handling
# ──────────────────────────────────────────────

def test_check_ytdlp():
    from media_handler import _check_ytdlp
    # Just verify it returns a bool (result depends on system)
    assert isinstance(_check_ytdlp(), bool)


def test_fetch_youtube_metadata_no_ytdlp():
    from media_handler import fetch_youtube_metadata
    with patch("media_handler.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="yt-dlp not found"):
            fetch_youtube_metadata("https://www.youtube.com/watch?v=test123")


def test_fetch_youtube_metadata_success():
    from media_handler import fetch_youtube_metadata
    mock_info = {
        "id": "test123",
        "title": "Test Video",
        "description": "A test video",
        "thumbnail": "https://i.ytimg.com/vi/test123/maxresdefault.jpg",
        "duration": 300,
        "uploader": "Test Channel",
        "upload_date": "20260226",
    }
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(mock_info)

    with patch("media_handler.shutil.which", return_value="/usr/bin/yt-dlp"), \
         patch("media_handler.subprocess.run", return_value=mock_result):
        metadata = fetch_youtube_metadata("https://www.youtube.com/watch?v=test123")

    assert metadata["video_id"] == "test123"
    assert metadata["title"] == "Test Video"
    assert metadata["uploader"] == "Test Channel"
    assert metadata["duration"] == 300


def test_fetch_youtube_metadata_failure():
    from media_handler import fetch_youtube_metadata
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "ERROR: Video unavailable"

    with patch("media_handler.shutil.which", return_value="/usr/bin/yt-dlp"), \
         patch("media_handler.subprocess.run", return_value=mock_result):
        with pytest.raises(RuntimeError, match="yt-dlp failed"):
            fetch_youtube_metadata("https://www.youtube.com/watch?v=invalid")


# ──────────────────────────────────────────────
# Audio handling
# ──────────────────────────────────────────────

def test_process_audio_copy_only(tmp_path):
    from media_handler import process_audio
    source = tmp_path / "recording.mp3"
    source.write_bytes(b"fake mp3 data")
    attachments = tmp_path / "Attachments"

    with patch("media_handler._check_whisper", return_value=False):
        result = process_audio(source, attachments, "test-slug")

    assert Path(result["local_path"]).exists()
    assert result["file_size"] == 13
    assert result["transcript"] is None
    assert result["citation"]["media_type"] == "audio"


# ──────────────────────────────────────────────
# High-level extraction
# ──────────────────────────────────────────────

def test_extract_and_download_no_media(tmp_path):
    from media_handler import extract_and_download_media
    vault = tmp_path / "vault"
    vault.mkdir()
    attachments = vault / "Attachments"

    md = "# Plain Article\n\nNo images here."
    result_md, citations = extract_and_download_media(
        md, attachments, "test", vault,
    )
    assert result_md == md
    assert citations == []


def test_extract_and_download_with_images(tmp_path):
    from media_handler import extract_and_download_media
    vault = tmp_path / "vault"
    vault.mkdir()
    attachments = vault / "Attachments"

    md = "# Article\n\n![photo](https://example.com/photo.jpg)\n\nMore text."

    mock_response = MagicMock()
    mock_response.headers = {"Content-Length": "100"}
    mock_response.iter_content.return_value = [b"fake jpg"]
    mock_response.raise_for_status = MagicMock()

    with patch("media_handler.requests.get", return_value=mock_response), \
         patch("media_handler._validate_media_url"):
        result_md, citations = extract_and_download_media(
            md, attachments, "test", vault, "https://example.com/page",
        )

    assert len(citations) == 1
    assert citations[0]["media_type"] == "image"
    assert "![[Attachments/" in result_md
    assert "https://example.com/photo.jpg" not in result_md


def test_extract_and_download_handles_failure(tmp_path):
    from media_handler import extract_and_download_media
    vault = tmp_path / "vault"
    vault.mkdir()
    attachments = vault / "Attachments"

    md = "![broken](https://example.com/broken.jpg)"

    with patch("media_handler.download_media", side_effect=RuntimeError("network error")):
        result_md, citations = extract_and_download_media(
            md, attachments, "test", vault,
        )

    # Should not crash, just skip the broken image
    assert citations == []
    # Original markdown preserved for failed downloads
    assert "https://example.com/broken.jpg" in result_md


# ──────────────────────────────────────────────
# attach_media.py helpers
# Note: attach_media imports config at module level which is auto-generated.
# We mock it here to test standalone helper functions.
# ──────────────────────────────────────────────

@pytest.fixture
def mock_config():
    """Create a mock config module for attach_media imports."""
    mock_cfg = MagicMock()
    mock_cfg.VAULT_PATH = Path("/tmp/test-vault")
    mock_cfg.INBOX_PATH = Path("/tmp/test-vault/Inbox")
    mock_cfg.ATTACHMENTS_PATH = Path("/tmp/test-vault/Attachments")
    import sys as _sys
    _sys.modules["config"] = mock_cfg
    yield mock_cfg
    # Don't remove — other tests may need it


def test_split_frontmatter(mock_config):
    from attach_media import _split_frontmatter
    content = '---\ntitle: "Test"\ntags: [inbox]\n---\n\n# Body\n\nContent here.'
    fm, body = _split_frontmatter(content)
    assert fm.startswith("---")
    assert "title:" in fm
    assert body.startswith("# Body")


def test_split_frontmatter_none(mock_config):
    from attach_media import _split_frontmatter
    content = "# No Frontmatter\n\nJust content."
    fm, body = _split_frontmatter(content)
    assert fm == ""
    assert body == content


def test_note_slug(mock_config):
    from attach_media import _note_slug
    assert _note_slug(Path("2026-02-26-my-article.md")) == "2026-02-26-my-article"


def test_detect_media_type(mock_config):
    from attach_media import _detect_media_type
    assert _detect_media_type(Path("photo.jpg")) == "image"
    assert _detect_media_type(Path("video.mp4")) == "video"
    assert _detect_media_type(Path("audio.mp3")) == "audio"
    assert _detect_media_type(Path("doc.pdf")) == "file"


# ──────────────────────────────────────────────
# discover_vault.py — attachments detection
# ──────────────────────────────────────────────

def test_categorize_folder_attachments():
    from discover_vault import categorize_folder
    assert categorize_folder("Attachments") == "attachments"
    assert categorize_folder("assets") == "attachments"
    assert categorize_folder("Media") == "attachments"
    assert categorize_folder("images") == "attachments"


def test_categorize_folder_other():
    from discover_vault import categorize_folder
    assert categorize_folder("Research") is None
    assert categorize_folder("Projects") is None


def test_generate_env_includes_attachments():
    from discover_vault import generate_env_content
    env = generate_env_content(
        vault_path=Path("/vault"),
        inbox_path=Path("/vault/Inbox"),
        daily_path=None,
        mocs_path=None,
        output_path=None,
        attachments_path=Path("/vault/Attachments"),
        tagging_note_path=None,
        api_key="test-key",
        tag_format="list",
        date_format="%Y-%m-%d",
        frontmatter_fields=["title", "source"],
    )
    assert "ATTACHMENTS_PATH=/vault/Attachments" in env
