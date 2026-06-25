"""Image vision description for Operational Memory (fallback when OCR is weak).

Real equipment photos (labels, valves, panels) are read poorly by plain OCR
(pytesseract) → garbage text. The project already has a vision pipeline that
reads them well (`core.image_vision_service.describe_image`). This thin async
wrapper exposes it to the operational media core as a fail-safe fallback.

Guarantees: never raises; never logs the description text (only status/length).
Adds no new dependency (reuses the existing vision stack)."""

from __future__ import annotations

import os
import re
from typing import Optional

from core.log import log


def _looks_weak_ocr(text: str) -> bool:
    """Heuristic: OCR output that is empty or garbage (photos, not screenshots).
    Weak when too short, or low ratio of real words / mostly noise characters."""
    t = (text or "").strip()
    if len(t) < 12:
        return True
    words = re.findall(r"[A-Za-zÀ-ÿ]{3,}", t)
    if len(words) < 3:
        return True
    # alpha-ratio: garbage OCR is dominated by isolated symbols/single chars.
    alpha = sum(c.isalnum() for c in t)
    if alpha / max(len(t), 1) < 0.5:
        return True
    return False


def _result(status: str, text: str = "", description: str = "", error: str = "") -> dict:
    return {"image_status": status, "text": text or "", "description": description or "", "error": error}


async def describe_image_file(path: Optional[str]) -> dict:
    """Describe an image via the vision pipeline. Always returns a dict; never raises.
    `image_status` ∈ {image_described, image_no_content, missing, image_analysis_failed}."""
    if not path or not os.path.exists(path):
        return _result("missing", error="file_not_found")
    try:
        from core.image_vision_service import describe_image
        desc = (await describe_image(path) or "").strip()
    except Exception as exc:  # describe_image is fail-safe; stay defensive
        log("OPERATIONAL_IMAGE_DESCRIBE_ERROR", error=str(exc))
        return _result("image_analysis_failed", error=f"describe_error:{exc}")
    if not desc:
        return _result("image_no_content")
    # Privacy: status / length only — never the description text.
    log("OPERATIONAL_IMAGE_DESCRIBED", status="image_described", text_len=len(desc))
    return _result("image_described", text=desc, description=desc)
