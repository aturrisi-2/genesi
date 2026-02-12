"""
TTS API - Genesi Core v2
OpenAI TTS streaming endpoint
"""

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from tts.openai_tts import stream_openai_tts, get_openai_tts_info

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tts")

class TTSRequest(BaseModel):
    text: str
    voice: str = "nova"

@router.post("/")
async def tts_endpoint(request: TTSRequest):
    """
    OpenAI TTS streaming endpoint
    """
    try:
        # Log richiesta
        logger.info("TTS_REQUEST", extra={"text_length": len(request.text), "voice": request.voice})
        
        # Streaming OpenAI TTS (gestisce internamente 429/API errors)
        return await stream_openai_tts(request.text)
        
    except Exception as e:
        logger.error("TTS_API_ERROR", exc_info=True, extra={"error": str(e)})
        # Risposta pulita invece di 500 - il frontend gestisce l'assenza di audio
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=200,
            content={"tts_status": "unavailable", "reason": "error"},
            headers={"X-TTS-Fallback": "true"}
        )

@router.get("/info")
async def tts_info():
    """Informazioni configurazione TTS"""
    return get_openai_tts_info()
