"""
TTS API - Genesi Cognitive System v3
Piper TTS locale. Zero cloud. Zero quota. Zero fallback.
"""

import io
import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from tts.piper_tts import piper_tts_engine
from auth.router import require_auth
from auth.models import AuthUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tts")


class TTSRequest(BaseModel):
    text: str


@router.post("/")
async def tts_endpoint(request: TTSRequest, user: AuthUser = Depends(require_auth)):
    """
    Piper TTS locale — restituisce audio WAV.
    Nessun cloud. Nessuna quota. Nessun fallback.
    """
    try:
        logger.info("TTS_REQUEST text_len=%d", len(request.text))

        # Sanitize text for TTS before synthesis
        from core.tts_sanitizer import sanitize_for_tts
        clean_text = sanitize_for_tts(request.text)
        
        wav_bytes = await piper_tts_engine.synthesize(clean_text)

        return StreamingResponse(
            io.BytesIO(wav_bytes),
            media_type="audio/wav",
            headers={
                "Content-Disposition": "inline; filename=piper_tts.wav",
                "Content-Length": str(len(wav_bytes)),
                "Cache-Control": "no-cache"
            }
        )

    except Exception as e:
        logger.error("TTS_API_ERROR", exc_info=True, extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"TTS error: {str(e)[:200]}")


@router.get("/info")
async def tts_info():
    """Informazioni configurazione Piper TTS locale."""
    return piper_tts_engine.info()
