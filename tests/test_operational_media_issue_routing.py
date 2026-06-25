"""Media issue routing: photo OCR weak → vision fallback; media-trigger phrases
are not operational items; technical issues are accepted.

Generic (no V27/Cefla token). analyze_media / describe_image mocked — no OCR/vision
API calls. No env/live.
"""

from __future__ import annotations

import pytest

import core.operational_memory.media_processor as mp
from core.operational_memory.image_describer import _looks_weak_ocr
from core.operational_memory.quality import classify_ingest
from core.operational_memory.models import Issue, OperationalTask


VISION = "Foto valvola: codice V27 LO FC FREDDO, manca manopola valvola di bilanciamento DN 32"


# --------------------------------------------------------------------------- #
# weak-OCR heuristic
# --------------------------------------------------------------------------- #


def test_weak_ocr_detects_garbage():
    assert _looks_weak_ocr("lo) Qa a 7 LJ ac SUL IU qll i O") is True
    assert _looks_weak_ocr("") is True
    assert _looks_weak_ocr("V27 LO FC FREDDO manca manopola valvola bilanciamento DN 32") is False


# --------------------------------------------------------------------------- #
# media_processor: weak image OCR → vision fallback
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_weak_image_ocr_falls_back_to_vision(monkeypatch, tmp_path):
    from core.operational_memory.media_analyzer import MediaAnalysisResult
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"\xff\xd8\xff")

    def garbage_ocr(path, type_hint=""):
        return MediaAnalysisResult(
            attachment_path=str(path), attachment_type="image",
            extracted_text="lo) Qa a 7 LJ ac SUL",  # garbage
            extraction_status="text_extracted", extraction_confidence="low",
            media_description="", metadata={})

    async def fake_vision(path):
        return {"image_status": "image_described", "text": VISION, "description": VISION, "error": ""}

    monkeypatch.setattr(mp, "analyze_media", garbage_ocr)
    monkeypatch.setattr(mp, "describe_image_file", fake_vision)

    att = await mp.analyze_attachment(str(f), media_type="image", mime_type="image/jpeg",
                                      allowed_dirs=[str(tmp_path)])
    assert att.type == "image"
    assert att.extracted_text == VISION                      # vision text used
    assert att.metadata["extraction_status"] == "vision_described"
    assert att.metadata.get("ocr_fallback") == "vision"


@pytest.mark.asyncio
async def test_strong_image_ocr_keeps_ocr(monkeypatch, tmp_path):
    from core.operational_memory.media_analyzer import MediaAnalysisResult
    f = tmp_path / "scan.png"
    f.write_bytes(b"\x89PNG")
    strong = "Verbale collaudo quadro QF-01 sala tecnica piano -1 conforme"

    def ocr(path, type_hint=""):
        return MediaAnalysisResult(attachment_path=str(path), attachment_type="image",
                                   extracted_text=strong, extraction_status="text_extracted",
                                   extraction_confidence="high", media_description="", metadata={})

    async def boom_vision(path):
        raise AssertionError("vision must not run when OCR is strong")

    monkeypatch.setattr(mp, "analyze_media", ocr)
    monkeypatch.setattr(mp, "describe_image_file", boom_vision)
    att = await mp.analyze_attachment(str(f), media_type="image", mime_type="image/png",
                                      allowed_dirs=[str(tmp_path)])
    assert att.extracted_text == strong
    assert att.metadata["extraction_status"] == "text_extracted"


# --------------------------------------------------------------------------- #
# media-trigger phrases are not operational items
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("phrase", [
    "Analizza questa immagine.", "Guarda questo video", "Ascolta questo audio",
])
def test_media_trigger_ignored(phrase):
    d, r = classify_ingest(OperationalTask(id="t", text=phrase, source="m"), "task")
    assert d == "ignored" and r == "media_trigger"


def test_real_issue_with_trigger_word_not_ignored():
    # A real operational sentence that merely starts with a verb is NOT a trigger.
    issue = Issue(id="i", text="manca manopola valvola di bilanciamento DN 32 su V27 LO FC FREDDO", source="m")
    d, r = classify_ingest(issue, "issue")
    assert d == "accepted"


def test_technical_issue_accepted():
    issue = Issue(id="i", text="V27 LO FC FREDDO manca manopola DN 32", source="m")
    d, r = classify_ingest(issue, "issue")
    assert d == "accepted"
