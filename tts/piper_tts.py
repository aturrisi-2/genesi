"""
PIPER TTS ENGINE - Genesi Cognitive System v3
TTS completamente locale via Piper CLI con streaming raw audio.
Zero cloud. Zero quota. Zero file temporanei.
"""

import logging
import asyncio
import struct
import os

logger = logging.getLogger(__name__)

PIPER_BINARY = os.getenv("PIPER_BINARY", "/opt/piper/piper/piper")
PIPER_MODEL = os.getenv("PIPER_MODEL", "/opt/piper/voices/it_IT-paola-medium.onnx")
PIPER_CONFIG = os.getenv("PIPER_CONFIG", "/opt/piper/voices/it_IT-paola-medium.onnx.json")
PIPER_TIMEOUT = int(os.getenv("PIPER_TIMEOUT", "30"))

# Raw PCM params (Piper default: 16-bit mono 22050 Hz)
SAMPLE_RATE = 22050
SAMPLE_WIDTH = 2  # 16-bit
CHANNELS = 1


def _build_wav_header(data_size: int) -> bytes:
    """Costruisce header WAV per PCM raw da Piper."""
    byte_rate = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH
    block_align = CHANNELS * SAMPLE_WIDTH
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + data_size,
        b'WAVE',
        b'fmt ',
        16,
        1,  # PCM
        CHANNELS,
        SAMPLE_RATE,
        byte_rate,
        block_align,
        SAMPLE_WIDTH * 8,
        b'data',
        data_size
    )
    return header


class PiperTTSEngine:
    """Engine TTS locale basato su Piper CLI con --output_raw."""

    def __init__(self):
        self.binary = PIPER_BINARY
        self.model = PIPER_MODEL
        self.config = PIPER_CONFIG
        self.timeout = PIPER_TIMEOUT
        logger.info("PIPER_TTS_ENGINE: Ready (binary=%s model=%s)", self.binary, self.model)

    async def synthesize(self, text: str) -> bytes:
        """
        Sintetizza testo in audio WAV via Piper --output_raw.
        Nessun file temporaneo. Streaming da stdout.

        Args:
            text: Testo da sintetizzare

        Returns:
            bytes WAV completo (header + PCM data)

        Raises:
            ValueError: testo vuoto
            RuntimeError: errore Piper
        """
        if not text or not text.strip():
            raise ValueError("Empty text for TTS")

        cleaned = text.strip()[:2000]

        logger.info("PIPER_TTS_START text_len=%d", len(cleaned))

        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary,
                "--model", self.model,
                "--config", self.config,
                "--output_raw",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            logger.info("PIPER_TTS_STREAMING")

            raw_pcm, stderr = await asyncio.wait_for(
                proc.communicate(input=cleaned.encode("utf-8")),
                timeout=self.timeout
            )

            if proc.returncode != 0:
                err_msg = stderr.decode("utf-8", errors="replace").strip()
                logger.error("PIPER_TTS_ERROR returncode=%d stderr=%s", proc.returncode, err_msg[:300])
                raise RuntimeError(f"Piper exited with code {proc.returncode}: {err_msg[:200]}")

            if len(raw_pcm) == 0:
                logger.error("PIPER_TTS_ERROR empty output from Piper")
                raise RuntimeError("Piper produced empty audio output")

            wav_header = _build_wav_header(len(raw_pcm))
            wav_bytes = wav_header + raw_pcm

            logger.info("PIPER_TTS_COMPLETE bytes=%d pcm=%d", len(wav_bytes), len(raw_pcm))
            return wav_bytes

        except asyncio.TimeoutError:
            logger.error("PIPER_TTS_ERROR timeout after %ds", self.timeout)
            raise RuntimeError(f"Piper timed out after {self.timeout}s")

        except FileNotFoundError:
            logger.error("PIPER_TTS_ERROR binary not found: %s", self.binary)
            raise RuntimeError(f"Piper binary not found at: {self.binary}")

    def info(self) -> dict:
        """Informazioni configurazione Piper TTS."""
        return {
            "engine": "piper",
            "model": self.model,
            "config": self.config,
            "binary": self.binary,
            "format": "wav",
            "sample_rate": SAMPLE_RATE,
            "sample_width": SAMPLE_WIDTH,
            "channels": CHANNELS,
            "provider": "local",
            "timeout": self.timeout
        }


# Singleton
piper_tts_engine = PiperTTSEngine()
