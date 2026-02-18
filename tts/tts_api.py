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
    TTS multi-provider — restituisce audio WAV.
    Supporta Piper e Edge TTS con fallback automatico.
    """
    try:
        logger.info("TTS_REQUEST text_len=%d", len(request.text))

        # Sanitize text for TTS before synthesis
        from core.tts_sanitizer import sanitize_for_tts
        clean_text = sanitize_for_tts(request.text)
        
        # TTS-PROVIDER-LAYER START
        from core.tts_provider import synthesize_with_fallback, get_tts_provider
        provider = get_tts_provider()
        wav_bytes = await synthesize_with_fallback(clean_text)
        
        # Aggiorna filename e media type basato sul provider
        filename = f"{provider.name()}_tts.wav"
        media_type = "audio/wav"
        
        # OpenAI restituisce MP3, non WAV
        if provider.name() == "openai":
            filename = f"{provider.name()}_tts.mp3"
            media_type = "audio/mpeg"
        # TTS-PROVIDER-LAYER END

        return StreamingResponse(
            io.BytesIO(wav_bytes),
            media_type=media_type,
            headers={
                "Content-Disposition": f"inline; filename={filename}",
                "Content-Length": str(len(wav_bytes)),
                "Cache-Control": "no-cache"
            }
        )

    except Exception as e:
        logger.error("TTS_API_ERROR", exc_info=True, extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"TTS error: {str(e)[:200]}")


@router.get("/info")
async def tts_info():
    """Informazioni configurazione TTS multi-provider."""
    # TTS-PROVIDER-LAYER START
    from core.tts_provider import get_tts_provider
    provider = get_tts_provider()
    
    info = {
        "active_provider": provider.name(),
        "engine": provider.name(),
        "format": "wav",
        "sample_rate": 22050,
        "sample_width": 2,
        "channels": 1,
        "fallback_enabled": True
    }
    # TTS-PROVIDER-LAYER END
    
    return info
