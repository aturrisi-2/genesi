from pathlib import Path

import pytest

from core.operational_memory.importers.whatsapp_export import parse_whatsapp_export
from core.operational_memory.media_analyzer import analyze_media, attachment_type_for_path, dependency_status
from core.operational_memory.watcher_engine import event_to_extraction_message


def test_parse_whatsapp_export_links_image_attachment(tmp_path):
    image_path = tmp_path / "0001-PHOTO-2026-06-12-08-31-00.jpg"
    image_path.write_bytes(b"not-a-real-image")
    raw_text = "12/06/26, 08:31 - Marco: STF B1 V10 Mandata T7 non alimentata <allegato: 0001-PHOTO-2026-06-12-08-31-00.jpg>"

    result = parse_whatsapp_export(raw_text, "media-demo", media_dir=tmp_path)

    assert result.media_detected == 1
    assert result.media_analyzed == 1
    assert result.media_ignored == 0
    assert len(result.events) == 1
    event = result.events[0]
    assert event.type == "image"
    assert event.attachment_path == str(image_path)
    assert event.attachment_type == "image"
    assert event.extraction_status in {"ocr_unavailable", "no_text_found"}
    assert event.media_description


def test_parse_whatsapp_export_ignores_audio_without_losing_text(tmp_path):
    audio_path = tmp_path / "0002-AUDIO-2026-06-12-08-31-00.opus"
    audio_path.write_bytes(b"audio")
    raw_text = "12/06/26, 08:31 - Marco: T7 M2 non parte <allegato: 0002-AUDIO-2026-06-12-08-31-00.opus>"

    result = parse_whatsapp_export(raw_text, "media-demo", media_dir=tmp_path)

    assert result.media_detected == 1
    assert result.media_ignored == 1
    assert len(result.events) == 1
    assert result.events[0].type == "text"
    assert result.events[0].content == "T7 M2 non parte"


def test_parse_whatsapp_export_ignores_sticker_only_message(tmp_path):
    sticker_path = tmp_path / "0003-STICKER-2026-06-12-08-31-00.webp"
    sticker_path.write_bytes(b"sticker")
    raw_text = "12/06/26, 08:31 - Marco: <allegato: 0003-STICKER-2026-06-12-08-31-00.webp>"

    result = parse_whatsapp_export(raw_text, "media-demo", media_dir=tmp_path)

    assert result.media_detected == 1
    assert result.media_ignored == 1
    assert result.events == []


def test_media_analyzer_reports_unsupported_pdf_extraction(tmp_path):
    pdf_path = tmp_path / "ordine.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% minimal placeholder\n")

    result = analyze_media(pdf_path)

    assert attachment_type_for_path(pdf_path) == "pdf"
    assert result.attachment_type == "pdf"
    assert result.extraction_status in {"pdf_text_unavailable", "text_extracted"}
    assert result.metadata["file_name"] == "ordine.pdf"


def test_media_analyzer_ocr_synthetic_image_or_clean_fallback(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw

    image_path = tmp_path / "ocr-test.png"
    image = Image.new("RGB", (900, 220), "white")
    draw = ImageDraw.Draw(image)
    draw.text((30, 80), "L0 V43 STF NON ALIMENTATA", fill="black")
    image.save(image_path)

    result = analyze_media(image_path)
    deps = dependency_status()

    assert result.attachment_type == "image"
    assert result.metadata["file_name"] == "ocr-test.png"
    if deps["pytesseract_binary"]:
        assert result.metadata["ocr_attempted"] is True
        assert result.extraction_status in {"text_extracted", "no_text_found"}
    else:
        assert result.metadata["ocr_attempted"] is False
        assert result.extraction_status == "ocr_unavailable"
        assert result.extracted_text == ""


def test_ocr_unavailable_media_does_not_generate_operational_noise(tmp_path):
    image_path = tmp_path / "plain.png"
    image_path.write_bytes(b"not-a-real-image")
    raw_text = "12/06/26, 08:31 - Marco: <allegato: plain.png>"

    result = parse_whatsapp_export(raw_text, "media-demo", media_dir=tmp_path)

    assert len(result.events) == 1
    assert result.events[0].content == ""
    assert result.events[0].extracted_text in {"", None}
    assert event_to_extraction_message(result.events[0]) == ""
