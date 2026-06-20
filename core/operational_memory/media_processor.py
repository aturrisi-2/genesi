"""MEDIA STEP 1 — Platform-independent async media/OCR core for Operational Memory.

Thin async wrapper over the existing, synchronous `media_analyzer.analyze_media`
(OCR for images, text for PDFs, placeholder otherwise). It runs the CPU-bound
work off the event loop (`asyncio.to_thread`) so it never blocks the host bot,
normalises the result into a `ChatAttachment` (the schema the Operational Memory
already understands), validates the path against traversal, and degrades to a
safe placeholder on any failure — never raising into the caller.

Generic: no channel-specific or domain logic here. Platform adapters only
download the file and pass a path; this core does the rest, identically for every
channel. No live side effects: it neither sends nor reads env/services.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

from core.log import log
from core.operational_memory.media_analyzer import analyze_media, attachment_type_for_path
from core.operational_memory.models import ChatAttachment


def _clean_meta(**fields) -> dict:
    return {k: v for k, v in fields.items() if v is not None}


def _placeholder(
    media_type: Optional[str],
    meta: dict,
    status: str,
    path: Optional[str] = None,
) -> ChatAttachment:
    return ChatAttachment(
        path=path,
        type=media_type or "document",
        extracted_text=None,
        metadata={**meta, "placeholder": True, "extraction_status": status},
    )


def _safe_path(path: str, allowed_dirs: Optional[list[str]]) -> tuple[bool, str]:
    """Reject parent-traversal and (if allowed_dirs given) any path outside them."""
    try:
        if ".." in Path(path).parts:
            return False, "parent_traversal"
        resolved = Path(path).resolve()
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"resolve_error:{exc}"
    if allowed_dirs:
        for base in allowed_dirs:
            try:
                if resolved.is_relative_to(Path(base).resolve()):
                    return True, ""
            except Exception:
                continue
        return False, "outside_allowed_dirs"
    return True, ""


async def analyze_attachment(
    path: Optional[str],
    media_type: Optional[str] = None,
    filename: Optional[str] = None,
    mime_type: Optional[str] = None,
    message_id: Optional[str] = None,
    platform: Optional[str] = None,
    allowed_dirs: Optional[list[str]] = None,
) -> ChatAttachment:
    """Analyse an attachment off the event loop and return a normalised
    `ChatAttachment`. Always returns — failures degrade to a placeholder."""
    base_meta = _clean_meta(
        platform=platform, message_id=message_id, filename=filename, mime_type=mime_type
    )

    if not path:
        return _placeholder(media_type, base_meta, status="no_file")

    safe, reason = _safe_path(path, allowed_dirs)
    if not safe:
        log("OPERATIONAL_MEDIA_PATH_REJECTED", reason=reason)
        return _placeholder(media_type, {**base_meta, "path_error": reason}, status="rejected_path")

    if not os.path.exists(path):
        return _placeholder(media_type, {**base_meta, "path": path}, status="file_missing", path=path)

    try:
        result = await asyncio.to_thread(analyze_media, Path(path))
    except Exception as exc:
        log("OPERATIONAL_MEDIA_ANALYSIS_ERROR", error=str(exc))
        return _placeholder(
            media_type or attachment_type_for_path(Path(path)),
            {**base_meta, "path": path, "ocr_error": str(exc)},
            status="analysis_error",
            path=path,
        )

    att_type = result.attachment_type or media_type or "document"
    merged_meta = {
        **base_meta,
        **(result.metadata or {}),
        "extraction_status": result.extraction_status,
        "extraction_confidence": result.extraction_confidence,
    }
    if result.media_description:
        merged_meta["media_description"] = result.media_description

    log("OPERATIONAL_MEDIA_ANALYZED", type=att_type, status=result.extraction_status,
        has_text=bool(result.extracted_text))
    return ChatAttachment(
        path=str(path),
        type=att_type,
        extracted_text=(result.extracted_text or None),
        metadata=merged_meta,
    )
