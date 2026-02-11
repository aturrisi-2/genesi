"""
TTS SIMPLE - Genesi Core v2
1 intent → 1 funzione
Text-to-Speech con XTTS v2 - speaker Alexandra Hisakawa lock definitivo
"""

from pathlib import Path
import logging
from typing import Optional
from core.emoji_filter import emoji_filter

logger = logging.getLogger(__name__)

# LOCK VOCALE DEFINITIVO
DEFAULT_SPEAKER = "Alexandra Hisakawa"
DEFAULT_LANGUAGE = "it"

class SimpleTTS:
    """
    TTS semplice - 1 intent → 1 funzione
    Con filtro emoji per TTS (non per chat) e XTTS v2 speaker lock
    """
    
    def __init__(self):
        self.tts_dir = Path("tts_cache")
        self.tts_dir.mkdir(exist_ok=True)
        # Inizializza XTTS v2 una sola volta all'avvio
        self.model = None
        self._init_xtts()
    
    def _init_xtts(self):
        """Inizializza XTTS v2 con speaker Alexandra Hisakawa lock definitivo"""
        try:
            from TTS.api import TTS
            
            # Inizializza XTTS v2
            self.model = TTS(
                model_name="tts_models/multilingual/multi-dataset/xtts_v2",
                progress_bar=False
            )
            
            # LOCK VOCALE DEFINITIVO
            logger.info("[TTS_INIT] XTTS v2 loaded")
            logger.info(f"[TTS_INIT] Speaker locked: {DEFAULT_SPEAKER}")
            logger.info("[TTS_INIT] Mode: lucida_super_partes")
            
        except ImportError:
            logger.error("TTS package not available - install with: pip install TTS==0.22.0")
            self.model = None
            raise
        except Exception as e:
            logger.error(f"Failed to initialize XTTS v2: {e}")
            self.model = None
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
            
            # Verifica che XTTS sia disponibile
            if not self.model:
                logger.error("XTTS v2 not available - cannot synthesize")
                raise RuntimeError("XTTS v2 not initialized")
            
            # Genera filename se non fornito
            if output_file is None:
                import uuid
                output_file = f"tts_{uuid.uuid4()}.wav"
            
            output_path = self.tts_dir / output_file
            
            # Sintesi con speaker lock definitivo
            self._synthesize_lock_vocale(output_path, filtered_text)
            
            from core.log import log
            log("TTS_SYNTHESIZED", original_text=text[:50], filtered_text=filtered_text[:50], output=str(output_path))
            
            return str(output_path)
            
        except Exception as e:
            from core.log import log
            log("TTS_ERROR", error=str(e))
            raise
    
    def _synthesize_lock_vocale(self, output_path: Path, text: str):
        """
        Sintesi con speaker Alexandra Hisakawa lock definitivo
        """
        try:
            # Sintesi ESATTA come test manuale
            wav = self.model.tts(
                text=text,
                speaker=DEFAULT_SPEAKER,
                language=DEFAULT_LANGUAGE
            )
            
            # Sample rate nativo del modello (nessun forcing)
            sample_rate = getattr(self.model.synthesizer, 'output_sample_rate', 24000)
            
            # Salva WAV PCM 16-bit standard (nessuna manipolazione)
            import soundfile as sf
            sf.write(str(output_path), wav, sample_rate, subtype='PCM_16')
            
            # Log obbligatorio per ogni sintesi
            logger.info(f"[TTS_SYNTH] speaker={DEFAULT_SPEAKER} lang={DEFAULT_LANGUAGE} text_len={len(text)} duration={len(wav)/sample_rate:.2f}s samples={len(wav)}")
            
        except Exception as e:
            logger.error(f"Lock vocale synthesis failed: {e}")
            raise
    
    def _generate_wav_file(self, output_path: Path, text: str):
        """
        Metodo legacy - NON USATO
        """
        raise NotImplementedError("Use XTTS v2 with Alexandra Hisakawa lock")

# Istanza globale con lock vocale definitivo
simple_tts = SimpleTTS()
