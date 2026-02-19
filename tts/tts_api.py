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
    TTS multi-provider con routing automatico basato su intent.
    Onyx per conversazione, Edge per contenuto, Piper fallback.
    """
    try:
        logger.info("TTS_REQUEST text_len=%d", len(request.text))

        # Sanitize text for TTS before synthesis
        from core.tts_sanitizer import sanitize_for_tts
        clean_text = sanitize_for_tts(request.text)
        
        # TTS-ROUTING-CALL START
        # Recupera ultimo intent dalla chat memory per routing
        from core.chat_memory import ChatMemory
        chat_memory = ChatMemory()
        uid = getattr(user, 'user_id', None) or getattr(user, 'id', None) or getattr(user, 'sub', None)
        last_message = chat_memory.get_last_message(uid)
        
        # Estrai intent e route dall'ultimo messaggio
        intent = last_message.get("intent") if last_message else None
        route = None  # Route non salvata in memory, ma possiamo dedurla dall'intent
        
        # Usa routing basato su intent
        from core.tts_provider import get_tts_provider_for_intent
        provider = get_tts_provider_for_intent(intent=intent, route=route, user_id=uid, text_len=len(clean_text))
        audio = await provider.synthesize(clean_text)
        
        # Gestione fallback a cascata se audio è None
        if audio is None:
            print("TTS_AUDIO_NONE primary — trying edge fallback")
            from core.tts_provider import EdgeTTSProvider
            audio = await EdgeTTSProvider().synthesize(clean_text)

        if audio is None:
            print("TTS_AUDIO_NONE edge — trying piper fallback")
            from core.tts_provider import PiperTTSProvider
            audio = await PiperTTSProvider().synthesize(clean_text)
        # TTS-ROUTING-CALL END
        
        # Aggiorna filename e media type basato sul provider
        filename = f"{provider.name()}_tts.wav"
        media_type = "audio/wav"
        
        # OpenAI restituisce MP3, non WAV
        if provider.name() == "openai":
            filename = f"{provider.name()}_tts.mp3"
            media_type = "audio/mpeg"

        return StreamingResponse(
            io.BytesIO(audio),
            media_type=media_type,
            headers={
                "Content-Disposition": f"inline; filename={filename}",
                "Content-Length": str(len(audio)),
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
