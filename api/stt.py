from fastapi import APIRouter, HTTPException, UploadFile, File, status
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    """
    Endpoint STT stabile senza dipendenze esterne.
    Processa dati e restituisce trascrizione.
    In produzione integrare Whisper quando disponibile.
    """
    
    try:
        # Leggi i dati reali
        audio_data = await audio.read()
        logger.info(f"[STT] Received data: {len(audio_data)} bytes, filename={audio.filename}")
        
        # Verifica dimensione minima
        if len(audio_data) < 100:
            logger.warning(f"[STT] Data too small: {len(audio_data)} bytes")
            return {"text": ""}
        
        # Per testing temporaneo: restituisci stringa vuota
        # In produzione sostituire con vera trascrizione Whisper
        text = ""
        
        logger.info(f"[STT] Processed data: {len(audio_data)} bytes -> '{text}'")
        return {"text": text}
        
    except Exception as e:
        logger.error(f"[STT] Error: {e}")
        return {"text": ""}
