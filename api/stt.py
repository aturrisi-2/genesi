from fastapi import APIRouter, HTTPException, UploadFile, File, status
import os
import logging
import subprocess
import tempfile
import io

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

def normalize_audio(audio_data: bytes, input_format: str) -> bytes:
    """
    Normalizza audio in PCM 16-bit 16kHz mono usando ffmpeg.
    Accept: webm, wav, audio/webm, audio/wav
    Output: PCM s16le 16000Hz mono
    """
    try:
        with tempfile.NamedTemporaryFile(suffix='.webm' if 'webm' in input_format else '.wav', delete=False) as temp_input:
            temp_input.write(audio_data)
            temp_input_path = temp_input.name
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_output:
            temp_output_path = temp_output.name
        
        # ffmpeg: converti in PCM 16-bit 16kHz mono
        cmd = [
            'ffmpeg', '-y', '-i', temp_input_path,
            '-acodec', 'pcm_s16le',
            '-ar', '16000',
            '-ac', '1',
            temp_output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"[STT] ffmpeg error: {result.stderr}")
            return None
        
        # Leggi audio normalizzato
        with open(temp_output_path, 'rb') as f:
            normalized_audio = f.read()
        
        # Rimuovi header WAV (44 bytes) per ottenere PCM puro
        pcm_data = normalized_audio[44:] if len(normalized_audio) > 44 else normalized_audio
        
        # Pulizia file temporanei
        os.unlink(temp_input_path)
        os.unlink(temp_output_path)
        
        logger.info(f"[STT] Audio normalized: {len(audio_data)} -> {len(pcm_data)} bytes PCM")
        return pcm_data
        
    except Exception as e:
        logger.error(f"[STT] Audio normalization error: {e}")
        return None

@router.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    """
    Endpoint STT con normalizzazione audio PCM 16-bit 16kHz mono.
    Processa audio normalizzato e restituisce trascrizione.
    """
    
    try:
        # Leggi i dati audio
        audio_data = await audio.read()
        content_type = audio.content_type or 'audio/webm'
        logger.info(f"[STT] Received data: {len(audio_data)} bytes, type={content_type}")
        
        # Verifica dimensione minima
        if len(audio_data) < 100:
            logger.warning(f"[STT] Data too small: {len(audio_data)} bytes")
            return {"text": ""}
        
        # NORMALIZZAZIONE AUDIO OBBLIGATORIA
        pcm_data = normalize_audio(audio_data, content_type)
        if pcm_data is None:
            logger.error("[STT] Audio normalization failed")
            return {"text": ""}
        
        # Calcola durata audio (PCM 16-bit = 2 bytes per sample, 16000 samples/sec)
        duration_seconds = len(pcm_data) / (2 * 16000)
        logger.info(f"[STT] Audio specs: duration={duration_seconds:.2f}s, sample_rate=16000Hz, channels=1, format=PCM16")
        
        # PIPELINE STT (per ora restituisce stringa vuota)
        # In produzione sostituire con vera trascrizione Whisper
        text = ""
        
        logger.info(f"[STT] STT result: '{text}'")
        return {"text": text}
        
    except Exception as e:
        logger.error(f"[STT] Error: {e}")
        return {"text": ""}
