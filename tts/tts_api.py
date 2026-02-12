"""
TTS API - Genesi Cognitive System v3
Piper TTS locale. Zero cloud. Zero quota.
"""

import io
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from tts.local_piper_tts import generate_piper_audio, get_piper_tts_info

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tts")


class TTSRequest(BaseModel):
    text: str


@router.post("/")
async def tts_endpoint(request: TTSRequest):
    """
    Piper TTS locale — restituisce audio WAV.
    Nessun cloud. Nessuna quota. Nessun fallback.
    """
    try:
        logger.info("TTS_REQUEST text_len=%d", len(request.text))

        audio_bytes = await generate_piper_audio(request.text)

        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type="audio/wav",
            headers={
                "Content-Disposition": "inline; filename=piper_tts.wav",
                "Content-Length": str(len(audio_bytes)),
                "Cache-Control": "no-cache"
            }
        )

    except Exception as e:
        logger.error("TTS_API_ERROR", exc_info=True, extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"TTS error: {str(e)[:200]}")


@router.get("/info")
async def tts_info():
    """Informazioni configurazione Piper TTS locale."""
    return get_piper_tts_info()
