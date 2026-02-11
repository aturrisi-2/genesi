"""
OPENAI TTS STREAMING - Genesi Core v2
Streaming TTS con OpenAI SDK v2.x - architettura definitiva
"""

from openai import AsyncOpenAI
from fastapi.responses import StreamingResponse
import os
from core.log import log

# Client OpenAI asincrono
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def stream_openai_tts(text: str):
    """
    Streaming OpenAI TTS con SDK v2.x - MP3 diretto al browser
    
    Args:
        text: Testo da sintetizzare
        
    Returns:
        StreamingResponse audio/mpeg
    """
    try:
        print("OPENAI_TTS_START")
        
        # Validazione testo
        if not text or not text.strip():
            raise ValueError("Empty text for TTS")
        
        # Cleanup testo per OpenAI TTS
        cleaned_text = text.strip()[:4096]  # OpenAI limit
        
        async def audio_generator():
            """Generatore streaming MP3 da OpenAI"""
            try:
                print("OPENAI_TTS_STREAMING")
                
                async with client.audio.speech.with_streaming_response.create(
                    model="gpt-4o-mini-tts",
                    voice="alloy",
                    input=cleaned_text,
                    response_format="mp3"
                ) as response:
                    async for chunk in response.iter_bytes():
                        yield chunk
                
                print("OPENAI_TTS_COMPLETE")
                
                # Log completamento
                log("OPENAI_TTS_STREAMED", 
                    text_length=len(cleaned_text),
                    model="gpt-4o-mini-tts",
                    voice="alloy"
                )
                
            except Exception as e:
                print(f"OPENAI_TTS_STREAM_ERROR: {e}")
                log("OPENAI_TTS_ERROR", error=str(e))
                raise
        
        # StreamingResponse ottimizzato
        return StreamingResponse(
            audio_generator(),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=openai_tts.mp3",
                "Cache-Control": "no-cache",
                "Transfer-Encoding": "chunked"
            }
        )
        
    except Exception as e:
        print(f"OPENAI_TTS_ERROR: {e}")
        log("OPENAI_TTS_ERROR", error=str(e))
        raise

def get_openai_tts_info():
    """Informazioni configurazione OpenAI TTS"""
    return {
        "model": "gpt-4o-mini-tts",
        "voice": "alloy",
        "format": "mp3",
        "provider": "OpenAI",
        "sdk_version": "v2.x"
    }

# Test configurazione
print("OPENAI_TTS_ENGINE: Ready with v2.x SDK")
