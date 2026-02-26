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
        logger.info("TTS_PROVIDER=piper text_len=%d", len(cleaned))
        
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
    
    def __init__(self, voice: str = "it-IT-IsabellaNeural", rate: str = "+0%", volume: str = "+0%"):
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
                
            logger.info("TTS_EDGE_OK voice=%s bytes=%d", self.voice, len(result))
            return result

        except Exception as e:
            logger.warning("TTS_EDGE_FALLBACK reason=%s", e)
            return None
    
    def name(self) -> str:
        return "edge_tts"


class OpenAITTSProvider(TTSProvider):
    """Provider TTS usando OpenAI API — voce onyx profonda e naturale."""

    def __init__(self, voice: str = "nova", model: str = "tts-1", speed: float = 1.0):
        import os
        self.voice = voice
        self.model = model
        self.speed = speed
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY non trovata nelle variabili d'ambiente")
        logger.info("TTS_PROVIDER=openai voice=%s model=%s", self.voice, self.model)

    def _pad_tts_text(self, text: str) -> str:
        """
        Aggiunge padding implicito per evitare che Onyx tagli l'audio
        all'inizio e alla fine.
        """
        text = text.strip()
        
        # Aggiungi pausa iniziale con virgola se il testo inizia con parola diretta
        if text and text[0].isalpha():
            text = "… " + text  # ellissi forza una micro-pausa iniziale
        
        # Assicura che il testo finisca con punteggiatura forte
        if text and text[-1] not in '.!?…':
            text = text + "."
        
        return text

    def name(self) -> str:
        return "openai"

    async def synthesize(self, text: str) -> bytes:
        """Sintetizza con OpenAI TTS e ritorna MP3 bytes."""
        import httpx

        try:
            # Applica padding per limitare i tagli
            if self.voice in ["onyx", "nova"]:
                text = self._pad_tts_text(text)
            
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
                logger.info("TTS_OPENAI_OK voice=%s bytes=%d", self.voice, len(result))
                return result

        except Exception as e:
            logger.warning("TTS_OPENAI_FALLBACK reason=%s", e)
            return None


# TTS-ROUTING START
CONVERSATIONAL_INTENTS = {
    "greeting", "chat_free", "how_are_you", "identity", 
    "emotional", "default_relational", "memory_context"
}

INFORMATIONAL_INTENTS = {
    "weather", "tecnica", "news", "date", "knowledge_strict",
    "tool", "reminder", "document"
}

def get_tts_provider_for_intent(intent: str = None, route: str = None, user_id: str = None, text_len: int = 0) -> TTSProvider:
    """
    Ritorna il provider TTS appropriato in base all'intent o route.
    
    Logica:
    - Conversazionale → OpenAI onyx (qualità premium)
    - Informativo/tool → edge_tts (gratuito)
    - chat_free lungo (>150 chars) → edge_tts (probabile tecnico)
    - chat_free corto (≤150 chars) → openai (conversazionale)
    - Fallback → Piper (offline, sempre disponibile)
    """
    import json
    import os

    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "tts_config.json")
    
    try:
        with open(config_path) as f:
            config = json.load(f)
        providers_cfg = config.get("providers", {})
    except Exception as e:
        logger.error("TTS_ROUTING_CONFIG_ERROR reason=%s fallback=piper", e)
        return _build_piper(providers_cfg={})

    # Determina categoria
    target = intent or route or ""
    
    # chat_free con risposta lunga (>150 chars) → probabile risposta tecnica → edge
    if intent == "chat_free" and text_len > 150:
        category = "informational"
        primary = "edge_tts"
        secondary = "openai"
    # chat_free con risposta corta → conversazionale → onyx
    elif intent == "chat_free" and text_len <= 150:
        category = "conversational"
        primary = "openai"
        secondary = "edge_tts"
    elif target in CONVERSATIONAL_INTENTS or route == "default_relational":
        category = "conversational"
        primary = "openai"
        secondary = "edge_tts"
    elif target in INFORMATIONAL_INTENTS or route in ("tool", "knowledge_strict"):
        category = "informational"
        primary = "edge_tts"
        secondary = "openai"
    else:
        # Intent sconosciuto → conversazionale per sicurezza
        category = "conversational"
        primary = "openai"
        secondary = "edge_tts"

    logger.info("TTS_ROUTING intent=%s route=%s category=%s provider=%s", intent, route, category, primary)

    # Prova primary
    try:
        if primary == "openai":
            import os
            cfg = providers_cfg.get("openai", {})
            return OpenAITTSProvider(
                voice=cfg.get("voice", "nova"),
                model=os.getenv("OPENAI_TTS_MODEL", cfg.get("model", "tts-1")),
                speed=float(os.getenv("ONYX_SPEED", str(cfg.get("speed", 1.0))))
            )
        elif primary == "edge_tts":
            cfg = providers_cfg.get("edge_tts", {})
            return EdgeTTSProvider(
                voice=cfg.get("voice", "it-IT-IsabellaNeural"),
                rate=cfg.get("rate", "+0%"),
                volume=cfg.get("volume", "+0%")
            )
    except Exception as e:
        logger.warning("TTS_ROUTING_PRIMARY_FAIL provider=%s reason=%s", primary, e)

    # Prova secondary
    try:
        if secondary == "edge_tts":
            cfg = providers_cfg.get("edge_tts", {})
            return EdgeTTSProvider(
                voice=cfg.get("voice", "it-IT-IsabellaNeural"),
                rate=cfg.get("rate", "+0%"),
                volume=cfg.get("volume", "+0%")
            )
        elif secondary == "openai":
            import os
            cfg = providers_cfg.get("openai", {})
            return OpenAITTSProvider(
                voice=cfg.get("voice", "nova"),
                model=os.getenv("OPENAI_TTS_MODEL", cfg.get("model", "tts-1")),
                speed=float(os.getenv("ONYX_SPEED", str(cfg.get("speed", 1.0))))
            )
    except Exception as e:
        logger.warning("TTS_ROUTING_SECONDARY_FAIL provider=%s reason=%s", secondary, e)

    # Fallback finale: Piper (sempre offline)
    logger.warning("TTS_ROUTING_FALLBACK_PIPER")
    return _build_piper(providers_cfg)


def _build_piper(providers_cfg: dict) -> TTSProvider:
    """Costruisce PiperTTSProvider con config o default sicuri."""
    try:
        cfg = providers_cfg.get("piper", {})
        return PiperTTSProvider(
            model=cfg.get("model", "it_IT-paola-medium"),
            speed=cfg.get("speed", 1.0)
        )
    except Exception as e:
        logger.error("TTS_PIPER_FALLBACK_ERROR reason=%s", e)
        return PiperTTSProvider()
# TTS-ROUTING END


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
            
            logger.info("TTS_PROVIDER_LOADED provider=%s", active_provider)
            
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
                    voice=edge_config.get("voice", "it-IT-IsabellaNeural"),
                    rate=edge_config.get("rate", "+0%"),
                    volume=edge_config.get("volume", "+0%")
                )
            elif active_provider == "openai":
                cfg = providers.get("openai", {})
                _tts_provider_instance = OpenAITTSProvider(
                    voice=cfg.get("voice", "nova"),
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
