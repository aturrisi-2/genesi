"""T-A1 — Platform-independent audio/voice transcription core for Operational Memory.

Thin async wrapper over the existing universal audio understanding service
(`core.audio_analysis_service.analyze_audio`: gpt-4o-audio primary, whisper-1
fallback). Path-based to match the media/OCR boundary (`media_processor`): it
reads the file bytes and returns a normalised, fail-silent result.

Guarantees:
  * never raises into the caller — every failure degrades to a status;
  * never logs the full transcription — only status / language / length;
  * adds no new dependency (reuses the STT stack already in requirements).

Generic: no channel/domain logic here. Adapters only pass a path + mime.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

from core.log import log


# Suffix → mime fallback (analyze_audio derives the temp extension from the mime).
_SUFFIX_MIME = {
    ".ogg": "audio/ogg", ".opus": "audio/ogg", ".oga": "audio/ogg",
    ".mp3": "audio/mpeg", ".mpeg": "audio/mpeg",
    ".m4a": "audio/mp4", ".mp4": "audio/mp4",
    ".wav": "audio/wav", ".aac": "audio/aac", ".amr": "audio/amr",
    ".webm": "audio/webm",
}


def _mime_for(path: str, mime_type: Optional[str]) -> str:
    if mime_type:
        return mime_type
    return _SUFFIX_MIME.get(Path(path).suffix.lower(), "audio/ogg")


def _result(
    status: str,
    text: str = "",
    language=None,
    confidence=None,
    kind: str = "",
    description: str = "",
    error: str = "",
) -> dict:
    return {
        "transcription_status": status,
        "text": text or "",
        "confidence": confidence,
        "language": language,
        "kind": kind,
        "description": description,
        "error": error,
    }


async def transcribe_audio_file(
    path: Optional[str],
    mime_type: Optional[str] = None,
) -> dict:
    """Transcribe an audio/voice file by path. Always returns a dict; never raises.

    `transcription_status`:
      * transcribed — speech recognised, `text` populated;
      * no_speech   — audio understood but no speech (music/sound/ambient);
      * unavailable — STT produced nothing at all (no model / total failure);
      * missing     — no path / file absent / empty file;
      * failed      — read or transcription error (see `error`).
    """
    if not path or not os.path.exists(path):
        return _result("missing", error="file_not_found")

    try:
        audio_bytes = await asyncio.to_thread(Path(path).read_bytes)
    except Exception as exc:
        log("OPERATIONAL_AUDIO_READ_ERROR", error=str(exc))
        return _result("failed", error=f"read_error:{exc}")

    if not audio_bytes:
        return _result("missing", error="empty_file")

    try:
        from core.audio_analysis_service import analyze_audio
        analysis = await analyze_audio(audio_bytes, _mime_for(path, mime_type))
    except Exception as exc:  # analyze_audio is fail-safe; stay defensive anyway
        log("OPERATIONAL_AUDIO_TRANSCRIBE_ERROR", error=str(exc))
        return _result("failed", error=f"transcribe_error:{exc}")

    analysis = analysis or {}
    text = (analysis.get("transcription") or "").strip()
    language = analysis.get("language")
    kind = analysis.get("kind") or "unknown"
    description = (analysis.get("description") or "").strip()

    if text:
        status = "transcribed"
    elif kind == "unknown" and not description:
        status = "unavailable"   # nothing came back at all
    else:
        status = "no_speech"     # audio understood, but no speech to ingest

    # Privacy: status / language / length only — NEVER the transcription text.
    log("OPERATIONAL_AUDIO_TRANSCRIBED", status=status, language=language,
        kind=kind, text_len=len(text))
    return _result(status, text=text, language=language, kind=kind, description=description)
