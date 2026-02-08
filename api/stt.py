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
    Processa audio reale e restituisce trascrizione simulata per test.
    In produzione integrare Whisper quando disponibile.
    """
    
    try:
        # Leggi i dati audio reali
        audio_data = await audio.read()
        logger.info(f"[STT] Received real audio: {len(audio_data)} bytes, filename={audio.filename}")
        
        # Verifica dimensione minima
        if len(audio_data) < 100:
            logger.warning(f"[STT] Audio too small: {len(audio_data)} bytes")
            return {"text": ""}
        
        # Simulazione trascrizione basata su dimensione audio (solo per test)
        # In produzione sostituire con vera trascrizione Whisper
        if len(audio_data) > 50000:
            # Audio lungo - simula trascrizione frase lunga
            text = "questo è un audio di prova lungo per verificare che il sistema funzioni correttamente"
        elif len(audio_data) > 20000:
            # Audio medio - simula trascrizione frase media
            text = "audio di prova medio funzionante"
        elif len(audio_data) > 5000:
            # Audio corto - simula trascrizione frase breve
            text = "prova audio"
        else:
            # Audio molto corto - nessuna trascrizione
            text = ""
        
        logger.info(f"[STT] Processed audio: {len(audio_data)} bytes -> '{text}'")
        return {"text": text}
        
    except Exception as e:
        logger.error(f"[STT] Error: {e}")
        return {"text": ""}