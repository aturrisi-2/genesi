from fastapi import APIRouter, HTTPException, UploadFile, File, status
import os
import whisper
import logging
import subprocess  # <--- Necessario per la conversione

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

    # Nomi file fissi nella cartella static
    webm_path = "static/input_audio.webm"
    wav_path = "static/converted_audio.wav"
    
    try:
        # 1. Pulizia vecchi file
        if os.path.exists(webm_path): os.remove(webm_path)
        if os.path.exists(wav_path): os.remove(wav_path)

        # 2. Salvataggio del file originale (WebM)
        content = await audio.read()
        with open(webm_path, "wb") as temp_file:
            file_size = temp_file.write(content)
        
        logger.info(f"Audio ricevuto: {file_size} bytes")

        # 3. CONVERSIONE FORZATA IN WAV (La magia)
        # Questo comando usa FFmpeg per creare un file WAV perfetto per Whisper (16kHz, Mono)
        command = f"ffmpeg -y -i {webm_path} -ar 16000 -ac 1 -c:a pcm_s16le {wav_path}"
        
        # Eseguiamo il comando e nascondiamo l'output se non serve
        process = subprocess.run(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if process.returncode != 0:
            logger.error("Errore critico nella conversione FFmpeg")
            return {"text": "Errore conversione audio"}

        logger.info("Conversione in WAV riuscita!")

        # 4. Trascrizione sul file WAV (non sul webm)
        result = whisper_model.transcribe(
            wav_path,
            language="it",
            task="transcribe",
            fp16=False
        )
        
        text = result.get("text", "").strip()
        logger.info(f"Trascrizione Finale: '{text}'")
        return {"text": text}

    except Exception as e:
        logger.error(f"Errore STT: {e}")
        return {"text": ""}