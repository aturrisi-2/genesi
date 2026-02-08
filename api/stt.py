from fastapi import APIRouter, HTTPException, UploadFile, File, status
import os
import logging
import subprocess
import speech_recognition as sr
import tempfile
import io

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# Inizializza Speech Recognition
recognizer = sr.Recognizer()
logger.info("Speech Recognition inizializzato")

@router.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    """
    Endpoint STT con vera trascrizione usando Google Speech Recognition.
    Processa audio reale e restituisce trascrizione vera.
    """
    
    try:
        # Leggi i dati audio reali
        audio_data = await audio.read()
        logger.info(f"[STT] Received real audio: {len(audio_data)} bytes, filename={audio.filename}")
        
        # Verifica dimensione minima
        if len(audio_data) < 100:
            logger.warning(f"[STT] Audio too small: {len(audio_data)} bytes")
            return {"text": ""}
        
        # Salva audio in file temporaneo
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
            temp_file.write(audio_data)
            temp_file_path = temp_file.name
        
        try:
            # Usa Speech Recognition per trascrivere
            with sr.AudioFile(temp_file_path) as source:
                # Regola per rumore ambientale
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                
                # Leggi l'audio
                audio_data_recognizer = recognizer.record(source)
                
                # Trascrivi usando Google Speech Recognition (gratuito)
                try:
                    text = recognizer.recognize_google(audio_data_recognizer, language='it-IT')
                    logger.info(f"[STT] Trascrizione riuscita: '{text}'")
                    return {"text": text}
                    
                except sr.UnknownValueError:
                    logger.warning("[STT] Google Speech Recognition non ha capito l'audio")
                    return {"text": ""}
                    
                except sr.RequestError as e:
                    logger.error(f"[STT] Errore Google Speech Recognition: {e}")
                    # Fallback: prova a usare un'altra API
                    try:
                        text = recognizer.recognize_sphinx(audio_data_recognizer, language='it-it')
                        logger.info(f"[STT] Trascrizione Sphinx: '{text}'")
                        return {"text": text}
                    except:
                        logger.error("[STT] Anche Sphinx fallito")
                        return {"text": ""}
                        
        finally:
            # Pulizia file temporaneo
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
        
    except Exception as e:
        logger.error(f"[STT] Error: {e}")
        return {"text": ""}