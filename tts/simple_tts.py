"""
TTS SIMPLE - Genesi Core v2
1 intent → 1 funzione
Text-to-Speech con Coqui TTS e voce italiana reale
"""

from pathlib import Path
import logging
from typing import Optional
from core.emoji_filter import emoji_filter

logger = logging.getLogger(__name__)

class SimpleTTS:
    """
    TTS semplice - 1 intent → 1 funzione
    Con filtro emoji per TTS (non per chat) e Coqui TTS
    """
    
    def __init__(self):
        self.tts_dir = Path("tts_cache")
        self.tts_dir.mkdir(exist_ok=True)
        # Inizializza Coqui TTS
        self._init_coqui()
    
    def _init_coqui(self):
        """Inizializza Coqui TTS con voce italiana"""
        try:
            import coqui
            self.coqui = coqui
            # Modello vocale italiano
            self.model_path = "coqui/it/v1.0"
            logger.info("Coqui TTS initialized with Italian model")
        except ImportError:
            logger.error("Coqui TTS not available - install with: pip install coqui")
            raise ImportError("Coqui TTS is required. Install with: pip install coqui")
    
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
        Sintesi vocale con Coqui TTS
        """
        import torch
        import torchaudio
        
        # Carica modello Coqui
        model = self.coqui.load_model(self.model_path)
        
        # Genera audio
        with torch.no_grad():
            audio = model.generate(text=text)
        
        # Salva come WAV
        torchaudio.save(output_path, audio, sample_rate=model.sample_rate)
        
        logger.info(f"Coqui TTS generated audio: {len(audio)} samples at {model.sample_rate}Hz")
    
    def _generate_wav_file(self, output_path: Path, text: str):
        """
        Metodo legacy - NON USATO
        Mantenuto solo per compatibilità ma non chiamato
        """
        raise NotImplementedError("Use Coqui TTS instead")

# Istanza globale
simple_tts = SimpleTTS()
