"""
STT API - Genesi Core v2
1 intent → 1 funzione
Speech-to-Text semplice senza orchestrazione
"""

from fastapi import APIRouter, HTTPException, UploadFile, File
from pathlib import Path
import logging
import tempfile
import subprocess
import os

router = APIRouter(prefix="/stt")
logger = logging.getLogger(__name__)

@router.post("/")
async def speech_to_text(audio: UploadFile = File(...)):
    """
    Speech-to-Text - 1 intent → 1 funzione
    
    Args:
        audio: File audio
        
    Returns:
        Trascrizione semplice
    """
    try:
        # Salva audio temporaneo
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as temp_audio:
            content = await audio.read()
            temp_audio.write(content)
            temp_audio_path = temp_audio.name
        
        try:
            # Trascrizione base (placeholder)
            # In una implementazione reale, qui ci sarebbe un motore STT
            transcription = "Trascrizione non disponibile in questa versione demo"
            
            from core.log import log
            log("STT_PROCESSED", filename=audio.filename)
            
            return {
                "transcription": transcription,
                "status": "processed"
            }
            
        finally:
            # Pulizia file temporaneo
            if os.path.exists(temp_audio_path):
                os.unlink(temp_audio_path)
        
    except Exception as e:
        from core.log import log
        log("STT_ERROR", error=str(e))
        raise HTTPException(status_code=500, detail="STT error")
