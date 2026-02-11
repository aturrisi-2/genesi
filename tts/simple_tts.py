"""
TTS SIMPLE - Genesi Core v2
1 intent → 1 funzione
Text-to-Speech con XTTS v2 - voce seria senza compromessi
"""

from pathlib import Path
import logging
from typing import Optional
from core.emoji_filter import emoji_filter

logger = logging.getLogger(__name__)

class SimpleTTS:
    """
    TTS semplice - 1 intent → 1 funzione
    Con filtro emoji per TTS (non per chat) e XTTS v2
    """
    
    def __init__(self):
        self.tts_dir = Path("tts_cache")
        self.tts_dir.mkdir(exist_ok=True)
        # Inizializza Coqui TTS con modello superiore
        self._init_coqui()
    
    def _init_coqui(self):
        """Inizializza Coqui TTS con modello XTTS v2 (voce seria)"""
        try:
            from TTS.api import TTS
            
            # FASE 2: Modello superiore XTTS v2
            self.tts = TTS(
                model_name="tts_models/multilingual/multi-dataset/xtts_v2",
                progress_bar=False
            )
            logger.info("Coqui TTS initialized with XTTS v2: tts_models/multilingual/multi-dataset/xtts_v2")
            
        except ImportError:
            logger.error("TTS package not available - install with: pip install TTS==0.22.0")
            self.tts = None
        except Exception as e:
            logger.error(f"Failed to initialize XTTS v2: {e}")
            # FASE 2: Fallback a modello italiano VITS migliore
            try:
                from TTS.api import TTS
                self.tts = TTS(
                    model_name="tts_models/it/mai_male/vits",
                    progress_bar=False
                )
                logger.info("Fallback to Italian male VITS: tts_models/it/mai_male/vits")
            except Exception as fallback_error:
                logger.error(f"Failed to initialize fallback model: {fallback_error}")
                self.tts = None
    
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
            
            # Verifica che TTS sia disponibile
            if not self.tts:
                logger.error("TTS not available - cannot synthesize")
                raise RuntimeError("TTS not initialized")
            
            # Genera filename se non fornito
            if output_file is None:
                import uuid
                output_file = f"tts_{uuid.uuid4()}.wav"
            
            output_path = self.tts_dir / output_file
            
            # FASE 3: Audio puro - nessuna manipolazione
            self._synthesize_pure_audio(output_path, filtered_text)
            
            from core.log import log
            log("TTS_SYNTHESIZED", original_text=text[:50], filtered_text=filtered_text[:50], output=str(output_path))
            
            return str(output_path)
            
        except Exception as e:
            from core.log import log
            log("TTS_ERROR", error=str(e))
            raise
    
    def _synthesize_pure_audio(self, output_path: Path, text: str):
        """
        FASE 3: Audio puro - nessuna normalizzazione, trim, o manipolazione
        """
        try:
            # Genera WAV con XTTS v2
            wav = self.tts.tts(text=text)
            
            # FASE 3: Sample rate nativo del modello
            sample_rate = self.tts.synthesizer.output_sample_rate
            
            # FASE 3: Salva WAV PCM 16-bit standard - nessuna manipolazione
            import soundfile as sf
            sf.write(str(output_path), wav, sample_rate, subtype='PCM_16')
            
            # FASE 4: Logging dettagliato
            duration = len(wav) / sample_rate
            logger.info(f"XTTS AUDIO PURO - model={self.tts.model_name}, sample_rate={sample_rate}, duration={duration:.2f}s, samples={len(wav)}")
            
        except Exception as e:
            logger.error(f"Pure audio synthesis failed: {e}")
            raise
    
    def _generate_wav_file(self, output_path: Path, text: str):
        """
        Metodo legacy - NON USATO
        Mantenuto solo per compatibilità ma non chiamato
        """
        raise NotImplementedError("Use XTTS v2 instead")

# Istanza globale
simple_tts = SimpleTTS()
