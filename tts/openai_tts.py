"""
OPENAI TTS STREAMING - Genesi Core v2
Streaming TTS con OpenAI API - elimina XTTS/F5/Torch stress
Architettura semplificata: Genesi → OpenAI TTS → Browser
"""

import openai
import asyncio
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from core.log import log
import io

# Configurazione OpenAI TTS
OPENAI_MODEL = "tts-1"  # Modello OpenAI TTS
OPENAI_VOICE = "alloy"  # Voce naturale moderna
OPENAI_RESPONSE_FORMAT = "mp3"  # Streaming MP3 per Safari
OPENAI_SPEED = 1.0  # Velocità normale

async def stream_openai_tts(text: str):
    """
    Streaming OpenAI TTS - audio MP3 diretto al browser
    
    Args:
        text: Testo da sintetizzare
        
    Returns:
        StreamingResponse audio/mpeg
        
    Raises:
        HTTPException: Se OpenAI TTS fallisce
    """
    try:
        print("OPENAI_TTS_START")
        
        # Validazione testo
        if not text or not text.strip():
            raise ValueError("Empty text for TTS")
        
        # Cleanup testo per OpenAI TTS
        cleaned_text = text.strip()[:4096]  # OpenAI limit: 4096 characters
        
        # Client OpenAI
        client = openai.OpenAI()
        
        # Genera streaming audio MP3
        response = client.audio.speech.create(
            model=OPENAI_MODEL,
            voice=OPENAI_VOICE,
            input=cleaned_text,
            response_format=OPENAI_RESPONSE_FORMAT,
            speed=OPENAI_SPEED
        )
        
        print("OPENAI_TTS_STREAMING")
        
        # Streaming response per FastAPI
        async def audio_stream():
            """Generatore streaming MP3"""
            try:
                # OpenAI restituisce bytes diretti
                audio_data = response.content
                
                # Stream in chunks per ottimizzare memoria
                chunk_size = 8192
                for i in range(0, len(audio_data), chunk_size):
                    chunk = audio_data[i:i + chunk_size]
                    yield chunk
                
                print("OPENAI_TTS_COMPLETE")
                
                # Log completamento
                log("OPENAI_TTS_STREAMED", 
                    text_length=len(cleaned_text),
                    audio_size=len(audio_data),
                    model=OPENAI_MODEL,
                    voice=OPENAI_VOICE
                )
                
            except Exception as e:
                print(f"OPENAI_TTS_STREAM_ERROR: {e}")
                log("OPENAI_TTS_ERROR", error=str(e))
                raise
        
        # StreamingResponse ottimizzato per Safari iPhone
        return StreamingResponse(
            audio_stream(),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=openai_tts.mp3",
                "Cache-Control": "no-cache",
                "Transfer-Encoding": "chunked",
                "Access-Control-Allow-Origin": "*"
            }
        )
        
    except openai.OpenAIError as e:
        print(f"OPENAI_TTS_API_ERROR: {e}")
        log("OPENAI_TTS_API_ERROR", error=str(e))
        raise HTTPException(status_code=500, detail="OpenAI TTS API error")
        
    except Exception as e:
        print(f"OPENAI_TTS_ERROR: {e}")
        log("OPENAI_TTS_ERROR", error=str(e))
        raise HTTPException(status_code=500, detail="OpenAI TTS streaming error")

def get_openai_tts_info():
    """Informazioni configurazione OpenAI TTS"""
    return {
        "model": OPENAI_MODEL,
        "voice": OPENAI_VOICE,
        "format": OPENAI_RESPONSE_FORMAT,
        "speed": OPENAI_SPEED,
        "provider": "OpenAI"
    }

# Test configurazione
print("OPENAI_TTS_ENGINE: Ready for streaming")
