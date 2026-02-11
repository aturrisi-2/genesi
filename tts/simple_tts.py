"""
TTS SIMPLE - Genesi Core v2
1 intent → 1 funzione
Text-to-Speech con XTTS v2 - Alexandra Hisakawa 24000Hz lock definitivo
"""

from pathlib import Path
import logging
from typing import Optional
from core.emoji_filter import emoji_filter

logger = logging.getLogger(__name__)

# BLOCCO DEFINITIVO VOCE XTTS
VOICE_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"
VOICE_SPEAKER = "Alexandra Hisakawa"
VOICE_LANGUAGE = "it"
VOICE_SAMPLE_RATE = 24000  # FISSO - NON MODIFICARE

class SimpleTTS:
    """
    TTS semplice - 1 intent → 1 funzione
    Con filtro emoji per TTS (non per chat) e XTTS v2 lock definitivo
    """
    
    def __init__(self):
        self.tts_dir = Path("tts_cache")
        self.tts_dir.mkdir(exist_ok=True)
        # Inizializza XTTS v2 - UNICO MODELLO
        self.tts = None
        self._init_xtts()
    
    def _init_xtts(self):
        """Inizializza XTTS v2 - BLOCCO DEFINITIVO"""
        try:
            from TTS.api import TTS
            
            # BLOCCO DEFINITIVO - XTTS v2 UNICO MODELLO
            self.tts = TTS(model_name=VOICE_MODEL)
            
            # LOG DI CONFERMA BOOT
            print("VOICE MODEL ACTIVE: XTTS v2")
            print(f"VOICE SPEAKER ACTIVE: {VOICE_SPEAKER}")
            print(f"VOICE SAMPLE RATE: {VOICE_SAMPLE_RATE}")
            
            logger.info(f"[VOICE_LOCK] Model: {VOICE_MODEL}")
            logger.info(f"[VOICE_LOCK] Speaker: {VOICE_SPEAKER}")
            logger.info(f"[VOICE_LOCK] Language: {VOICE_LANGUAGE}")
            logger.info(f"[VOICE_LOCK] Sample Rate: {VOICE_SAMPLE_RATE}Hz (FISSO)")
            
        except ImportError:
            logger.error("TTS package not available - install with: pip install TTS==0.22.0")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize XTTS v2: {e}")
            raise
    
    def synthesize(self, text: str, output_file: Optional[str] = None) -> str:
        """
        Sintesi vocale - 1 intent → 1 funzione
        Filtra emoji SOLO per TTS, non per chat
        
        Args:
            text: Testo da sintetizzare (con emoji ammesse)
            output_file: File output opzionale
            
        Returns:
            Percorso file audio
        """
        try:
            # Filtra emoji SOLO per TTS
            filtered_text = emoji_filter.filter_for_tts(text)
            
            if not filtered_text.strip():
                raise ValueError("Empty text after filtering")
            
            # Verifica XTTS disponibile
            if not self.tts:
                logger.error("XTTS v2 not available - cannot synthesize")
                raise RuntimeError("XTTS v2 not initialized")
            
            # Genera filename se non fornito
            if output_file is None:
                import uuid
                output_file = f"tts_{uuid.uuid4()}.wav"
            
            output_path = self.tts_dir / output_file
            
            # Sintesi BLOCCO DEFINITIVO
            self._synthesize_definitivo(output_path, filtered_text)
            
            from core.log import log
            log("TTS_SYNTHESIZED", original_text=text[:50], filtered_text=filtered_text[:50], output=str(output_path))
            
            return str(output_path)
            
        except Exception as e:
            from core.log import log
            log("TTS_ERROR", error=str(e))
            raise
    
    def _synthesize_definitivo(self, output_path: Path, text: str):
        """
        Sintesi BLOCCO DEFINITIVO - Alexandra Hisakawa 24000Hz
        """
        try:
            # SINTESI ESATTA - Alexandra Hisakawa
            wav = self.tts.tts(
                text=text,
                speaker=VOICE_SPEAKER,
                language=VOICE_LANGUAGE
            )
            
            # SALVATAGGIO ESATTO - 24000Hz FISSO
            import soundfile as sf
            sf.write(str(output_path), wav, VOICE_SAMPLE_RATE)
            
            # LOG SINTESI
            duration = len(wav) / VOICE_SAMPLE_RATE
            logger.info(f"[VOICE_SYNTH] speaker={VOICE_SPEAKER} lang={VOICE_LANGUAGE} sr={VOICE_SAMPLE_RATE}Hz duration={duration:.2f}s samples={len(wav)}")
            
        except Exception as e:
            logger.error(f"Definitivo synthesis failed: {e}")
            raise
    
    def _generate_wav_file(self, output_path: Path, text: str):
        """
        Metodo legacy - NON USATO
        """
        raise NotImplementedError("Use XTTS v2 with Alexandra Hisakawa lock")

# Istanza globale - BLOCCO DEFINITIVO
simple_tts = SimpleTTS()
