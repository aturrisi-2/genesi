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
from core.operational_memory.audio_transcriber import transcribe_audio_file
from core.operational_memory.media_analyzer import analyze_media, attachment_type_for_path
from core.operational_memory.models import ChatAttachment, normalize_media_category


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

    # Audio/voice → transcription via the shared STT core (never OCR). Same
    # boundary, every platform inherits it. Transcription rides in extracted_text
    # so the operational engine treats it exactly like OCR text.
    if normalize_media_category(media_type, mime_type) == "audio":
        audio = await transcribe_audio_file(path, mime_type=mime_type)
        att_type = media_type if media_type in {"voice", "audio"} else "audio"
        text = audio.get("text") or ""
        merged_meta = {
            **base_meta,
            "extraction_status": audio.get("transcription_status"),
            "extraction_confidence": audio.get("confidence"),
            "audio_kind": audio.get("kind"),
        }
        if audio.get("language"):
            merged_meta["language"] = audio["language"]
        if audio.get("description"):
            merged_meta["media_description"] = audio["description"]
        if audio.get("error"):
            merged_meta["audio_error"] = audio["error"]
        # Privacy: status / has_text only — never the transcription text.
        log("OPERATIONAL_MEDIA_AUDIO", type=att_type,
            status=audio.get("transcription_status"), has_text=bool(text))
        return ChatAttachment(
            path=str(path),
            type=att_type,
            extracted_text=(text or None),
            metadata=merged_meta,
        )

    try:
        # Pass the known category as a hint so extension-less cache files (e.g. an
        # image named by id) are still analysed as their real kind, not 'unknown'.
        result = await asyncio.to_thread(analyze_media, Path(path), media_type or "")
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

    log("OPERATIONAL_MEDIA_ANALYZED", type=att_type, original_type=(media_type or result.attachment_type),
        status=result.extraction_status, has_text=bool(result.extracted_text))
    return ChatAttachment(
        path=str(path),
        type=att_type,
        extracted_text=(result.extracted_text or None),
        metadata=merged_meta,
    )
