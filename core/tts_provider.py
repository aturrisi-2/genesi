"""
TTS Provider Layer - Genesi Cognitive System
Astrazione multi-provider per sintesi vocale (Piper, Edge TTS, futuri)
"""

import asyncio
import json
import os
import logging
import struct
import subprocess
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Audio format constants (Piper default: 16-bit mono 22050 Hz)
SAMPLE_RATE = 22050
SAMPLE_WIDTH = 2  # 16-bit
CHANNELS = 1


def _build_wav_header(data_size: int) -> bytes:
    """Costruisce header WAV per PCM raw."""
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


class TTSProvider(ABC):
    """Classe base astratta per provider TTS."""
    
    @abstractmethod
    async def synthesize(self, text: str) -> Optional[bytes]:
        """Sintetizza testo in audio PCM bytes."""
        pass
    
    @abstractmethod
    def name(self) -> str:
        """Nome del provider."""
        pass


class PiperTTSProvider(TTSProvider):
    """Provider TTS basato su Piper CLI."""
    
    def __init__(self, model: str = "it_IT-paola-medium", speed: float = 1.0):
        self.binary = os.getenv("PIPER_BINARY", "/opt/piper/piper/piper")
        self.model = os.getenv("PIPER_MODEL", f"/opt/piper/voices/{model}.onnx")
        self.config = os.getenv("PIPER_CONFIG", f"/opt/piper/voices/{model}.onnx.json")
        self.speed = speed
        self.timeout = int(os.getenv("PIPER_TIMEOUT", "30"))
        logger.info("PIPER_TTS_PROVIDER: Ready (binary=%s model=%s)", self.binary, self.model)
    
    async def synthesize(self, text: str) -> Optional[bytes]:
        """Sintetizza testo via Piper CLI."""
        if not text or not text.strip():
            return None
        
        cleaned = text.strip()[:2000]
        print(f"TTS_PROVIDER=piper text_len={len(cleaned)}")
        
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
            
            raw_pcm, stderr = await asyncio.wait_for(
                proc.communicate(input=cleaned.encode("utf-8")),
                timeout=self.timeout
            )
            
            if proc.returncode != 0:
                err_msg = stderr.decode("utf-8", errors="replace").strip()
                logger.error("PIPER_TTS_ERROR returncode=%d stderr=%s", proc.returncode, err_msg[:300])
                return None
            
            if len(raw_pcm) == 0:
                logger.error("PIPER_TTS_ERROR empty output")
                return None
            
            wav_header = _build_wav_header(len(raw_pcm))
            wav_bytes = wav_header + raw_pcm
            
            logger.info("PIPER_TTS_COMPLETE bytes=%d pcm=%d", len(wav_bytes), len(raw_pcm))
            return wav_bytes
            
        except asyncio.TimeoutError:
            logger.error("PIPER_TTS_ERROR timeout after %ds", self.timeout)
            return None
        except FileNotFoundError:
            logger.error("PIPER_TTS_ERROR binary not found: %s", self.binary)
            return None
        except Exception as e:
            logger.error("PIPER_TTS_ERROR unexpected: %s", str(e))
            return None
    
    def name(self) -> str:
        return "piper"


class EdgeTTSProvider(TTSProvider):
    """Provider TTS basato su Edge TTS (Microsoft)."""
    
    def __init__(self, voice: str = "it-IT-DiegoNeural", rate: str = "+0%", volume: str = "+0%"):
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self.timeout = 5.0
        logger.info("EDGE_TTS_PROVIDER: Ready (voice=%s rate=%s volume=%s)", voice, rate, volume)
    
    async def synthesize(self, text: str) -> bytes:
        """Sintetizza testo con edge-tts e ritorna bytes audio."""
        import io
        import edge_tts

        try:
            communicate = edge_tts.Communicate(
                text,
                voice=self.voice,
                rate=self.rate,
                volume=self.volume
            )
            audio_buffer = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_buffer.write(chunk["data"])
            
            result = audio_buffer.getvalue()
            if not result:
                raise ValueError("Audio buffer vuoto")
                
            print(f"TTS_EDGE_OK voice={self.voice} bytes={len(result)}")
            return result

        except Exception as e:
            print(f"TTS_EDGE_FALLBACK reason={e}")
            return None
    
    def name(self) -> str:
        return "edge_tts"


class OpenAITTSProvider(TTSProvider):
    """Provider TTS usando OpenAI API — voce onyx profonda e naturale."""

    def __init__(self, voice: str = "onyx", model: str = "tts-1", speed: float = 1.0):
        import os
        self.voice = voice
        self.model = model
        self.speed = speed
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY non trovata nelle variabili d'ambiente")
        print(f"TTS_PROVIDER=openai voice={self.voice} model={self.model}")

    def name(self) -> str:
        return "openai"

    async def synthesize(self, text: str) -> bytes:
        """Sintetizza con OpenAI TTS e ritorna MP3 bytes."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "input": text,
                        "voice": self.voice,
                        "speed": self.speed,
                        "response_format": "mp3"
                    }
                )
                response.raise_for_status()
                result = response.content
                print(f"TTS_OPENAI_OK voice={self.voice} bytes={len(result)}")
                return result

        except Exception as e:
            print(f"TTS_OPENAI_FALLBACK reason={e}")
            return None


# Singleton con cache e invalidazione per modifiche config
_tts_provider_instance: Optional[TTSProvider] = None
_config_mtime: Optional[float] = None
_provider_lock = asyncio.Lock()


def get_tts_provider() -> TTSProvider:
    """Factory function che ritorna il provider TTS configurato."""
    global _tts_provider_instance, _config_mtime
    
    config_path = Path("config/tts_config.json")
    
    try:
        # Controlla se il file di config è stato modificato
        current_mtime = config_path.stat().st_mtime
        
        if _tts_provider_instance is None or _config_mtime != current_mtime:
            # Ricarica la configurazione
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            active_provider = config.get("active_provider", "piper")
            providers = config.get("providers", {})
            
            print(f"TTS_PROVIDER_LOADED provider={active_provider}")
            
            # Istanzia il provider corretto
            if active_provider == "piper":
                piper_config = providers.get("piper", {})
                _tts_provider_instance = PiperTTSProvider(
                    model=piper_config.get("model", "it_IT-paola-medium"),
                    speed=piper_config.get("speed", 1.0)
                )
            elif active_provider == "edge_tts":
                edge_config = providers.get("edge_tts", {})
                _tts_provider_instance = EdgeTTSProvider(
                    voice=edge_config.get("voice", "it-IT-DiegoNeural"),
                    rate=edge_config.get("rate", "+0%"),
                    volume=edge_config.get("volume", "+0%")
                )
            elif active_provider == "openai":
                cfg = providers.get("openai", {})
                _tts_provider_instance = OpenAITTSProvider(
                    voice=cfg.get("voice", "onyx"),
                    model=cfg.get("model", "tts-1"),
                    speed=cfg.get("speed", 1.0)
                )
            else:
                logger.error("Unknown TTS provider: %s, falling back to Piper", active_provider)
                _tts_provider_instance = PiperTTSProvider()
            
            _config_mtime = current_mtime
            
        return _tts_provider_instance
        
    except FileNotFoundError:
        logger.error("TTS config file not found, using Piper fallback")
        return PiperTTSProvider()
    except Exception as e:
        logger.error("Error loading TTS config: %s, using Piper fallback", str(e))
        return PiperTTSProvider()


async def synthesize_with_fallback(text: str) -> bytes:
    """Sintetizza testo con fallback automatico."""
    provider = get_tts_provider()
    
    # Tenta con il provider primario
    audio = await provider.synthesize(text)
    
    if audio is None:
        logger.warning("Primary TTS provider failed, using Piper fallback")
        # Fallback a Piper
        fallback_provider = PiperTTSProvider()
        audio = await fallback_provider.synthesize(text)
        
        if audio is None:
            raise RuntimeError("Both primary and fallback TTS providers failed")
    
    return audio
