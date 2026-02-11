"""
TTS API - Genesi Core v2
1 intent → 1 funzione
Text-to-Speech API streaming - restituisce audio binario WAV in streaming
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pathlib import Path
from tts.simple_tts import simple_tts
from core.log import log
import re
import asyncio
import io

router = APIRouter(prefix="/tts")

class TTSRequest(BaseModel):
    text: str
    voice: str = "default"

@router.post("/")
async def text_to_speech(request: TTSRequest):
    """
    Text-to-Speech - 1 intent → 1 funzione con streaming reale
    Restituisce audio WAV in streaming progressivo
    
    Args:
        request: Richiesta TTS
        
    Returns:
        StreamingResponse audio WAV
    """
    try:
        print("STREAM_TTS_START")
        
        # FASE 2: CHUNK INTELLIGENTE PER LUNGHEZZA (250-300 char)
        chunks = _split_text_by_length(request.text, max_length=280)
        print(f"STREAM_TTS_CHUNK_COUNT: {len(chunks)}")
        
        async def audio_generator():
            """Generatore streaming audio"""
            for i, chunk in enumerate(chunks):
                if chunk.strip():
                    print(f"STREAM_TTS_CHUNK_READY {i+1}")
                    
                    # Genera WAV singolo
                    chunk_path = simple_tts.synthesize(chunk.strip())
                    
                    # Leggi e invia chunk immediatamente
                    with open(chunk_path, 'rb') as f:
                        chunk_data = f.read()
                    
                    print(f"STREAM_TTS_CHUNK_SENT {i+1}")
                    yield chunk_data
            
            print("STREAM_TTS_COMPLETE")
        
        # StreamingResponse con Content-Type audio/wav
        return StreamingResponse(
            audio_generator(),
            media_type="audio/wav",
            headers={
                "Content-Disposition": "inline; filename=tts_stream.wav",
                "Cache-Control": "no-cache",
                "Transfer-Encoding": "chunked"
            }
        )
        
    except Exception as e:
        log("TTS_API_ERROR", error=str(e))
        raise HTTPException(status_code=500, detail="TTS streaming error")

def _split_text_by_length(text: str, max_length: int = 280) -> list:
    """
    Split intelligente per lunghezza mantenendo parole intere
    Evita split su singola frase, preferisce split per lunghezza
    """
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    current_chunk = ""
    words = text.split()
    
    for word in words:
        test_chunk = current_chunk + " " + word if current_chunk else word
        
        if len(test_chunk) <= max_length:
            current_chunk = test_chunk
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = word
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks
