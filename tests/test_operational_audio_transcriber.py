"""T-A1 — Audio/voice transcription core for Operational Memory.

Validates the platform-independent core + the media_processor audio branch:
  * valid audio (analyze_audio mocked) → status transcribed, extracted_text set;
  * missing path → status missing, no crash;
  * analyze_audio raising → status failed, no crash;
  * non-audio media unchanged (still OCR/document path);
  * audio routing in media_processor produces a ChatAttachment with extracted_text;
  * the transcription reaches the operational engine via event.extracted_text;
  * no log line carries the full transcription text.

No env / restart / live. No bridge changes (those are T-A2).
"""

from __future__ import annotations

import asyncio

import pytest

import core.operational_memory.audio_transcriber as at
import core.operational_memory.media_processor as mp
from core.operational_memory.chat_presence import _event_from_message
from core.operational_memory.models import ChatAttachment, ChatMessage


SECRET = "consegnare il quadro elettrico al cantiere entro venerdì"


def _analysis(transcription=None, kind="speech", language="it", description="desc"):
    return {
        "kind": kind,
        "language": language,
        "transcription": transcription,
        "translation_it": None,
        "description": description,
    }


# --------------------------------------------------------------------------- #
# Core transcriber
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_transcribe_valid_audio_sets_text(monkeypatch, tmp_path):
    f = tmp_path / "voice.ogg"
    f.write_bytes(b"OggS-fake-bytes")

    async def fake_analyze(audio_bytes, content_type="audio/ogg"):
        assert audio_bytes == b"OggS-fake-bytes"
        return _analysis(transcription=SECRET)

    monkeypatch.setattr("core.audio_analysis_service.analyze_audio", fake_analyze)
    out = await at.transcribe_audio_file(str(f), mime_type="audio/ogg")
    assert out["transcription_status"] == "transcribed"
    assert out["text"] == SECRET
    assert out["language"] == "it"


@pytest.mark.asyncio
async def test_transcribe_missing_path():
    out = await at.transcribe_audio_file("/nope/missing.ogg")
    assert out["transcription_status"] == "missing"
    assert out["text"] == ""


@pytest.mark.asyncio
async def test_transcribe_empty_file(tmp_path):
    f = tmp_path / "empty.ogg"
    f.write_bytes(b"")
    out = await at.transcribe_audio_file(str(f))
    assert out["transcription_status"] == "missing"


@pytest.mark.asyncio
async def test_transcribe_analyze_exception_is_failed(monkeypatch, tmp_path):
    f = tmp_path / "voice.ogg"
    f.write_bytes(b"bytes")

    async def boom(audio_bytes, content_type="audio/ogg"):
        raise RuntimeError("stt down")

    monkeypatch.setattr("core.audio_analysis_service.analyze_audio", boom)
    out = await at.transcribe_audio_file(str(f))
    assert out["transcription_status"] == "failed"
    assert "stt down" in out["error"]
    assert out["text"] == ""


@pytest.mark.asyncio
async def test_transcribe_no_speech(monkeypatch, tmp_path):
    f = tmp_path / "music.ogg"
    f.write_bytes(b"bytes")

    async def fake_analyze(audio_bytes, content_type="audio/ogg"):
        return _analysis(transcription=None, kind="music", language=None, description="jazz")

    monkeypatch.setattr("core.audio_analysis_service.analyze_audio", fake_analyze)
    out = await at.transcribe_audio_file(str(f))
    assert out["transcription_status"] == "no_speech"
    assert out["text"] == ""


@pytest.mark.asyncio
async def test_transcribe_unavailable(monkeypatch, tmp_path):
    f = tmp_path / "x.ogg"
    f.write_bytes(b"bytes")

    async def fake_analyze(audio_bytes, content_type="audio/ogg"):
        return {"kind": "unknown", "language": None, "transcription": None,
                "translation_it": None, "description": ""}

    monkeypatch.setattr("core.audio_analysis_service.analyze_audio", fake_analyze)
    out = await at.transcribe_audio_file(str(f))
    assert out["transcription_status"] == "unavailable"


# --------------------------------------------------------------------------- #
# media_processor audio routing
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_media_processor_routes_audio_to_transcriber(monkeypatch, tmp_path):
    f = tmp_path / "ptt.ogg"
    f.write_bytes(b"bytes")

    async def fake_transcribe(path, mime_type=None):
        return {"transcription_status": "transcribed", "text": SECRET, "confidence": None,
                "language": "it", "kind": "speech", "description": "", "error": ""}

    # Guard: OCR must NOT be invoked for audio.
    def boom_ocr(*a, **k):
        raise AssertionError("analyze_media must not run for audio")

    monkeypatch.setattr(mp, "transcribe_audio_file", fake_transcribe)
    monkeypatch.setattr(mp, "analyze_media", boom_ocr)

    att = await mp.analyze_attachment(
        str(f), media_type="voice", mime_type="audio/ogg",
        allowed_dirs=[str(tmp_path)])
    assert isinstance(att, ChatAttachment)
    assert att.type == "voice"
    assert att.extracted_text == SECRET
    assert att.metadata["extraction_status"] == "transcribed"


@pytest.mark.asyncio
async def test_media_processor_non_audio_unchanged(monkeypatch, tmp_path):
    from core.operational_memory.media_analyzer import MediaAnalysisResult
    f = tmp_path / "scan.png"
    f.write_bytes(b"\x89PNG")

    def fake_ocr(path, type_hint=""):
        return MediaAnalysisResult(
            attachment_path=str(path), attachment_type="image", extracted_text="OCR TEXT",
            extraction_status="text_extracted", extraction_confidence="high",
            media_description="", metadata={})

    # Guard: transcriber must NOT run for images.
    async def boom_audio(path, mime_type=None):
        raise AssertionError("transcriber must not run for image")

    monkeypatch.setattr(mp, "analyze_media", fake_ocr)
    monkeypatch.setattr(mp, "transcribe_audio_file", boom_audio)

    att = await mp.analyze_attachment(
        str(f), media_type="image", mime_type="image/png", allowed_dirs=[str(tmp_path)])
    assert att.type == "image"
    assert att.extracted_text == "OCR TEXT"


@pytest.mark.asyncio
async def test_media_processor_audio_missing_file_no_crash(monkeypatch, tmp_path):
    # Absent file → media_processor's own file_missing placeholder (transcriber not reached).
    att = await mp.analyze_attachment(
        str(tmp_path / "gone.ogg"), media_type="voice", mime_type="audio/ogg",
        allowed_dirs=[str(tmp_path)])
    assert att.metadata["extraction_status"] == "file_missing"


# --------------------------------------------------------------------------- #
# Transcription reaches the operational engine
# --------------------------------------------------------------------------- #


def test_transcribed_text_becomes_operational_content():
    msg = ChatMessage(
        project_id="p", message_id="m1", source="whatsapp", text="",
        attachments=[ChatAttachment(type="voice", extracted_text=SECRET,
                                    metadata={"extraction_status": "transcribed"})],
    )
    event = _event_from_message(msg)
    # extracted_text is what watcher_engine feeds to extraction as content.
    assert event.extracted_text == SECRET


# --------------------------------------------------------------------------- #
# Privacy: transcription text never logged
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_full_transcription_never_logged(monkeypatch, tmp_path):
    f = tmp_path / "v.ogg"
    f.write_bytes(b"bytes")
    logged = []

    async def fake_analyze(audio_bytes, content_type="audio/ogg"):
        return _analysis(transcription=SECRET)

    monkeypatch.setattr("core.audio_analysis_service.analyze_audio", fake_analyze)
    monkeypatch.setattr(at, "log", lambda event, **kw: logged.append((event, kw)))

    await at.transcribe_audio_file(str(f))
    for _event, kw in logged:
        for v in kw.values():
            assert SECRET not in str(v), "transcription text leaked into a log line"
