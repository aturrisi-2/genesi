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
    """
    Endpoint Speech-to-Text usando Whisper.
    Accetta file audio (webm/mp4/wav) e restituisce trascrizione.
    """
    
    # Verifica che il modello Whisper sia caricato
    if whisper_model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="STT service unavailable - Whisper model not loaded"
        )
    
    # Verifica che il file sia stato fornito
    if not audio or not audio.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio file is required"
        )
    
    # Verifica content type
    allowed_types = [
        "audio/webm", 
        "audio/mp4", 
        "audio/wav", 
        "audio/mpeg",
        "audio/ogg"
    ]
    
    if audio.content_type not in allowed_types:
        logger.warning(f"Unsupported content type: {audio.content_type}")
        # Non bloccare, ma logga il warning
    
    # Crea file temporaneo
    temp_dir = tempfile.gettempdir()
    temp_file_path = None
    
    try:
        # Salva file temporaneo con estensione appropriata
        file_extension = Path(audio.filename).suffix or ".webm"
        temp_file_path = os.path.join(temp_dir, f"stt_temp_{os.getpid()}{file_extension}")
        
        # Scrivi file su disco
        with open(temp_file_path, "wb") as temp_file:
            content = await audio.read()
            temp_file.write(content)
        
        logger.info(f"Audio saved temporarily: {temp_file_path}")
        
        # Trascrivi con Whisper
        result = whisper_model.transcribe(
            temp_file_path,
            language="it",  # Italiano automatico
            task="transcribe",  # Solo trascrizione, non traduzione
            fp16=False,  # Compatibilità massima
            verbose=False
        )
        
        # Estrai testo
        transcribed_text = result.get("text", "").strip()
        
        logger.info(f"Transcription completed: '{transcribed_text[:50]}...'")
        
        # Ritorna risposta nel formato atteso dal frontend
        return {"text": transcribed_text}
        
    except Exception as e:
        logger.error(f"STT Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Speech-to-text error: {str(e)}"
        )
    
    finally:
        # Pulizia file temporaneo
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                logger.info(f"Temporary file cleaned: {temp_file_path}")
            except Exception as e:
                logger.warning(f"Failed to clean temp file {temp_file_path}: {e}")
