"""
OCR SERVICE - Genesi Core v2
Estrazione testo da immagini via Tesseract locale (subprocess).
"""

import asyncio
import logging
import shutil
from core.log import log

logger = logging.getLogger(__name__)

# Tesseract binary path — auto-detect
_TESSERACT_CMD = shutil.which("tesseract") or "tesseract"


async def extract_text_from_image(path: str) -> str:
    """
    Extract text from image file using Tesseract OCR.
    
    Args:
        path: Absolute path to image file
        
    Returns:
        Extracted text string (may be empty if no text found)
    """
    log("OCR_START", path=path)

    try:
        proc = await asyncio.create_subprocess_exec(
            _TESSERACT_CMD, path, "stdout",
            "-l", "ita+eng",
            "--psm", "3",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            logger.error("OCR_SUBPROCESS_ERROR returncode=%d stderr=%s", proc.returncode, err_msg)
            raise RuntimeError(f"Tesseract error (code {proc.returncode}): {err_msg}")

        text = stdout.decode("utf-8", errors="replace").strip()
        log("OCR_DONE", chars=len(text))
        return text

    except asyncio.TimeoutError:
        logger.error("OCR_TIMEOUT path=%s", path)
        raise RuntimeError("OCR timeout (30s)")

    except FileNotFoundError:
        logger.error("OCR_NOT_INSTALLED tesseract_cmd=%s", _TESSERACT_CMD)
        raise RuntimeError("Tesseract non installato. Installa con: apt install tesseract-ocr")
