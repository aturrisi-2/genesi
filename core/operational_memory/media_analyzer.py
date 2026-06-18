from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
PDF_EXTENSIONS = {".pdf"}
DOCUMENT_EXTENSIONS = {".doc", ".docx", ".xls", ".xlsx", ".txt"}
IGNORED_MEDIA_EXTENSIONS = {".mp4", ".mov", ".avi", ".opus", ".ogg", ".mp3", ".wav"}


class MediaAnalysisResult(BaseModel):
    attachment_path: str
    attachment_type: str
    extracted_text: str = ""
    media_description: str = ""
    extraction_status: str = "not_analyzed"
    extraction_confidence: str = "low"
    metadata: dict[str, Any] = Field(default_factory=dict)


def attachment_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix in IMAGE_EXTENSIONS:
        if "sticker" in name:
            return "sticker"
        return "image"
    if suffix in PDF_EXTENSIONS:
        return "pdf"
    if suffix in DOCUMENT_EXTENSIONS:
        return "document"
    if suffix in IGNORED_MEDIA_EXTENSIONS:
        return "ignored"
    return "unknown"


def is_supported_attachment(path: Path) -> bool:
    return attachment_type_for_path(path) in {"image", "pdf", "document"}


def dependency_status() -> dict[str, bool]:
    try:
        import PIL  # noqa: F401

        pil_available = True
    except Exception:
        pil_available = False

    try:
        import pytesseract

        try:
            pytesseract.get_tesseract_version()
            tesseract_available = True
        except Exception:
            tesseract_available = False
    except Exception:
        tesseract_available = False

    pdf_extractors = {}
    for module in ("pdfplumber", "pypdf", "fitz"):
        try:
            __import__(module)
            pdf_extractors[module] = True
        except Exception:
            pdf_extractors[module] = False

    return {
        "pil": pil_available,
        "pytesseract_binary": tesseract_available,
        **pdf_extractors,
    }


def _base_metadata(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "file_name": path.name,
        "size_bytes": stat.st_size,
        "modified_timestamp": stat.st_mtime,
        "mime_type": mimetypes.guess_type(path.name)[0],
    }


def _analyze_image(path: Path) -> MediaAnalysisResult:
    metadata = _base_metadata(path)
    deps = dependency_status()
    metadata["dependencies"] = deps

    width = None
    height = None
    try:
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
            metadata["width"] = width
            metadata["height"] = height
    except Exception as exc:
        metadata["image_error"] = str(exc)

    if deps["pytesseract_binary"]:
        try:
            from PIL import Image
            import pytesseract

            with Image.open(path) as image:
                text = pytesseract.image_to_string(image).strip()
            return MediaAnalysisResult(
                attachment_path=str(path),
                attachment_type="image",
                extracted_text=text,
                media_description=f"Immagine WhatsApp analizzata localmente: {path.name}",
                extraction_status="text_extracted" if text else "no_text_found",
                extraction_confidence="medium" if text else "low",
                metadata=metadata,
            )
        except Exception as exc:
            metadata["ocr_error"] = str(exc)

    dimensions = f"{width}x{height}" if width and height else "dimensioni non disponibili"
    return MediaAnalysisResult(
        attachment_path=str(path),
        attachment_type="image",
        extracted_text="",
        media_description=f"Immagine WhatsApp offline: {path.name} ({dimensions}). OCR locale non disponibile.",
        extraction_status="ocr_unavailable",
        extraction_confidence="low",
        metadata=metadata,
    )


def _extract_pdf_text(path: Path) -> tuple[str, dict[str, Any]]:
    metadata = _base_metadata(path)
    deps = dependency_status()
    metadata["dependencies"] = deps

    if deps.get("pdfplumber"):
        try:
            import pdfplumber

            with pdfplumber.open(path) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            return text.strip(), metadata
        except Exception as exc:
            metadata["pdfplumber_error"] = str(exc)
    if deps.get("pypdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text.strip(), metadata
        except Exception as exc:
            metadata["pypdf_error"] = str(exc)
    return "", metadata


def analyze_media(path: Path) -> MediaAnalysisResult:
    path = Path(path)
    attachment_type = attachment_type_for_path(path)
    if attachment_type == "image":
        return _analyze_image(path)
    if attachment_type == "pdf":
        text, metadata = _extract_pdf_text(path)
        return MediaAnalysisResult(
            attachment_path=str(path),
            attachment_type="pdf",
            extracted_text=text,
            media_description=f"PDF WhatsApp offline: {path.name}",
            extraction_status="text_extracted" if text else "pdf_text_unavailable",
            extraction_confidence="medium" if text else "low",
            metadata=metadata,
        )
    metadata = _base_metadata(path)
    return MediaAnalysisResult(
        attachment_path=str(path),
        attachment_type=attachment_type,
        media_description=f"Allegato WhatsApp non analizzato: {path.name}",
        extraction_status="ignored" if attachment_type in {"ignored", "sticker"} else "unsupported",
        extraction_confidence="low",
        metadata=metadata,
    )
