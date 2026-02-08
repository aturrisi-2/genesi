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
        
        # FASE 2: ANALISI PIPELINE AUDIO DETTAGLIATA
        duration_seconds = len(pcm_data) / (2 * 16000)
        
        import numpy as np
        audio_array = np.frombuffer(pcm_data, dtype=np.int16)
        
        # METRICHE AUDIO DETTAGLIATE
        max_amplitude = np.max(np.abs(audio_array))
        rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
        dc_offset = np.mean(audio_array)
        clipping_count = np.sum(np.abs(audio_array) >= 32767)
        
        logger.info(f"[STT] PIPELINE ANALYSIS:")
        logger.info(f"[STT]   input: {len(audio_data)} bytes, type={content_type}")
        logger.info(f"[STT]   pcm: {len(pcm_data)} bytes, duration={duration_seconds:.2f}s")
        logger.info(f"[STT]   sample_rate: 16000Hz, channels: 1, format: PCM16")
        logger.info(f"[STT]   max_amplitude: {max_amplitude}")
        logger.info(f"[STT]   rms: {rms:.2f}")
        logger.info(f"[STT]   dc_offset: {dc_offset:.2f}")
        logger.info(f"[STT]   clipping_samples: {clipping_count}")
        
        # FASE 2: CONTROLLO QUALITÀ AUDIO PRIMA DI WHISPER
        quality_issues = []
        
        # Controllo RMS (rumore troppo basso)
        if rms < 500:
            quality_issues.append(f"rms_too_low:{rms:.0f}")
        
        # Controllo clipping (audio saturato)
        if clipping_count > len(audio_array) * 0.1:  # >10% clipping
            quality_issues.append(f"excessive_clipping:{clipping_count}")
        
        # Controllo DC offset (problemi hardware)
        if abs(dc_offset) > 1000:
            quality_issues.append(f"dc_offset:{dc_offset:.0f}")
        
        # Controllo frame ripetuti (audio bloccato)
        if len(audio_array) > 16000:  # almeno 1 secondo
            # Controlla se ci sono frame identici ripetuti
            frame_size = 1600  # 100ms frames
            frames = audio_array[:len(audio_array)//frame_size*frame_size].reshape(-1, frame_size)
            if len(frames) > 10:
                # Calcola similarità tra frame consecutivi
                correlations = []
                for i in range(len(frames)-1):
                    corr = np.corrcoef(frames[i], frames[i+1])[0,1]
                    if not np.isnan(corr):
                        correlations.append(corr)
                
                if correlations and np.mean(correlations) > 0.95:
                    quality_issues.append("repeated_frames")
        
        # Se ci sono problemi qualità → scarta prima di Whisper
        if quality_issues:
            logger.warning(f"[STT] AUDIO QUALITY ISSUES: {', '.join(quality_issues)}")
            logger.warning(f"[STT] Discarding audio before Whisper")
            return {
                "text": "",
                "stt_status": "noise",
                "quality_issues": quality_issues
            }
        
        logger.info(f"[STT] Audio quality OK → proceeding to Whisper")
        
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
            
            # FASE 3: CONTROLLO QUALITÀ TRASCRIZIONE
            logger.info(f"[STT] Whisper raw output: '{text}'")
            
            # Analisi qualità trascrizione
            transcription_issues = []
            
            # Controllo sillabe singole
            words = text.split()
            if len(words) == 1 and len(text) < 4:
                transcription_issues.append("single_syllable")
            
            # Controllo caratteri random/non-italiani
            if any(ord(c) < 32 or ord(c) > 255 for c in text if not c.isspace()):
                transcription_issues.append("invalid_characters")
            
            # Controllo lingue miste (caratteri non italiani)
            italian_chars = set("abcdefghijklmnopqrstuvwxyzàèéìòùABCDEFGHIJKLMNOPQRSTUVWXYZÀÈÉÌÒÙ'.,!?- ")
            if any(c not in italian_chars for c in text):
                transcription_issues.append("mixed_languages")
            
            # Controllo ripetizioni caratteri
            if len(text) > 5 and len(set(text.replace(' ', ''))) < 3:
                transcription_issues.append("repeated_chars")
            
            # Se ci sono problemi trascrizione → classificare come NOISE
            if transcription_issues:
                logger.warning(f"[STT] TRANSCRIPTION QUALITY ISSUES: {', '.join(transcription_issues)}")
                logger.warning(f"[STT] Classifying as noise")
                return {
                    "text": "",
                    "stt_status": "noise",
                    "transcription_issues": transcription_issues
                }
            
            # VALIDAZIONE POST-WHISPER OBBLIGATORIA
            if not _is_valid_transcription(text):
                logger.warning(f"[STT] empty transcription → ignored")
                return {"text": "", "stt_status": "empty", "action": "retry"}
            
        except Exception as e:
            logger.error(f"[STT] Whisper error: {e}")
            logger.warning(f"[STT] Whisper exception → returning error status")
            return {
                "text": "",
                "stt_status": "error",
                "whisper_error": str(e)
            }
        
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
