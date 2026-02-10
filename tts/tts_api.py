"""
TTS API - Genesi Core v2
1 intent → 1 funzione
Text-to-Speech API semplice
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
from tts.simple_tts import simple_tts
from core.log import log

router = APIRouter(prefix="/tts")

class TTSRequest(BaseModel):
    text: str
    voice: str = "default"

@router.post("/")
async def text_to_speech(request: TTSRequest):
    """
    Text-to-Speech - 1 intent → 1 funzione
    
    Args:
        request: Richiesta TTS
        
    Returns:
        File audio sintetizzato
    """
    try:
        # 1 intent → 1 funzione: sintesi diretta
        audio_path = simple_tts.synthesize(request.text)
        
        log("TTS_API", text=request.text[:50])
        
        return {
            "audio_file": audio_path,
            "status": "synthesized"
        }
        
    except Exception as e:
        log("TTS_API_ERROR", error=str(e))
        raise HTTPException(status_code=500, detail="TTS error")
