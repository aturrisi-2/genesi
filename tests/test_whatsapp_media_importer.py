from pathlib import Path

from core.operational_memory.importers.whatsapp_export import parse_whatsapp_export
from core.operational_memory.media_analyzer import analyze_media, attachment_type_for_path


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
