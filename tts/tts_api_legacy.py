"""
TTS API - Genesi Core v2
1 intent → 1 funzione
Text-to-Speech API streaming ottimizzato con parallelizzazione CPU
"""

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pathlib import Path
from tts.simple_tts import simple_tts
from core.log import log
import asyncio
from concurrent.futures import ThreadPoolExecutor

router = APIRouter(prefix="/tts")

logger = logging.getLogger(__name__)

class TTSRequest(BaseModel):
    text: str
    voice: str = "default"

# 3️⃣ PARALLELIZZAZIONE CPU
executor = ThreadPoolExecutor(max_workers=2)

@router.post("/")
async def text_to_speech(request: TTSRequest):
    """
    Text-to-Speech - 1 intent → 1 funzione con streaming ottimizzato
    Restituisce audio WAV in streaming con parallelizzazione
    
    Args:
        request: Richiesta TTS
        
    Returns:
        StreamingResponse audio WAV
    """
    try:
        print("STREAM_TTS_START")
        
        # Usa chunking intelligente da simple_tts
        from tts.simple_tts import smart_chunk_text, clean_tts_text
        
        # 1️⃣ NORMALIZZAZIONE TESTO
        cleaned_text = clean_tts_text(request.text)
        
        # 2️⃣ CHUNKING INTELLIGENTE
        chunks = smart_chunk_text(cleaned_text)
        
        async def audio_generator():
            """Generatore streaming audio con parallelizzazione"""
            # Genera primo chunk immediatamente
            if chunks:
                first_chunk_path = await asyncio.get_event_loop().run_in_executor(
                    executor, simple_tts.synthesize, chunks[0]
                )
                
                with open(first_chunk_path, 'rb') as f:
                    yield f.read()
                
                # 3️⃣ PARALLELIZZAZIONE: genera chunk successivi in background
                for i in range(1, len(chunks)):
                    chunk_path = await asyncio.get_event_loop().run_in_executor(
                        executor, simple_tts.synthesize, chunks[i]
                    )
                    
                    with open(chunk_path, 'rb') as f:
                        yield f.read()
            
            print("STREAM_TTS_COMPLETE")
        
        # StreamingResponse ottimizzato
        return StreamingResponse(
            audio_generator(),
            media_type="audio/wav",
            headers={
                "Content-Disposition": "inline; filename=tts_optimized.wav",
                "Cache-Control": "no-cache",
                "Transfer-Encoding": "chunked"
            }
        )
        
    except Exception as e:
        logger.error("TTS_API_ERROR", exc_info=True, extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="TTS optimized streaming error")
