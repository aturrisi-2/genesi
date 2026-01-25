import os
import uuid
from pathlib import Path
from typing import Optional

from TTS.api import TTS
from TTS.utils.synthesizer import Synthesizer

class TTSModel:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.model_name = "tts_models/it/mai_female/glow-tts"
            self.output_dir = Path("data/tts_cache")
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self._load_model()
            self._initialized = True
    
    def _load_model(self):
        """Carica il modello Coqui TTS"""
        try:
            self.synthesizer = TTS(self.model_name)
        except Exception as e:
            raise RuntimeError(f"Errore nel caricamento del modello TTS: {str(e)}")
    
    def synthesize(self, text: str) -> str:
        """
        Sintetizza il testo in parlato.
        
        Args:
            text: Testo da sintetizzare
            
        Returns:
            Percorso del file WAV generato
            
        Raises:
            ValueError: Se il testo è vuoto o non valido
            RuntimeError: In caso di errore nella sintesi
        """
        if not text or not isinstance(text, str) or not text.strip():
            raise ValueError("Il testo non può essere vuoto")
        
        try:
            # Genera un nome file univoco
            output_file = self.output_dir / f"tts_{uuid.uuid4()}.wav"
            
            # Esegue la sintesi
            self.synthesizer.tts_to_file(
                text=text,
                file_path=str(output_file)
            )
            
            return str(output_file.absolute())
            
        except Exception as e:
            raise RuntimeError(f"Errore durante la sintesi vocale: {str(e)}")

# Istanza globale del modello
_tts_model = TTSModel()

# Funzione pubblica
def synthesize(text: str) -> str:
    """
    Sintetizza il testo in parlato usando Coqui TTS.
    
    Args:
        text: Testo da sintetizzare
        
    Returns:
        Percorso assoluto del file WAV generato
        
    Raises:
        ValueError: Se il testo è vuoto o non valido
        RuntimeError: In caso di errore nella sintesi
    """
    return _tts_model.synthesize(text)

# Test locale
if __name__ == "__main__":
    try:
        test_text = "Ciao, questo è un test di sintesi vocale con Coqui TTS."
        audio_file = synthesize(test_text)
        print(f"Audio generato: {audio_file}")
    except Exception as e:
        print(f"Errore: {str(e)}")