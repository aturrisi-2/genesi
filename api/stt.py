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
        
        # Verifica che l'audio contenga dati (non sia tutto silenzio)
        import numpy as np
        audio_array = np.frombuffer(pcm_data, dtype=np.int16)
        max_amplitude = np.max(np.abs(audio_array))
        logger.info(f"[STT] Audio specs: duration={duration_seconds:.2f}s, sample_rate=16000Hz, channels=1, format=PCM16, max_amplitude={max_amplitude}")
        
        if max_amplitude < 1000:  # Soglia molto bassa per audio silenzioso
            logger.warning(f"[STT] Audio too quiet (max_amplitude={max_amplitude}), may not contain speech")
        
        # PIPELINE STT con Whisper reale
        try:
            import whisper
            model = whisper.load_model("base")
            
            # Salva PCM come WAV temporaneo per Whisper
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
                # Calcola header WAV dinamico
                pcm_size = len(pcm_data)
                file_size = pcm_size + 36
                wav_header = (
                    b'RIFF' + file_size.to_bytes(4, 'little') +
                    b'WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00@\x1f\x00\x00\x80\x3e\x00\x00\x02\x00\x10\x00' +
                    b'data' + pcm_size.to_bytes(4, 'little')
                )
                temp_wav.write(wav_header + pcm_data)
                temp_wav_path = temp_wav.name
                logger.info(f"[STT] WAV created: {file_size} bytes total, {pcm_size} bytes PCM")
            
            # Trascrivi con Whisper
            result = model.transcribe(temp_wav_path, language='it', fp16=False)
            text = result['text'].strip()
            
            # Pulizia file temporaneo
            os.unlink(temp_wav_path)
            
            logger.info(f"[STT] Whisper transcription: '{text}'")
            
            # VALIDAZIONE POST-WHISPER OBBLIGATORIA
            if not self._is_valid_transcription(text):
                logger.warning(f"[STT] empty transcription → ignored")
                return {"text": "", "status": "empty", "action": "retry"}
            
        except Exception as e:
            logger.error(f"[STT] Whisper error: {e}")
            logger.warning(f"[STT] empty transcription → ignored (Whisper error)")
            return {"text": "", "status": "empty", "action": "retry"}
        
        logger.info(f"[STT] STT result: '{text}'")
        return {"text": text}
        
    except Exception as e:
        logger.error(f"[STT] Error: {e}")
        logger.warning(f"[STT] empty transcription → ignored (general error)")
        return {"text": "", "status": "empty", "action": "retry"}

def _is_valid_transcription(text: str) -> bool:
    """
    Validazione post-Whisper per trascrizioni valide
    """
    # Lunghezza minima
    if len(text) < 2:
        return False
    
    # Non solo spazi
    text_clean = text.strip()
    if len(text_clean) < 2:
        return False
    
    # Almeno un carattere alfanumerico
    if not any(c.isalnum() for c in text_clean):
        return False
    
    # Non solo caratteri ripetuti (es "aaa", "ooo") - solo se > 3 caratteri
    if len(text_clean) > 3:
        chars_no_spaces = text_clean.replace(' ', '')
        if len(set(chars_no_spaces)) < 2:
            return False
    
    # Parole significative comuni anche se corte
    meaningful_short = ['ok', 'sì', 'si', 'no', 'va', 'ben']
    if text_clean.lower() in meaningful_short:
        return True
    
    # Se ha spazi, probabilmente è una frase valida
    if ' ' in text_clean and len(text_clean) >= 3:
        return True
    
    return True
