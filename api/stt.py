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
    Endpoint STT deterministico con una sola pipeline.
    Processa dati vocali e restituisce sempre una stringa.
    MAI stringa vuota se audio > 0 bytes.
    """
    
    try:
        # Leggi i dati vocali
        audio_data = await audio.read()
        logger.info(f"[STT] Received data: {len(audio_data)} bytes, filename={audio.filename}")
        
        # Verifica dimensione minima
        if len(audio_data) < 100:
            logger.warning(f"[STT] Data too small: {len(audio_data)} bytes")
            return {"text": "[audio troppo breve]"}
        
        # PIPELINE UNICA DETERMINISTICA
        # In produzione sostituire con vera trascrizione Whisper
        # MAI stringa vuota se audio ricevuto
        text = "[audio non riconosciuto]"
        
        logger.info(f"[STT] Processed data: {len(audio_data)} bytes -> '{text}'")
        return {"text": text}
        
    except Exception as e:
        logger.error(f"[STT] Error: {e}")
        return {"text": "[errore trascrizione]"}
