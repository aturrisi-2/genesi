"""
OPENAI TTS STREAMING - Genesi Core v2
Streaming TTS con OpenAI SDK v2.x - architettura definitiva
"""

import logging
from openai import AsyncOpenAI, RateLimitError, APIError, APIConnectionError
from fastapi.responses import StreamingResponse, JSONResponse
import os
from core.log import log

logger = logging.getLogger(__name__)

# Client OpenAI asincrono
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Configurazione TTS - facilmente modificabile
TTS_SPEED = 1.25  # Velocità voce (1.0 = normale, >1.0 = più veloce)
TTS_VOICE = "nova"  # Voce più dinamica rispetto ad alloy

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
                    voice=TTS_VOICE,
                    input=cleaned_text,
                    response_format="mp3",
                    speed=TTS_SPEED
                ) as response:
                    async for chunk in response.iter_bytes():
                        yield chunk
                
                print("OPENAI_TTS_COMPLETE")
                
                # Log completamento
                logger.info("OPENAI_TTS_STREAMED", 
                    extra={
                        "text_length": len(cleaned_text),
                        "model": "gpt-4o-mini-tts",
                        "voice": TTS_VOICE,
                        "speed": TTS_SPEED
                    })
                
            except (RateLimitError, APIError, APIConnectionError) as api_err:
                print(f"OPENAI_TTS_QUOTA_ERROR: {type(api_err).__name__}")
                logger.warning("TTS_FALLBACK_ACTIVATED", extra={
                    "error_type": type(api_err).__name__,
                    "error": str(api_err)[:100]
                })
                # Yield empty bytes - stream chiuso pulito, nessun crash ASGI
                return
            except Exception as e:
                print(f"OPENAI_TTS_STREAM_ERROR: {e}")
                logger.error("OPENAI_TTS_ERROR", exc_info=True, extra={"error": str(e)})
                return
        
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
        
    except (RateLimitError, APIError, APIConnectionError) as api_err:
        print(f"OPENAI_TTS_QUOTA_ERROR: {type(api_err).__name__}")
        logger.warning("TTS_FALLBACK_ACTIVATED", extra={
            "error_type": type(api_err).__name__,
            "error": str(api_err)[:100]
        })
        # Ritorna risposta vuota invece di crash
        return JSONResponse(
            status_code=200,
            content={"tts_status": "unavailable", "reason": "quota_exceeded"},
            headers={"X-TTS-Fallback": "true"}
        )
    except Exception as e:
        print(f"OPENAI_TTS_ERROR: {e}")
        logger.error("OPENAI_TTS_ERROR", exc_info=True, extra={"error": str(e)})
        return JSONResponse(
            status_code=200,
            content={"tts_status": "unavailable", "reason": "error"},
            headers={"X-TTS-Fallback": "true"}
        )

def get_openai_tts_info():
    """Informazioni configurazione OpenAI TTS"""
    return {
        "model": "gpt-4o-mini-tts",
        "voice": TTS_VOICE,
        "speed": TTS_SPEED,
        "format": "mp3",
        "provider": "OpenAI",
        "sdk_version": "v2.x"
    }

# Test configurazione
print(f"OPENAI_TTS_ENGINE: Ready with {TTS_VOICE} voice at {TTS_SPEED}x speed")
