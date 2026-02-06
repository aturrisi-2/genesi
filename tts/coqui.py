import asyncio
import uuid
import io
from pathlib import Path

import edge_tts


# Voce: Isabella — italiana, femminile, calda, naturale
VOICE = "it-IT-IsabellaNeural"

# Rate e pitch per voce calma e rassicurante
RATE = "-5%"
PITCH = "-2Hz"

OUTPUT_DIR = Path("data/tts_cache")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def _synthesize_async(text: str) -> bytes:
    """
    Genera audio MP3 da testo usando Edge TTS (Microsoft Neural).
    Ritorna i bytes MP3 direttamente.
    """
    communicate = edge_tts.Communicate(
        text=text,
        voice=VOICE,
        rate=RATE,
        pitch=PITCH
    )

    buffer = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buffer.write(chunk["data"])

    return buffer.getvalue()


def synthesize_bytes(text: str) -> bytes:
    """
    Sincrono wrapper — ritorna bytes MP3.
    Usato dall'endpoint FastAPI.
    """
    if not text or not isinstance(text, str) or not text.strip():
        raise ValueError("Testo vuoto")

    return asyncio.run(_synthesize_async(text.strip()))


async def synthesize_bytes_async(text: str) -> bytes:
    """
    Async wrapper — ritorna bytes MP3.
    Usato dall'endpoint FastAPI async.
    """
    if not text or not isinstance(text, str) or not text.strip():
        raise ValueError("Testo vuoto")

    return await _synthesize_async(text.strip())


def synthesize(text: str) -> str:
    """
    Compatibilità: genera file MP3 e ritorna il path.
    """
    audio_bytes = synthesize_bytes(text)
    out_file = OUTPUT_DIR / f"tts_{uuid.uuid4().hex}.mp3"
    out_file.write_bytes(audio_bytes)
    return str(out_file.resolve())


if __name__ == "__main__":
    path = synthesize("Ciao, sono Genesi. Sono qui con te.")
    print(f"Audio: {path}")
