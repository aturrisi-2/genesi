from __future__ import annotations

import pytest

from core.operational_memory.media_analyzer import MediaAnalysisResult
from core.operational_memory.media_processor import analyze_attachment
from core.operational_memory.models import ChatAttachment


def _media_result(
    *,
    text: str = "",
    description: str = "",
    status: str = "no_text_found",
    attachment_type: str = "image",
) -> MediaAnalysisResult:
    return MediaAnalysisResult(
        attachment_path="fixture",
        attachment_type=attachment_type,
        extracted_text=text,
        media_description=description,
        extraction_status=status,
        extraction_confidence="high" if text else "low",
        metadata={"source": "contract"},
    )


@pytest.mark.asyncio
async def test_media_contract_success_fields_are_stable(monkeypatch, tmp_path):
    import core.operational_memory.media_processor as mp

    media = tmp_path / "image.bin"
    media.write_bytes(b"fake image")
    monkeypatch.setattr(mp, "_looks_weak_ocr", lambda _text: False)
    monkeypatch.setattr(
        mp,
        "analyze_media",
        lambda _path, _hint="": _media_result(
            text="seriale 123",
            description="foto con etichetta leggibile",
            status="text_extracted",
        ),
    )

    attachment = await analyze_attachment(
        str(media),
        media_type="image",
        filename="image.bin",
        mime_type="image/jpeg",
        message_id="m1",
        platform="test",
        allowed_dirs=[str(tmp_path)],
    )

    assert isinstance(attachment, ChatAttachment)
    assert attachment.type == "image"
    assert attachment.extracted_text == "seriale 123"
    assert attachment.metadata["extraction_status"] == "text_extracted"
    assert attachment.metadata["media_description"] == "foto con etichetta leggibile"
    assert attachment.metadata["filename"] == "image.bin"
    assert attachment.metadata["mime_type"] == "image/jpeg"
    assert attachment.metadata["message_id"] == "m1"
    assert attachment.metadata["platform"] == "test"


@pytest.mark.asyncio
async def test_media_contract_missing_file_is_placeholder(tmp_path):
    attachment = await analyze_attachment(
        str(tmp_path / "missing.pdf"),
        media_type="pdf",
        allowed_dirs=[str(tmp_path)],
    )

    assert isinstance(attachment, ChatAttachment)
    assert attachment.type == "pdf"
    assert attachment.extracted_text is None
    assert attachment.metadata["placeholder"] is True
    assert attachment.metadata["extraction_status"] == "file_missing"


@pytest.mark.asyncio
async def test_media_contract_analysis_failure_is_explicit(monkeypatch, tmp_path):
    import core.operational_memory.media_processor as mp

    media = tmp_path / "doc.bin"
    media.write_bytes(b"fake document")

    def fail_analysis(_path, _hint=""):
        raise RuntimeError("simulated media failure")

    monkeypatch.setattr(mp, "analyze_media", fail_analysis)

    attachment = await analyze_attachment(
        str(media),
        media_type="document",
        allowed_dirs=[str(tmp_path)],
    )

    assert isinstance(attachment, ChatAttachment)
    assert attachment.type == "document"
    assert attachment.extracted_text is None
    assert attachment.metadata["placeholder"] is True
    assert attachment.metadata["extraction_status"] == "analysis_error"
    assert "simulated media failure" in attachment.metadata["ocr_error"]
