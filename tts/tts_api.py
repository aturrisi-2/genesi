"""
TTS API - Genesi Core v2
1 intent → 1 funzione
Text-to-Speech API semplice - restituisce audio binario WAV
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
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
    Restituisce SOLO audio binario WAV
    
    Args:
        request: Richiesta TTS
        
    Returns:
        File audio WAV binario
    """
    try:
        # 1 intent → 1 funzione: sintesi diretta
        audio_path = simple_tts.synthesize(request.text)
        
        # Verifica esistenza file
        path_obj = Path(audio_path)
        if not path_obj.exists():
            log("TTS_FILE_NOT_FOUND", audio_path=audio_path)
            raise HTTPException(status_code=500, detail="Audio file not found")
        
        # Verifica size file - CRITICO
        file_size = path_obj.stat().st_size
        if file_size == 0:
            log("TTS_FILE_EMPTY", audio_path=audio_path, size=file_size)
            raise HTTPException(status_code=500, detail="Audio file is empty")
        
        log("TTS_API", text=request.text[:50], audio_path=audio_path, size=file_size)
        
        # Restituisci SOLO file audio binario WAV se size > 0
        return FileResponse(
            path=audio_path,
            media_type="audio/wav",
            filename="tts_output.wav"
        )
        
    except Exception as e:
        log("TTS_API_ERROR", error=str(e))
        raise HTTPException(status_code=500, detail="TTS error")
