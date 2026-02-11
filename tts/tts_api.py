"""
TTS API - Genesi Core v2
1 intent → 1 funzione
Text-to-Speech API semplice - restituisce audio binario WAV con chunking
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
from tts.simple_tts import simple_tts
from core.log import log
import re
import numpy as np

router = APIRouter(prefix="/tts")

class TTSRequest(BaseModel):
    text: str
    voice: str = "default"

@router.post("/")
async def text_to_speech(request: TTSRequest):
    """
    Text-to-Speech - 1 intent → 1 funzione con chunking intelligente
    Restituisce SOLO audio binario WAV
    
    Args:
        request: Richiesta TTS
        
    Returns:
        File audio WAV binario
    """
    try:
        # FASE 2: CHUNKING INTELLIGENTE
        chunks = re.split(r'(?<=[.!?]) +', request.text)
        print(f"VOICE CHUNK COUNT: {len(chunks)}")
        
        chunk_wavs = []
        
        # Genera WAV per ogni chunk
        for chunk in chunks:
            if chunk.strip():
                chunk_path = simple_tts.synthesize(chunk.strip())
                chunk_wavs.append(chunk_path)
        
        # Concatena WAV con pausa naturale
        if len(chunk_wavs) > 1:
            final_wav = _concatenate_wavs_with_pause(chunk_wavs)
            final_path = _save_final_wav(final_wav)
        else:
            final_path = chunk_wavs[0] if chunk_wavs else None
        
        if not final_path:
            raise HTTPException(status_code=500, detail="No audio generated")
        
        # Verifica esistenza file
        path_obj = Path(final_path)
        if not path_obj.exists():
            log("TTS_FILE_NOT_FOUND", audio_path=final_path)
            raise HTTPException(status_code=500, detail="Audio file not found")
        
        # Verifica size file - CRITICO
        file_size = path_obj.stat().st_size
        if file_size == 0:
            log("TTS_FILE_EMPTY", audio_path=final_path, size=file_size)
            raise HTTPException(status_code=500, detail="Audio file is empty")
        
        log("TTS_API", text=request.text[:50], audio_path=final_path, size=file_size, chunks=len(chunks))
        
        # Restituisci SOLO file audio binario WAV se size > 0
        return FileResponse(
            path=final_path,
            media_type="audio/wav",
            filename="tts_output.wav"
        )
        
    except Exception as e:
        log("TTS_API_ERROR", error=str(e))
        raise HTTPException(status_code=500, detail="TTS error")

def _concatenate_wavs_with_pause(chunk_paths):
    """Concatena WAV con pausa naturale tra chunk"""
    import soundfile as sf
    
    all_audio = []
    sample_rate = 24000  # Sample rate fisso XTTS
    
    # Pausa naturale di 150ms
    pause = np.zeros(int(0.15 * sample_rate))
    
    for i, chunk_path in enumerate(chunk_paths):
        # Carica chunk
        data, sr = sf.read(chunk_path)
        
        # Assicura sample rate corretto
        if sr != sample_rate:
            import librosa
            data = librosa.resample(data, orig_sr=sr, target_sr=sample_rate)
        
        all_audio.append(data)
        
        # Aggiungi pausa tra chunk (non dopo l'ultimo)
        if i < len(chunk_paths) - 1:
            all_audio.append(pause)
    
    # Concatena tutto
    final_audio = np.concatenate(all_audio)
    return final_audio

def _save_final_wav(audio_data):
    """Salva WAV finale concatenato"""
    import soundfile as sf
    import uuid
    
    output_file = f"tts_final_{uuid.uuid4()}.wav"
    output_path = Path("tts_cache") / output_file
    output_path.parent.mkdir(exist_ok=True)
    
    # Salva con sample rate fisso 24000Hz
    sf.write(str(output_path), audio_data, 24000)
    return str(output_path)
