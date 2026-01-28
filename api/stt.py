from fastapi import APIRouter, HTTPException, UploadFile, File, status
from fastapi.responses import JSONResponse
import tempfile
import os
from pathlib import Path
import whisper
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# Carica modello Whisper una sola volta
try:
    # Usa modello base per buon compromesso velocità/accuratezza
    whisper_model = whisper.load_model("base")
    logger.info("Whisper model loaded successfully")
except Exception as e:
    logger.error(f"Failed to load Whisper model: {e}")
    whisper_model = None

@router.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    if whisper_model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    # 1. Nome file FISSO per debug facile
    temp_file_path = "/tmp/debug_audio_test.webm"
    
    try:
        # Pulisce eventuali residui precedenti manualmente
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

        # 2. Scrive il file
        content = await audio.read()
        with open(temp_file_path, "wb") as temp_file:
            file_size = temp_file.write(content)
        
        # LOG DELLA VERITÀ
        logger.info(f"!!! FILE SALVATO QUI: {temp_file_path} !!!")
        logger.info(f"!!! DIMENSIONE: {file_size} bytes !!!")

        # 3. Trascrizione
        result = whisper_model.transcribe(
            temp_file_path,
            language="it",
            task="transcribe",
            fp16=False
        )
        
        text = result.get("text", "").strip()
        logger.info(f"Trascrizione: '{text}'")
        return {"text": text}

    except Exception as e:
        logger.error(f"Errore: {e}")
        return {"text": ""}
    
    # 4. NESSUN 'FINALLY'. IL FILE RIMANE LÌ PER FORZA.