"""Tests for fetch_media.py — media download and asset management."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, call


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


# ──────────────────────────────────────────────
# _extract_video_id tests
# ──────────────────────────────────────────────

def test_extract_video_id_youtube_watch():
    from fetch_media import _extract_video_id
    assert _extract_video_id("https://www.youtube.com/watch?v=abc123") == "abc123"


def test_extract_video_id_youtube_short():
    from fetch_media import _extract_video_id
    assert _extract_video_id("https://youtu.be/abc123") == "abc123"


def test_extract_video_id_vimeo():
    from fetch_media import _extract_video_id
    assert _extract_video_id("https://vimeo.com/123456") == "123456"


def test_extract_video_id_fallback():
    from fetch_media import _extract_video_id
    result = _extract_video_id("https://example.com/somevideo.mp4")
    assert result == "somevideo"


# ──────────────────────────────────────────────
# download_video tests
# ──────────────────────────────────────────────

def test_download_video_extracts_audio(tmp_path):
    from fetch_media import download_video
    assets_dir = tmp_path / "assets"

    def fake_run(cmd, **kwargs):
        # Simulate yt-dlp creating the output file
        target_dir = assets_dir / "test"
        target_dir.mkdir(parents=True, exist_ok=True)
        mp3_path = target_dir / "abc123.mp3"
        mp3_path.write_bytes(b"fake mp3 audio data")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("fetch_media.subprocess.run", side_effect=fake_run) as mock_run:
        result = download_video(
            url="https://youtube.com/watch?v=abc123",
            assets_dir=assets_dir,
            topic_slug="test",
        )
    assert mock_run.called
    # yt-dlp should be called with audio-only flags
    call_args = mock_run.call_args[0][0]
    assert call_args[0] == "yt-dlp"
    assert "-x" in call_args
    assert "--audio-format" in call_args
    assert "mp3" in call_args
    # Result should be valid
    assert result is not None
    assert result["url"] == "https://youtube.com/watch?v=abc123"
    assert result["type"] == "video"
    assert result["size_bytes"] == 19  # len(b"fake mp3 audio data")
    assert result["local_path"].endswith("abc123.mp3")


def test_download_video_writes_meta_sidecar(tmp_path):
    from fetch_media import download_video
    assets_dir = tmp_path / "assets"

    def fake_run(cmd, **kwargs):
        target_dir = assets_dir / "test"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "abc123.mp3").write_bytes(b"audio")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("fetch_media.subprocess.run", side_effect=fake_run):
        result = download_video(
            url="https://youtube.com/watch?v=abc123",
            assets_dir=assets_dir,
            topic_slug="test",
            run_id="run-42",
        )
    assert result is not None
    meta_path = assets_dir / "test" / "abc123.mp3.meta"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["source_url"] == "https://youtube.com/watch?v=abc123"
    assert meta["research_run"] == "run-42"
    assert meta["content_type"] == "audio/mpeg"
    assert "downloaded_at" in meta
    assert "size_bytes" in meta


def test_download_video_returns_none_on_ytdlp_failure(tmp_path):
    from fetch_media import download_video
    with patch("fetch_media.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = download_video(
            url="https://youtube.com/watch?v=abc123",
            assets_dir=tmp_path / "assets",
            topic_slug="test",
        )
    assert result is None


def test_download_video_returns_none_on_exception(tmp_path):
    from fetch_media import download_video
    with patch("fetch_media.subprocess.run", side_effect=Exception("boom")):
        result = download_video(
            url="https://youtube.com/watch?v=abc123",
            assets_dir=tmp_path / "assets",
            topic_slug="test",
        )
    assert result is None


def test_download_video_returns_none_when_no_output_file(tmp_path):
    from fetch_media import download_video
    with patch("fetch_media.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        # yt-dlp succeeds but no file is written
        result = download_video(
            url="https://youtube.com/watch?v=abc123",
            assets_dir=tmp_path / "assets",
            topic_slug="test",
        )
    assert result is None


def test_download_video_youtu_be(tmp_path):
    from fetch_media import download_video
    assets_dir = tmp_path / "assets"

    def fake_run(cmd, **kwargs):
        target_dir = assets_dir / "test"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "xyz789.mp3").write_bytes(b"audio")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("fetch_media.subprocess.run", side_effect=fake_run):
        result = download_video(
            url="https://youtu.be/xyz789",
            assets_dir=assets_dir,
            topic_slug="test",
        )
    assert result is not None
    assert result["local_path"].endswith("xyz789.mp3")


def test_download_video_vimeo(tmp_path):
    from fetch_media import download_video
    assets_dir = tmp_path / "assets"

    def fake_run(cmd, **kwargs):
        target_dir = assets_dir / "test"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "999888.mp3").write_bytes(b"audio")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("fetch_media.subprocess.run", side_effect=fake_run):
        result = download_video(
            url="https://vimeo.com/999888",
            assets_dir=assets_dir,
            topic_slug="test",
        )
    assert result is not None
    assert result["local_path"].endswith("999888.mp3")


# ──────────────────────────────────────────────
# transcribe_audio tests
# ──────────────────────────────────────────────

def test_transcribe_audio_calls_whisper(tmp_path):
    from fetch_media import transcribe_audio
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake audio")

    def fake_run(cmd, **kwargs):
        # Simulate whisper creating the output .txt file
        txt_path = tmp_path / "audio.txt"
        txt_path.write_text("Transcribed text here", encoding="utf-8")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("fetch_media.subprocess.run", side_effect=fake_run) as mock_run:
        result = transcribe_audio(audio_file)
    assert result == "Transcribed text here"
    assert mock_run.called
    call_args = mock_run.call_args[0][0]
    assert call_args[0] == "whisper"
    assert "--output_format" in call_args
    assert "txt" in call_args


def test_transcribe_audio_with_custom_model(tmp_path):
    from fetch_media import transcribe_audio
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake audio")

    def fake_run(cmd, **kwargs):
        txt_path = tmp_path / "audio.txt"
        txt_path.write_text("transcript", encoding="utf-8")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("fetch_media.subprocess.run", side_effect=fake_run) as mock_run:
        result = transcribe_audio(audio_file, model="large")
    assert result == "transcript"
    call_args = mock_run.call_args[0][0]
    assert "--model" in call_args
    model_idx = call_args.index("--model")
    assert call_args[model_idx + 1] == "large"


def test_transcribe_audio_returns_none_on_whisper_failure(tmp_path):
    from fetch_media import transcribe_audio
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake audio")
    with patch("fetch_media.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = transcribe_audio(audio_file)
    assert result is None


def test_transcribe_audio_returns_none_on_exception(tmp_path):
    from fetch_media import transcribe_audio
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake audio")
    with patch("fetch_media.subprocess.run", side_effect=Exception("boom")):
        result = transcribe_audio(audio_file)
    assert result is None


def test_transcribe_audio_returns_none_when_file_missing():
    from fetch_media import transcribe_audio
    result = transcribe_audio(Path("/nonexistent/audio.mp3"))
    assert result is None


def test_transcribe_audio_returns_none_when_no_output(tmp_path):
    from fetch_media import transcribe_audio
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake audio")
    with patch("fetch_media.subprocess.run") as mock_run:
        # Whisper succeeds but no .txt file is written
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = transcribe_audio(audio_file)
    assert result is None


def test_transcribe_audio_returns_none_for_empty_transcript(tmp_path):
    from fetch_media import transcribe_audio
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake audio")

    def fake_run(cmd, **kwargs):
        txt_path = tmp_path / "audio.txt"
        txt_path.write_text("   \n  ", encoding="utf-8")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("fetch_media.subprocess.run", side_effect=fake_run):
        result = transcribe_audio(audio_file)
    assert result is None
