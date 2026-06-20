from __future__ import annotations

import asyncio

import pytest

from core.operational_memory.media_analyzer import MediaAnalysisResult, dependency_status
from core.operational_memory.media_processor import analyze_attachment
from core.operational_memory.models import ChatAttachment


def _fake_result(text="ROOM 12 READY", atype="image", status="text_extracted"):
    return MediaAnalysisResult(
        attachment_path="x",
        attachment_type=atype,
        extracted_text=text,
        media_description=f"{atype} analizzato",
        extraction_status=status,
        extraction_confidence="high" if text else "low",
        metadata={"file_name": "f", "size_bytes": 10},
    )


@pytest.mark.asyncio
async def test_analyze_attachment_image_with_text(monkeypatch, tmp_path):
    # Deterministic unit: mock the analyzer to return OCR text.
    import core.operational_memory.media_processor as mp
    f = tmp_path / "img.png"
    f.write_bytes(b"fake")
    monkeypatch.setattr(mp, "analyze_media", lambda p: _fake_result("ROOM 12 READY"))
    att = await analyze_attachment(str(f), media_type="image", filename="img.png")
    assert isinstance(att, ChatAttachment)
    assert att.type == "image"
    assert att.extracted_text == "ROOM 12 READY"
    assert att.metadata["extraction_status"] == "text_extracted"


@pytest.mark.asyncio
async def test_analyze_attachment_uses_to_thread(monkeypatch, tmp_path):
    import core.operational_memory.media_processor as mp
    f = tmp_path / "img.png"
    f.write_bytes(b"fake")
    called = {}

    async def fake_to_thread(fn, *a, **k):
        called["used"] = True
        return fn(*a, **k)

    monkeypatch.setattr(mp.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(mp, "analyze_media", lambda p: _fake_result("X"))
    att = await analyze_attachment(str(f), media_type="image")
    assert called.get("used") is True       # ran off the event loop
    assert att.extracted_text == "X"


@pytest.mark.asyncio
async def test_analyze_attachment_pdf_placeholder_or_text(tmp_path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-1.4\n%minimal\n")
    att = await analyze_attachment(str(f), media_type="pdf")
    assert att.type == "pdf"
    # On a host without a PDF text extractor this stays a stable placeholder,
    # never a crash; with one it may carry text.
    assert "extraction_status" in att.metadata


@pytest.mark.asyncio
async def test_unprocessable_media_returns_placeholder(tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"\x00\x00\x00")
    att = await analyze_attachment(str(f), media_type="video")
    assert isinstance(att, ChatAttachment)
    assert att.extracted_text is None
    assert att.metadata.get("extraction_status") in {"ignored", "unsupported"}


@pytest.mark.asyncio
async def test_ocr_failure_does_not_block_or_raise(monkeypatch, tmp_path):
    import core.operational_memory.media_processor as mp
    f = tmp_path / "img.png"
    f.write_bytes(b"fake")

    def boom(p):
        raise RuntimeError("tesseract exploded")

    monkeypatch.setattr(mp, "analyze_media", boom)
    att = await analyze_attachment(str(f), media_type="image")
    assert att.metadata["extraction_status"] == "analysis_error"
    assert "tesseract exploded" in att.metadata["ocr_error"]
    assert att.extracted_text is None


@pytest.mark.asyncio
async def test_attachment_metadata_preserved(monkeypatch, tmp_path):
    import core.operational_memory.media_processor as mp
    f = tmp_path / "img.png"
    f.write_bytes(b"fake")
    monkeypatch.setattr(mp, "analyze_media", lambda p: _fake_result("X"))
    att = await analyze_attachment(
        str(f), media_type="image", filename="img.png", mime_type="image/png",
        message_id="m1", platform="generic",
    )
    for key, val in [("filename", "img.png"), ("mime_type", "image/png"),
                     ("message_id", "m1"), ("platform", "generic")]:
        assert att.metadata[key] == val


@pytest.mark.asyncio
async def test_path_traversal_rejected():
    att = await analyze_attachment("../../etc/passwd", media_type="image", allowed_dirs=["/tmp"])
    assert att.metadata["extraction_status"] == "rejected_path"
    assert att.metadata["path_error"] == "parent_traversal"
    assert att.extracted_text is None


@pytest.mark.asyncio
async def test_outside_allowed_dirs_rejected(tmp_path):
    f = tmp_path / "img.png"
    f.write_bytes(b"fake")
    att = await analyze_attachment(str(f), media_type="image", allowed_dirs=["/nonexistent-allowed"])
    assert att.metadata["extraction_status"] == "rejected_path"


@pytest.mark.asyncio
async def test_missing_file_returns_placeholder():
    att = await analyze_attachment("/tmp/does-not-exist-12345.png", media_type="image")
    assert att.metadata["extraction_status"] == "file_missing"
    assert att.extracted_text is None


@pytest.mark.asyncio
async def test_chat_attachment_mapping(monkeypatch, tmp_path):
    # The result must drop straight into the Operational Memory event mapping.
    import core.operational_memory.media_processor as mp
    from core.operational_memory.chat_presence import _event_from_message
    from core.operational_memory.models import ChatMessage
    f = tmp_path / "img.png"
    f.write_bytes(b"fake")
    monkeypatch.setattr(mp, "analyze_media", lambda p: _fake_result("DELIVERY DONE"))
    att = await analyze_attachment(str(f), media_type="image")
    msg = ChatMessage(project_id="p", message_id="e1", text="", attachments=[att])
    event = _event_from_message(msg)
    assert event.type == "image"
    assert event.extracted_text == "DELIVERY DONE"   # OCR text flows into the event


@pytest.mark.asyncio
async def test_media_processor_default_has_no_live_side_effects():
    # No file → placeholder, no exception, nothing sent.
    att = await analyze_attachment(None, media_type="image")
    assert att.metadata["extraction_status"] == "no_file"
    # Module must not import any platform adapter / transport.
    import core.operational_memory.media_processor as mp
    src = open(mp.__file__, "r", encoding="utf-8").read().lower()
    for forbidden in ["whatsapp_operational", "telegram_operational", "send_message", "whatsapp_bot", "telegram_bot"]:
        assert forbidden not in src


@pytest.mark.asyncio
@pytest.mark.skipif(not dependency_status().get("pytesseract_binary"), reason="tesseract not available")
async def test_real_ocr_image_optional(tmp_path):
    # Integration: real OCR path must not crash and must yield a valid status.
    from PIL import Image, ImageDraw
    f = tmp_path / "real.png"
    img = Image.new("RGB", (600, 200), "white")
    ImageDraw.Draw(img).text((20, 80), "ROOM 12 READY", fill="black")
    img.save(f)
    att = await analyze_attachment(str(f), media_type="image")
    assert att.type == "image"
    assert att.metadata["extraction_status"] in {"text_extracted", "no_text_found", "ocr_unavailable"}


def test_no_platform_domain_hardcoding_media_processor():
    import re
    import core.operational_memory.media_processor as mp
    import core.operational_memory.media_analyzer as ma
    forbidden = ["test tab", "tab cefla", "cantiere", "corridoio", "pane", "quadro elettrico", "whatsapp", "telegram"]
    for mod in (mp, ma):
        body = open(mod.__file__, "r", encoding="utf-8").read().lower()
        for token in forbidden:
            assert not re.search(rf"\b{re.escape(token)}\b", body), f"hardcoded '{token}' in {mod.__name__}"
