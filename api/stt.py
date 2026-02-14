"""
STT API - Genesi Core v2
Speech-to-Text via OpenAI Whisper API.
Accetta audio multipart/form-data (webm, wav, mp4, ogg).
Restituisce JSON: {"text": "trascrizione"}
"""

from fastapi import APIRouter, UploadFile, File, Depends
import logging
import tempfile
import os
from openai import AsyncOpenAI
from core.log import log
from auth.router import require_auth
from auth.models import AuthUser

router = APIRouter(prefix="/stt")
logger = logging.getLogger(__name__)

_client = AsyncOpenAI()

# Estensioni supportate da OpenAI Whisper API
_SUPPORTED_EXTENSIONS = {
    "audio/webm": ".webm",
    "audio/webm;codecs=opus": ".webm",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/ogg": ".ogg",
    "audio/ogg;codecs=opus": ".ogg",
    "audio/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
}


def _ext_for_content_type(content_type: str) -> str:
    """Map content-type to file extension for Whisper API."""
    if not content_type:
        return ".webm"
    ct = content_type.lower().strip()
    return _SUPPORTED_EXTENSIONS.get(ct, ".webm")


async def transcribe_audio(audio_data: bytes, content_type: str, filename: str = "audio") -> dict:
    """
    Transcribe audio bytes via OpenAI Whisper API.
    Returns dict with 'text' and optional 'stt_status'.
    """
    if len(audio_data) < 100:
        logger.warning("STT_DATA_TOO_SMALL size=%d", len(audio_data))
        return {"text": "", "stt_status": "empty"}

    ext = _ext_for_content_type(content_type)
    tmp_path = None

    try:
        # Write to temp file (Whisper API needs a file-like with name)
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name

        # Call OpenAI Whisper API
        with open(tmp_path, "rb") as audio_file:
            transcript = await _client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="it",
                response_format="text",
            )

        text = transcript.strip() if isinstance(transcript, str) else str(transcript).strip()
        logger.info("STT_TRANSCRIPTION_RESULT text_len=%d text=%s", len(text), repr(text[:80]))
        log("STT_TRANSCRIPTION_RESULT", text_len=len(text))

        if not text or len(text) < 2:
            return {"text": "", "stt_status": "empty"}

        return {"text": text}

    except Exception as e:
        logger.error("STT_WHISPER_ERROR error=%s", str(e), exc_info=True)
        log("STT_ERROR", error=str(e))
        return {"text": "", "stt_status": "error", "error": str(e)}

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@router.post("/")
async def speech_to_text(audio: UploadFile = File(...), user: AuthUser = Depends(require_auth)):
    """
    POST /api/stt/
    Accepts multipart/form-data with field 'audio'.
    Supports: audio/webm, audio/wav, audio/ogg, audio/mp4.
    Returns: {"text": "trascrizione"} or {"text": "", "stt_status": "error|empty|noise"}
    """
    content_type = audio.content_type or "audio/webm"
    audio_data = await audio.read()

    logger.info("STT_REQUEST_RECEIVED size=%d content_type=%s filename=%s",
                len(audio_data), content_type, audio.filename)
    log("STT_REQUEST_RECEIVED", size=len(audio_data), content_type=content_type)

    result = await transcribe_audio(audio_data, content_type, audio.filename or "audio")
    return result
