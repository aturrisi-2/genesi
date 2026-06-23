"""Video description core for Operational Memory (platform-independent).

Validates the core + the media_processor video branch:
  * valid video (describe_video mocked) → status video_analyzed, extracted_text set;
  * missing path → status missing, no crash;
  * describe_video raising → video_analysis_failed, no crash;
  * no frames → video_unavailable;
  * media_processor routes video → describer (not OCR), attachment carries text;
  * non-video media (image) unchanged → still OCR;
  * video description reaches the operational engine via event.extracted_text;
  * no log line carries the full description text.

describe_video / OCR mocked — no ffmpeg / no vision API call. No reply produced.
"""

from __future__ import annotations

import pytest

import core.operational_memory.video_describer as vd
import core.operational_memory.media_processor as mp
from core.operational_memory.chat_presence import _event_from_message
from core.operational_memory.models import ChatAttachment, ChatMessage


DESC = "video tecnico: ispezione giuntura metallica, testo 'da siliconare', area industriale"


# --------------------------------------------------------------------------- #
# Core describer
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_describe_valid_video(monkeypatch, tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    async def fake_describe(path):
        return {"description": DESC, "best_frame": "/tmp/f.jpg", "frames_count": 4}

    monkeypatch.setattr("core.video_vision_service.describe_video", fake_describe)
    out = await vd.describe_video_file(str(f), mime_type="video/mp4")
    assert out["video_status"] == "video_analyzed"
    assert out["text"] == DESC
    assert out["frames_count"] == 4


@pytest.mark.asyncio
async def test_describe_missing_path():
    out = await vd.describe_video_file("/nope/missing.mp4")
    assert out["video_status"] == "missing"
    assert out["text"] == ""


@pytest.mark.asyncio
async def test_describe_exception_failed(monkeypatch, tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"bytes")

    async def boom(path):
        raise RuntimeError("ffmpeg down")

    monkeypatch.setattr("core.video_vision_service.describe_video", boom)
    out = await vd.describe_video_file(str(f))
    assert out["video_status"] == "video_analysis_failed"
    assert "ffmpeg down" in out["error"]
    assert out["text"] == ""


@pytest.mark.asyncio
async def test_describe_no_frames_unavailable(monkeypatch, tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"bytes")

    async def fake_describe(path):
        return {"description": "", "best_frame": None, "frames_count": 0}

    monkeypatch.setattr("core.video_vision_service.describe_video", fake_describe)
    out = await vd.describe_video_file(str(f))
    assert out["video_status"] == "video_unavailable"


@pytest.mark.asyncio
async def test_describe_frames_no_description(monkeypatch, tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"bytes")

    async def fake_describe(path):
        return {"description": "", "best_frame": "/tmp/f.jpg", "frames_count": 3}

    monkeypatch.setattr("core.video_vision_service.describe_video", fake_describe)
    out = await vd.describe_video_file(str(f))
    assert out["video_status"] == "video_no_content"


# --------------------------------------------------------------------------- #
# media_processor routing
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_media_processor_routes_video(monkeypatch, tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"bytes")

    async def fake_describe(path, mime_type=None):
        return {"video_status": "video_analyzed", "text": DESC, "description": DESC,
                "frames_count": 4, "confidence": None, "error": ""}

    def boom_ocr(*a, **k):
        raise AssertionError("analyze_media must not run for video")

    monkeypatch.setattr(mp, "describe_video_file", fake_describe)
    monkeypatch.setattr(mp, "analyze_media", boom_ocr)

    att = await mp.analyze_attachment(
        str(f), media_type="video", mime_type="video/mp4", allowed_dirs=[str(tmp_path)])
    assert att.type == "video"
    assert att.extracted_text == DESC
    assert att.metadata["extraction_status"] == "video_analyzed"
    assert att.metadata["frames_count"] == 4


@pytest.mark.asyncio
async def test_media_processor_image_unchanged(monkeypatch, tmp_path):
    from core.operational_memory.media_analyzer import MediaAnalysisResult
    f = tmp_path / "scan.png"
    f.write_bytes(b"\x89PNG")

    def fake_ocr(path, type_hint=""):
        return MediaAnalysisResult(
            attachment_path=str(path), attachment_type="image", extracted_text="OCR",
            extraction_status="text_extracted", extraction_confidence="high",
            media_description="", metadata={})

    async def boom_video(path, mime_type=None):
        raise AssertionError("describer must not run for image")

    monkeypatch.setattr(mp, "analyze_media", fake_ocr)
    monkeypatch.setattr(mp, "describe_video_file", boom_video)

    att = await mp.analyze_attachment(
        str(f), media_type="image", mime_type="image/png", allowed_dirs=[str(tmp_path)])
    assert att.type == "image" and att.extracted_text == "OCR"


@pytest.mark.asyncio
async def test_media_processor_video_missing_file(monkeypatch, tmp_path):
    att = await mp.analyze_attachment(
        str(tmp_path / "gone.mp4"), media_type="video", mime_type="video/mp4",
        allowed_dirs=[str(tmp_path)])
    assert att.metadata["extraction_status"] == "file_missing"


# --------------------------------------------------------------------------- #
# Reaches the operational engine
# --------------------------------------------------------------------------- #


def test_video_description_becomes_operational_content():
    msg = ChatMessage(
        project_id="p", message_id="m1", source="whatsapp", text="",
        attachments=[ChatAttachment(type="video", extracted_text=DESC,
                                    metadata={"extraction_status": "video_analyzed"})],
    )
    event = _event_from_message(msg)
    assert event.extracted_text == DESC          # fed to extraction as content
    assert event.type == "document"              # video normalized to a valid event type


# --------------------------------------------------------------------------- #
# Privacy
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_description_never_logged(monkeypatch, tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"bytes")
    logged = []

    async def fake_describe(path):
        return {"description": DESC, "best_frame": None, "frames_count": 4}

    monkeypatch.setattr("core.video_vision_service.describe_video", fake_describe)
    monkeypatch.setattr(vd, "log", lambda event, **kw: logged.append((event, kw)))

    await vd.describe_video_file(str(f))
    for _event, kw in logged:
        for v in kw.values():
            assert DESC not in str(v), "video description leaked into a log line"
