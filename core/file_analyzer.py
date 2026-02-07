import os
import mimetypes
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ===============================
# MIME DETECTION (reale, non solo estensione)
# ===============================
def _detect_mime(file_path: str, filename: str, declared_ct: str) -> str:
    """Rileva MIME type reale. Prova python-magic, poi mimetypes, poi declared."""
    # 1. python-magic (analisi contenuto binario)
    try:
        import magic
        mime = magic.from_file(file_path, mime=True)
        if mime and mime != "application/octet-stream":
            logger.info(f"[MIME] magic: {mime}")
            return mime
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"[MIME] magic error: {e}")

    # 2. mimetypes (basato su estensione, ma affidabile)
    guessed, _ = mimetypes.guess_type(filename)
    if guessed:
        logger.info(f"[MIME] mimetypes: {guessed}")
        return guessed

    # 3. Fallback: content_type dichiarato dal browser
    if declared_ct and declared_ct != "application/octet-stream":
        logger.info(f"[MIME] declared: {declared_ct}")
        return declared_ct

    # 4. Ultimo fallback: sniff header bytes
    try:
        with open(file_path, "rb") as f:
            header = f.read(16)
        if header[:4] == b"%PDF":
            return "application/pdf"
        if header[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if header[:2] == b"\xff\xd8":
            return "image/jpeg"
        if header[:4] == b"GIF8":
            return "image/gif"
        if header[:4] == b"PK\x03\x04":
            return "application/zip"
        if header[:4] == b"RIFF":
            return "audio/wav"
    except Exception:
        pass

    return "application/octet-stream"


def _mime_to_kind(mime: str, ext: str) -> tuple:
    """Converte MIME type in (kind, subtype) logici."""
    major = mime.split("/")[0] if "/" in mime else ""
    minor = mime.split("/")[1] if "/" in mime else mime

    # Immagini
    if major == "image":
        return "image", ext.lstrip(".") or minor

    # Audio
    if major == "audio":
        return "audio", ext.lstrip(".") or minor

    # Video
    if major == "video":
        return "video", ext.lstrip(".") or minor

    # PDF
    if mime == "application/pdf":
        return "document", "pdf"

    # Documenti Office
    office_mimes = {
        "application/msword": "doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/vnd.ms-excel": "xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "application/vnd.ms-powerpoint": "ppt",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    }
    if mime in office_mimes:
        return "document", office_mimes[mime]

    # Testo / codice
    text_exts = {".txt", ".md", ".py", ".js", ".html", ".css", ".json", ".xml", ".csv",
                 ".yaml", ".yml", ".toml", ".ini", ".cfg", ".sh", ".bat", ".log",
                 ".ts", ".tsx", ".jsx", ".swift", ".kt", ".java", ".c", ".cpp", ".h",
                 ".rs", ".go", ".rb", ".php", ".sql", ".r", ".m", ".tex", ".rtf"}
    if major == "text" or ext in text_exts:
        return "text", ext.lstrip(".") or "txt"

    # Archivi
    archive_mimes = {"application/zip", "application/x-tar", "application/gzip",
                     "application/x-rar-compressed", "application/x-7z-compressed"}
    if mime in archive_mimes:
        return "archive", ext.lstrip(".") or minor

    return "binary", ext.lstrip(".") or "unknown"


# ===============================
# PDF TEXT EXTRACTION
# ===============================
def extract_pdf_text(file_path: str) -> tuple:
    try:
        import PyPDF2
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    text += page_text + "\n"
            if text.strip():
                return True, text.strip()
            return False, ""
    except ImportError:
        return False, ""
    except Exception:
        return False, ""


# ===============================
# MAIN ANALYZER
# ===============================
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

def analyze_file(file_path: str, filename: str, content_type: str) -> dict:
    ext = Path(filename).suffix.lower()
    size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    # Sicurezza: limite dimensione
    if size > MAX_FILE_SIZE:
        return {
            "kind": "rejected",
            "subtype": ext.lstrip(".") or "unknown",
            "size": "too_large",
            "size_bytes": size,
            "processable": False,
            "error": f"File troppo grande ({size // (1024*1024)}MB). Limite: 20MB."
        }

    # Size categories
    if size < 100 * 1024:
        size_cat = "small"
    elif size < 5 * 1024 * 1024:
        size_cat = "medium"
    else:
        size_cat = "large"

    # MIME detection reale
    mime = _detect_mime(file_path, filename, content_type)
    kind, subtype = _mime_to_kind(mime, ext)

    # Processability
    processable = kind in ["text", "image", "document"] and size_cat != "large"

    result = {
        "kind": kind,
        "subtype": subtype,
        "mime": mime,
        "size": size_cat,
        "size_bytes": size,
        "filename": filename,
        "processable": processable
    }

    # PDF: estrai testo
    if kind == "document" and subtype == "pdf":
        has_text, text_content = extract_pdf_text(file_path)
        result["has_text"] = has_text
        result["pdf_type"] = "textual" if has_text else "scanned"
        if has_text:
            result["text"] = text_content

    # Testo: leggi contenuto
    if kind == "text" and processable:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                result["text"] = f.read(50000)
                result["has_text"] = True
        except Exception:
            pass

    # OCR fallback per immagini e PDF scansionati
    if not result.get("has_text", False) and kind in ["image", "document"]:
        try:
            from core.ocr.ocr_engine import extract_text_with_ocr
            ocr_text = extract_text_with_ocr(file_path)
            if ocr_text.strip():
                result["has_text"] = True
                result["text"] = ocr_text
                result["ocr_used"] = True
                logger.info(f"[ANALYZE] OCR fallback: {len(ocr_text)} chars for {filename}")
        except ImportError:
            logger.warning("[ANALYZE] OCR module not available")
        except Exception as e:
            logger.error(f"[ANALYZE] OCR failed for {filename}: {e}")

    # Descrizione per file non processabili
    if not processable and kind not in ["rejected"]:
        result["description"] = _describe_file(kind, subtype, mime, size, filename)

    logger.info(f"[ANALYZE] {filename}: kind={kind} subtype={subtype} mime={mime} size={size_cat} processable={processable}")
    return result


def _describe_file(kind: str, subtype: str, mime: str, size: int, filename: str) -> str:
    """Genera descrizione intelligente per qualsiasi file."""
    size_str = f"{size / 1024:.0f}KB" if size < 1024 * 1024 else f"{size / (1024*1024):.1f}MB"
    descriptions = {
        "audio": f"File audio {subtype.upper()} ({size_str}). Contiene una traccia audio che potrebbe essere musica, voce registrata o un podcast.",
        "video": f"File video {subtype.upper()} ({size_str}). Contiene un filmato che potrebbe essere un video personale, una registrazione o un clip.",
        "archive": f"Archivio compresso {subtype.upper()} ({size_str}). Contiene uno o più file compressi al suo interno.",
        "binary": f"File {subtype.upper() if subtype != 'unknown' else 'binario'} ({size_str}). Tipo MIME: {mime}.",
    }
    return descriptions.get(kind, f"File {filename} ({size_str}), tipo: {mime}.")
