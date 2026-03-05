"""Tests for fetch_media.py — media download and asset management."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_extract_media_refs_finds_images():
    from fetch_media import extract_media_refs
    content = "Some text ![img](https://example.com/photo.jpg) and more"
    refs = extract_media_refs(content)
    assert len(refs) == 1
    assert refs[0]["url"] == "https://example.com/photo.jpg"
    assert refs[0]["type"] == "image"


def test_extract_media_refs_finds_bare_image_urls():
    from fetch_media import extract_media_refs
    content = "Check out https://example.com/diagram.png for details"
    refs = extract_media_refs(content)
    assert len(refs) == 1
    assert refs[0]["url"] == "https://example.com/diagram.png"
    assert refs[0]["type"] == "image"


def test_extract_media_refs_finds_pdfs():
    from fetch_media import extract_media_refs
    content = "See the [report](https://example.com/report.pdf) for details"
    refs = extract_media_refs(content)
    assert len(refs) == 1
    assert refs[0]["type"] == "document"


def test_extract_media_refs_finds_youtube():
    from fetch_media import extract_media_refs
    content = "Watch [video](https://www.youtube.com/watch?v=abc123)"
    refs = extract_media_refs(content)
    assert len(refs) == 1
    assert refs[0]["type"] == "video"


def test_extract_media_refs_finds_youtu_be():
    from fetch_media import extract_media_refs
    content = "Watch [video](https://youtu.be/abc123)"
    refs = extract_media_refs(content)
    assert len(refs) == 1
    assert refs[0]["type"] == "video"


def test_extract_media_refs_finds_vimeo():
    from fetch_media import extract_media_refs
    content = "Watch [video](https://vimeo.com/123456)"
    refs = extract_media_refs(content)
    assert len(refs) == 1
    assert refs[0]["type"] == "video"


def test_extract_media_refs_finds_video_files():
    from fetch_media import extract_media_refs
    content = "Watch [clip](https://example.com/clip.mp4)"
    refs = extract_media_refs(content)
    assert len(refs) == 1
    assert refs[0]["type"] == "video"


def test_extract_media_refs_skips_blocked_types():
    from fetch_media import extract_media_refs
    content = "Download [file](https://example.com/malware.exe)"
    refs = extract_media_refs(content)
    assert len(refs) == 0


def test_extract_media_refs_skips_zip():
    from fetch_media import extract_media_refs
    content = "Download [archive](https://example.com/data.zip)"
    refs = extract_media_refs(content)
    assert len(refs) == 0


def test_extract_media_refs_skips_docx():
    from fetch_media import extract_media_refs
    content = "See [doc](https://example.com/notes.docx)"
    refs = extract_media_refs(content)
    assert len(refs) == 0


def test_extract_media_refs_skips_msi():
    from fetch_media import extract_media_refs
    content = "Install [setup](https://example.com/setup.msi)"
    refs = extract_media_refs(content)
    assert len(refs) == 0


def test_extract_media_refs_deduplicates():
    from fetch_media import extract_media_refs
    content = (
        "![img](https://example.com/photo.jpg) and again "
        "![img2](https://example.com/photo.jpg)"
    )
    refs = extract_media_refs(content)
    assert len(refs) == 1


def test_extract_media_refs_multiple_types():
    from fetch_media import extract_media_refs
    content = (
        "![img](https://example.com/photo.jpg)\n"
        "[report](https://example.com/report.pdf)\n"
        "[video](https://www.youtube.com/watch?v=abc123)"
    )
    refs = extract_media_refs(content)
    types = {r["type"] for r in refs}
    assert types == {"image", "document", "video"}


def test_extract_media_refs_all_image_extensions():
    from fetch_media import extract_media_refs
    extensions = ["png", "jpg", "jpeg", "gif", "svg", "webp"]
    for ext in extensions:
        content = f"![img](https://example.com/photo.{ext})"
        refs = extract_media_refs(content)
        assert len(refs) == 1, f"Failed for .{ext}"
        assert refs[0]["type"] == "image", f"Wrong type for .{ext}"


def test_download_media_saves_file_and_meta(tmp_path):
    from fetch_media import download_media_file
    mock_resp = MagicMock()
    mock_resp.headers = {"content-length": "1000", "content-type": "image/png"}
    mock_resp.iter_content = MagicMock(return_value=[b"fake image data"])
    mock_resp.raise_for_status = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("fetch_media.requests.get", return_value=mock_resp):
        result = download_media_file(
            url="https://example.com/photo.png",
            assets_dir=tmp_path / "assets",
            topic_slug="test-topic",
            run_id="test-run",
        )
    assert result is not None
    assert result["url"] == "https://example.com/photo.png"
    assert result["size_bytes"] == 15  # len(b"fake image data")
    assert result["type"] == "image"
    assert (tmp_path / "assets" / "test-topic" / "photo.png").exists()
    meta_file = tmp_path / "assets" / "test-topic" / "photo.png.meta"
    assert meta_file.exists()
    meta = json.loads(meta_file.read_text())
    assert meta["source_url"] == "https://example.com/photo.png"
    assert meta["research_run"] == "test-run"
    assert meta["content_type"] == "image/png"
    assert "downloaded_at" in meta
    assert "size_bytes" in meta


def test_download_media_skips_oversized(tmp_path):
    from fetch_media import download_media_file
    mock_resp = MagicMock()
    mock_resp.headers = {"content-length": str(20 * 1024 * 1024), "content-type": "image/png"}
    mock_resp.raise_for_status = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("fetch_media.requests.get", return_value=mock_resp):
        result = download_media_file(
            url="https://example.com/huge.png",
            assets_dir=tmp_path / "assets",
            topic_slug="test",
            run_id="test-run",
            max_size_bytes=10 * 1024 * 1024,
        )
    assert result is None


def test_download_media_handles_missing_content_length(tmp_path):
    from fetch_media import download_media_file
    mock_resp = MagicMock()
    mock_resp.headers = {"content-type": "image/png"}  # No content-length
    mock_resp.iter_content = MagicMock(return_value=[b"data"])
    mock_resp.raise_for_status = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("fetch_media.requests.get", return_value=mock_resp):
        result = download_media_file(
            url="https://example.com/photo.png",
            assets_dir=tmp_path / "assets",
            topic_slug="test-topic",
            run_id="test-run",
        )
    assert result is not None
    assert (tmp_path / "assets" / "test-topic" / "photo.png").exists()


def test_download_media_handles_request_error(tmp_path):
    from fetch_media import download_media_file
    with patch("fetch_media.requests.get", side_effect=Exception("Network error")):
        result = download_media_file(
            url="https://example.com/photo.png",
            assets_dir=tmp_path / "assets",
            topic_slug="test-topic",
            run_id="test-run",
        )
    assert result is None


def test_download_media_returns_correct_local_path(tmp_path):
    from fetch_media import download_media_file
    mock_resp = MagicMock()
    mock_resp.headers = {"content-length": "100", "content-type": "application/pdf"}
    mock_resp.iter_content = MagicMock(return_value=[b"pdf data"])
    mock_resp.raise_for_status = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("fetch_media.requests.get", return_value=mock_resp):
        result = download_media_file(
            url="https://example.com/report.pdf",
            assets_dir=tmp_path / "assets",
            topic_slug="my-topic",
            run_id="run-1",
        )
    assert result is not None
    expected_path = str(tmp_path / "assets" / "my-topic" / "report.pdf")
    assert result["local_path"] == expected_path


def test_rewrite_media_refs_updates_content():
    from fetch_media import rewrite_media_refs
    content = "See ![img](https://example.com/photo.png) here"
    manifest = [{"url": "https://example.com/photo.png",
                 "local_path": "assets/topic/photo.png"}]
    updated = rewrite_media_refs(content, manifest)
    assert "![[assets/topic/photo.png]]" in updated
    assert "https://example.com/photo.png" not in updated


def test_rewrite_media_refs_handles_markdown_links():
    from fetch_media import rewrite_media_refs
    content = "See the [report](https://example.com/report.pdf) for details"
    manifest = [{"url": "https://example.com/report.pdf",
                 "local_path": "assets/topic/report.pdf"}]
    updated = rewrite_media_refs(content, manifest)
    assert "![[assets/topic/report.pdf]]" in updated
    assert "https://example.com/report.pdf" not in updated


def test_rewrite_media_refs_multiple_replacements():
    from fetch_media import rewrite_media_refs
    content = (
        "![a](https://example.com/a.png) and "
        "![b](https://example.com/b.jpg)"
    )
    manifest = [
        {"url": "https://example.com/a.png", "local_path": "assets/topic/a.png"},
        {"url": "https://example.com/b.jpg", "local_path": "assets/topic/b.jpg"},
    ]
    updated = rewrite_media_refs(content, manifest)
    assert "![[assets/topic/a.png]]" in updated
    assert "![[assets/topic/b.jpg]]" in updated
    assert "https://example.com/a.png" not in updated
    assert "https://example.com/b.jpg" not in updated


def test_rewrite_media_refs_no_manifest():
    from fetch_media import rewrite_media_refs
    content = "See ![img](https://example.com/photo.png) here"
    updated = rewrite_media_refs(content, [])
    assert updated == content


def test_rewrite_media_refs_preserves_non_media_content():
    from fetch_media import rewrite_media_refs
    content = "# Title\n\nSome text\n\n![img](https://example.com/photo.png)\n\nMore text"
    manifest = [{"url": "https://example.com/photo.png",
                 "local_path": "assets/topic/photo.png"}]
    updated = rewrite_media_refs(content, manifest)
    assert "# Title" in updated
    assert "Some text" in updated
    assert "More text" in updated
    assert "![[assets/topic/photo.png]]" in updated
