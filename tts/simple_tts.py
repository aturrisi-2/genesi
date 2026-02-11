"""
TTS SIMPLE - Genesi Core v2
1 intent → 1 funzione
Text-to-Speech con Coqui TTS API ufficiale e voce italiana reale
"""

from pathlib import Path
import logging
from typing import Optional
from core.emoji_filter import emoji_filter

logger = logging.getLogger(__name__)

class SimpleTTS:
    """
    TTS semplice - 1 intent → 1 funzione
    Con filtro emoji per TTS (non per chat) e Coqui TTS API ufficiale
    """
    
    def __init__(self):
        self.tts_dir = Path("tts_cache")
        self.tts_dir.mkdir(exist_ok=True)
        # Inizializza Coqui TTS con API ufficiale
        self._init_coqui()
    
    def _init_coqui(self):
        """Inizializza Coqui TTS con API ufficiale"""
        try:
            from TTS.api import TTS
            
            # Inizializza Coqui TTS con modello VITS italiano (voce umana naturale)
            self.tts = TTS(
                model_name="tts_models/it/mai_female/vits",
                progress_bar=False
            )
            logger.info("Coqui TTS initialized with VITS Italian model: tts_models/it/mai_female/vits")
            
        except ImportError:
            logger.error("TTS package not available - install with: pip install TTS==0.22.0")
            self.tts = None
        except Exception as e:
            logger.error(f"Failed to initialize Coqui TTS: {e}")
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
            
            # Verifica che Coqui TTS sia disponibile
            if not self.tts:
                logger.error("Coqui TTS not available - cannot synthesize")
                raise RuntimeError("TTS not initialized")
            
            # Genera filename se non fornito
            if output_file is None:
                import uuid
                output_file = f"tts_{uuid.uuid4()}.wav"
            
            output_path = self.tts_dir / output_file
            
            # Sintesi vocale con Coqui TTS
            self._synthesize_with_coqui(output_path, filtered_text)
            
            from core.log import log
            log("TTS_SYNTHESIZED", original_text=text[:50], filtered_text=filtered_text[:50], output=str(output_path))
            
            return str(output_path)
            
        except Exception as e:
            from core.log import log
            log("TTS_ERROR", error=str(e))
            raise
    
    def _synthesize_with_coqui(self, output_path: Path, text: str):
        """
        Sintesi vocale con Coqui TTS API ufficiale
        """
        try:
            # Genera WAV con Coqui TTS
            wav = self.tts.tts(text)
            
            # Salva WAV PCM reale
            import soundfile as sf
            sf.write(str(output_path), wav, self.tts.synthesizer.output_sample_rate)
            
            logger.info(f"Coqui TTS generated audio: {len(wav)} samples at {self.tts.synthesizer.output_sample_rate}Hz")
            
        except Exception as e:
            logger.error(f"Coqui TTS synthesis failed: {e}")
            raise
    
    def _generate_wav_file(self, output_path: Path, text: str):
        """
        Metodo legacy - NON USATO
        Mantenuto solo per compatibilità ma non chiamato
        """
        raise NotImplementedError("Use Coqui TTS instead")

# Istanza globale
simple_tts = SimpleTTS()
