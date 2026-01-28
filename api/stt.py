from fastapi import APIRouter, HTTPException, UploadFile, File, status
import os
import whisper
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

try:
    whisper_model = whisper.load_model("base")
    logger.info("Whisper model loaded successfully")
except Exception as e:
    logger.error(f"Failed to load Whisper model: {e}")
    whisper_model = None

@router.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    if whisper_model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    # === MODIFICA FONDAMENTALE ===
    # Salviamo nella cartella 'static' così è visibile via web e non nascosta da systemd
    temp_file_path = "static/debug_test.webm"
    
    try:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

        content = await audio.read()
        with open(temp_file_path, "wb") as temp_file:
            file_size = temp_file.write(content)
        
        logger.info(f"!!! FILE SALVATO IN PUBBLICO: {temp_file_path} !!!")
        logger.info(f"!!! DIMENSIONE: {file_size} bytes !!!")

        # Trascrizione
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