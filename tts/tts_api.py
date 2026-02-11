"""
TTS API - Genesi Core v2
OpenAI TTS Streaming - architettura definitiva
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from tts.openai_tts import stream_openai_tts
from core.log import log

router = APIRouter(prefix="/tts")

class TTSRequest(BaseModel):
    text: str
    voice: str = "default"

@router.post("/")
async def text_to_speech(request: TTSRequest):
    """
    Text-to-Speech - OpenAI TTS Streaming
    Restituisce audio MP3 streaming da OpenAI
    
    Args:
        request: Richiesta TTS
        
    Returns:
        StreamingResponse audio MP3
    """
    try:
        # Log richiesta
        log("TTS_REQUEST", text_length=len(request.text), voice=request.voice)
        
        # Streaming OpenAI TTS
        return await stream_openai_tts(request.text)
        
    except Exception as e:
        log("TTS_API_ERROR", error=str(e))
        raise HTTPException(status_code=500, detail="OpenAI TTS streaming error")

@router.get("/info")
async def tts_info():
    """Informazioni configurazione TTS"""
    from tts.openai_tts import get_openai_tts_info
    return get_openai_tts_info()
