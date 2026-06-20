from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
PDF_EXTENSIONS = {".pdf"}
DOCUMENT_EXTENSIONS = {".doc", ".docx", ".xls", ".xlsx", ".txt"}
IGNORED_MEDIA_EXTENSIONS = {".mp4", ".mov", ".avi", ".opus", ".ogg", ".mp3", ".wav"}
DEFAULT_MAX_IMAGE_BYTES = 15 * 1024 * 1024
DEFAULT_MAX_IMAGE_PIXELS = 16_000_000
MIN_OCR_SIDE = 900
DEFAULT_OCR_LANG = "ita+eng"
COMMON_TESSERACT_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


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


def dependency_status() -> dict[str, Any]:
    try:
        import PIL  # noqa: F401

        pil_available = True
    except Exception:
        pil_available = False

    tesseract_cmd = _configured_tesseract_cmd()
    tesseract_languages: list[str] = []
    try:
        import pytesseract

        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        try:
            pytesseract.get_tesseract_version()
            tesseract_available = True
            try:
                tesseract_languages = pytesseract.get_languages(config="")
            except Exception:
                tesseract_languages = []
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
        "tesseract_cmd_configured": bool(tesseract_cmd),
        "tesseract_cmd": tesseract_cmd,
        "tesseract_ita": "ita" in tesseract_languages,
        "tesseract_eng": "eng" in tesseract_languages,
        **pdf_extractors,
    }


def _configured_tesseract_cmd() -> str | None:
    configured = os.getenv("TESSERACT_CMD")
    if configured and Path(configured).exists():
        return configured
    for candidate in COMMON_TESSERACT_PATHS:
        if Path(candidate).exists():
            return candidate
    return configured or None


def _base_metadata(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "file_name": path.name,
        "size_bytes": stat.st_size,
        "modified_timestamp": stat.st_mtime,
        "mime_type": mimetypes.guess_type(path.name)[0],
    }


def _ocr_language(deps: dict[str, Any]) -> str:
    requested = os.getenv("TESSERACT_LANG", DEFAULT_OCR_LANG)
    parts = [part for part in requested.split("+") if part]
    available = []
    if deps.get("tesseract_ita"):
        available.append("ita")
    if deps.get("tesseract_eng"):
        available.append("eng")
    selected = [part for part in parts if part in available]
    if selected:
        return "+".join(selected)
    if available:
        return "+".join(available)
    return "eng"


def _preprocess_image_for_ocr(path: Path):
    from PIL import Image, ImageEnhance, ImageOps

    image = Image.open(path)
    image = ImageOps.exif_transpose(image)
    image = image.convert("L")
    image = ImageEnhance.Contrast(image).enhance(1.7)
    width, height = image.size
    longest = max(width, height)
    if longest and longest < MIN_OCR_SIDE:
        scale = MIN_OCR_SIDE / longest
        image = image.resize((int(width * scale), int(height * scale)))
    return image


def _confidence_for_text(text: str) -> str:
    clean = " ".join((text or "").split())
    if len(clean) >= 40:
        return "high"
    if len(clean) >= 8:
        return "medium"
    return "low"


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

    if metadata["size_bytes"] > DEFAULT_MAX_IMAGE_BYTES:
        return MediaAnalysisResult(
            attachment_path=str(path),
            attachment_type="image",
            extracted_text="",
            media_description=f"Immagine offline: {path.name}. OCR saltato per dimensione file.",
            extraction_status="ocr_skipped_too_large",
            extraction_confidence="low",
            metadata={**metadata, "ocr_attempted": False},
        )
    if width and height and width * height > DEFAULT_MAX_IMAGE_PIXELS:
        return MediaAnalysisResult(
            attachment_path=str(path),
            attachment_type="image",
            extracted_text="",
            media_description=f"Immagine offline: {path.name}. OCR saltato per risoluzione elevata.",
            extraction_status="ocr_skipped_too_large",
            extraction_confidence="low",
            metadata={**metadata, "ocr_attempted": False},
        )

    if deps["pytesseract_binary"]:
        try:
            import pytesseract

            tesseract_cmd = _configured_tesseract_cmd()
            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            with _preprocess_image_for_ocr(path) as image:
                lang = _ocr_language(deps)
                text = pytesseract.image_to_string(image, lang=lang).strip()
            return MediaAnalysisResult(
                attachment_path=str(path),
                attachment_type="image",
                extracted_text=text,
                media_description=(
                    f"Immagine analizzata localmente: {path.name}"
                    if text
                    else f"Immagine analizzata localmente: {path.name}. Nessun testo OCR rilevato."
                ),
                extraction_status="text_extracted" if text else "no_text_found",
                extraction_confidence=_confidence_for_text(text),
                metadata={**metadata, "ocr_attempted": True, "ocr_lang": lang},
            )
        except Exception as exc:
            metadata["ocr_error"] = str(exc)

    dimensions = f"{width}x{height}" if width and height else "dimensioni non disponibili"
    return MediaAnalysisResult(
        attachment_path=str(path),
        attachment_type="image",
        extracted_text="",
        media_description=f"Immagine offline: {path.name} ({dimensions}). OCR locale non disponibile.",
        extraction_status="ocr_unavailable",
        extraction_confidence="low",
        metadata={**metadata, "ocr_attempted": False},
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
            media_description=f"PDF offline: {path.name}",
            extraction_status="text_extracted" if text else "pdf_text_unavailable",
            extraction_confidence="medium" if text else "low",
            metadata=metadata,
        )
    metadata = _base_metadata(path)
    return MediaAnalysisResult(
        attachment_path=str(path),
        attachment_type=attachment_type,
        media_description=f"Allegato non analizzato: {path.name}",
        extraction_status="ignored" if attachment_type in {"ignored", "sticker"} else "unsupported",
        extraction_confidence="low",
        metadata=metadata,
    )
