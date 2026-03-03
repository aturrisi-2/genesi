"""
FILE ANALYZER - Genesi Core v2
Identifica tipo file, smista a handler appropriato.
Restituisce dict strutturato: {"type": ..., "content": ..., "meta": {...}}
"""

import os
import logging
import tempfile
from fastapi import UploadFile
from core.log import log

logger = logging.getLogger(__name__)

# Estensioni supportate → tipo logico
_EXT_MAP = {
    # PDF
    ".pdf": "pdf",
    # Immagini
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".bmp": "image",
    ".webp": "image",
    ".tiff": "image",
    ".tif": "image",
    # Testo
    ".txt": "text",
    ".md": "text",
    ".csv": "text",
    ".json": "text",
    ".xml": "text",
    ".html": "text",
    ".htm": "text",
    ".log": "text",
    ".py": "text",
    ".js": "text",
    ".ts": "text",
    ".css": "text",
    ".yaml": "text",
    ".yml": "text",
    ".toml": "text",
    ".ini": "text",
    ".cfg": "text",
    ".env": "text",
    ".sh": "text",
    ".bat": "text",
    ".sql": "text",
    ".r": "text",
    ".java": "text",
    ".c": "text",
    ".cpp": "text",
    ".h": "text",
    ".rs": "text",
    ".go": "text",
    ".rb": "text",
    ".php": "text",
    ".swift": "text",
    ".kt": "text",
    ".heic": "image",
    ".heif": "image",
}

_SUPPORTED_EXTENSIONS = set(_EXT_MAP.keys())

# Max file size: 20 MB
_MAX_FILE_SIZE = 20 * 1024 * 1024


def _detect_type(filename: str) -> str:
    """Detect file type from extension. Returns type string or raises ValueError."""
    if not filename:
        raise ValueError("Nome file mancante")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _EXT_MAP:
        raise ValueError(f"Estensione non supportata: {ext}")
    return _EXT_MAP[ext]


async def analyze_file(file: UploadFile) -> dict:
    """
    Main entry point: read file, detect type, route to handler.
    Returns: {"type": "...", "content": "...", "meta": {...}}
    """
    log("FILE_ANALYZER_START", filename=file.filename, content_type=file.content_type)

    # Fail-fast: empty filename
    if not file.filename:
        raise ValueError("File senza nome")

    # Detect type
    file_type = _detect_type(file.filename)
    log("FILE_TYPE_DETECTED", type=file_type, filename=file.filename)

    # Read file data
    data = await file.read()

    # Fail-fast: empty file
    if len(data) == 0:
        raise ValueError("File vuoto")

    # Fail-fast: too large
    if len(data) > _MAX_FILE_SIZE:
        raise ValueError(f"File troppo grande: {len(data)} bytes (max {_MAX_FILE_SIZE})")

    # Write to temp file for handlers that need a path
    ext = os.path.splitext(file.filename)[1].lower()
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        # Route to handler
        if file_type == "pdf":
            result = await _handle_pdf(tmp_path, file.filename)
        elif file_type == "image":
            result = await _handle_image(tmp_path, file.filename)
        elif file_type == "text":
            result = await _handle_text(data, file.filename)
        else:
            raise ValueError(f"Tipo non gestito: {file_type}")

        log("FILE_ANALYZER_DONE", type=file_type, content_len=len(result.get("content", "")))
        return result

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


async def _handle_pdf(path: str, filename: str) -> dict:
    """Extract text from PDF using PyPDF2."""
    try:
        import PyPDF2
    except ImportError:
        logger.error("PyPDF2 not installed")
        raise ValueError("PyPDF2 non installato. Installa con: pip install PyPDF2")

    text_parts = []
    page_count = 0

    try:
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            page_count = len(reader.pages)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text.strip())
    except Exception as e:
        logger.error("PDF_EXTRACT_ERROR error=%s", str(e))
        raise ValueError(f"Errore lettura PDF: {str(e)}")

    content = "\n\n".join(text_parts)

    # If no text extracted, try OCR on first page
    if not content.strip():
        try:
            from core.ocr_service import extract_text_from_image
            content = await extract_text_from_image(path)
        except Exception as ocr_err:
            logger.warning("PDF_OCR_FALLBACK_FAILED error=%s", str(ocr_err))
            content = ""

    return {
        "type": "pdf",
        "content": content,
        "meta": {
            "filename": filename,
            "pages": page_count,
            "chars": len(content),
        }
    }


async def _handle_image(path: str, filename: str) -> dict:
    """Process image: OCR for text extraction + vision for description."""
    ocr_text = ""
    description = ""

    # OCR
    try:
        from core.ocr_service import extract_text_from_image
        ocr_text = await extract_text_from_image(path)
    except Exception as e:
        logger.warning("IMAGE_OCR_FAILED error=%s", str(e))

    # Vision description
    try:
        from core.image_vision_service import describe_image
        description = await describe_image(path)
    except Exception as e:
        logger.warning("IMAGE_VISION_FAILED error=%s", str(e))

    # Combina OCR + vision: entrambi nel contenuto per massima ricchezza
    ocr_clean = ocr_text.strip() if ocr_text else ""
    desc_clean = description.strip() if description else ""

    if ocr_clean and len(ocr_clean) > 20 and desc_clean:
        # Immagine con testo E descrizione visiva — massima qualità
        content = f"TESTO ESTRATTO DALL'IMMAGINE:\n{ocr_clean}\n\nDESCRIZIONE VISIVA:\n{desc_clean}"
    elif desc_clean:
        # Immagine pura — solo descrizione visiva
        content = desc_clean
    elif ocr_clean:
        # Solo OCR (vision fallita)
        content = ocr_clean
    else:
        content = ""

    return {
        "type": "image",
        "content": content,
        "meta": {
            "filename": filename,
            "ocr_text": ocr_clean[:500],
            "description": desc_clean[:500],
            "chars": len(content),
        }
    }


async def _handle_text(data: bytes, filename: str) -> dict:
    """Read plain text file."""
    # Try UTF-8 first, then latin-1 as fallback
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            content = data.decode("latin-1")
        except UnicodeDecodeError:
            content = data.decode("utf-8", errors="replace")

    return {
        "type": "text",
        "content": content,
        "meta": {
            "filename": filename,
            "chars": len(content),
            "lines": content.count("\n") + 1,
        }
    }
