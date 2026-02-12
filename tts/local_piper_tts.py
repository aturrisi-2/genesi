"""
LOCAL PIPER TTS - Genesi Cognitive System v3
TTS completamente locale via Piper CLI.
Zero cloud. Zero quota. Zero dipendenze OpenAI.
"""

import logging
import asyncio
import tempfile
import os
import uuid

logger = logging.getLogger(__name__)

PIPER_BINARY = os.getenv("PIPER_BINARY", "piper")
PIPER_MODEL = os.getenv("PIPER_MODEL", "/opt/piper/it_IT-riccardo-medium.onnx")
PIPER_TIMEOUT = int(os.getenv("PIPER_TIMEOUT", "30"))
SENTENCE_SILENCE = float(os.getenv("PIPER_SENTENCE_SILENCE", "0.2"))


async def generate_piper_audio(text: str) -> bytes:
    """
    Genera audio WAV tramite Piper CLI locale.

    Args:
        text: Testo da sintetizzare

    Returns:
        bytes WAV audio

    Raises:
        RuntimeError: se Piper fallisce o timeout
    """
    if not text or not text.strip():
        raise ValueError("Empty text for TTS")

    cleaned = text.strip()[:2000]

    tmp_path = os.path.join(tempfile.gettempdir(), f"piper_tts_{uuid.uuid4().hex}.wav")

    logger.info("PIPER_TTS_START text_len=%d output=%s", len(cleaned), tmp_path)

    try:
        proc = await asyncio.create_subprocess_exec(
            PIPER_BINARY,
            "--model", PIPER_MODEL,
            "--output_file", tmp_path,
            "--sentence_silence", str(SENTENCE_SILENCE),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=cleaned.encode("utf-8")),
            timeout=PIPER_TIMEOUT
        )

        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            logger.error("PIPER_TTS_ERROR returncode=%d stderr=%s", proc.returncode, err_msg[:300])
            raise RuntimeError(f"Piper exited with code {proc.returncode}: {err_msg[:200]}")

        if not os.path.exists(tmp_path):
            logger.error("PIPER_TTS_ERROR output file not found: %s", tmp_path)
            raise RuntimeError("Piper did not produce output file")

        with open(tmp_path, "rb") as f:
            audio_bytes = f.read()

        if len(audio_bytes) == 0:
            logger.error("PIPER_TTS_ERROR output file is empty: %s", tmp_path)
            raise RuntimeError("Piper produced empty audio file")

        logger.info("PIPER_TTS_SUCCESS bytes=%d", len(audio_bytes))
        return audio_bytes

    except asyncio.TimeoutError:
        logger.error("PIPER_TTS_ERROR timeout after %ds", PIPER_TIMEOUT)
        raise RuntimeError(f"Piper timed out after {PIPER_TIMEOUT}s")

    except FileNotFoundError:
        logger.error("PIPER_TTS_ERROR binary not found: %s", PIPER_BINARY)
        raise RuntimeError(f"Piper binary not found at: {PIPER_BINARY}")

    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def get_piper_tts_info() -> dict:
    """Informazioni configurazione Piper TTS locale."""
    return {
        "engine": "piper",
        "model": PIPER_MODEL,
        "binary": PIPER_BINARY,
        "format": "wav",
        "provider": "local",
        "timeout": PIPER_TIMEOUT,
        "sentence_silence": SENTENCE_SILENCE
    }


logger.info("PIPER_TTS_ENGINE: Ready (binary=%s model=%s)", PIPER_BINARY, PIPER_MODEL)
