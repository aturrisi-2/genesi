import uuid
import subprocess
from pathlib import Path
from typing import Optional

from TTS.api import TTS


class TTSModel:
    """
    Singleton per il modello Coqui TTS.
    Carica il modello una sola volta e lo riutilizza.
    """
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.model_name = "tts_models/it/mai_female/glow-tts"

        # Directory output
        self.output_dir = Path("data/tts_cache")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._load_model()
        self._initialized = True

    def _load_model(self):
        """
        Carica il modello Coqui TTS.
        """
        try:
            self.tts = TTS(
                model_name=self.model_name,
                progress_bar=False,
                gpu=False
            )
        except Exception as e:
            raise RuntimeError(f"Errore nel caricamento del modello TTS: {e}")

    def synthesize(self, text: str) -> str:
        """
        Sintetizza il testo in parlato e restituisce il path del WAV finale.

        Pipeline:
        1. Coqui raw wav
        2. Pulizia anti-metallo / anti-caverna (sox)
        3. Micro-silenzio iniziale e finale

        Args:
            text (str): testo da sintetizzare

        Returns:
            str: percorso assoluto del file WAV finale
        """
        if not text or not isinstance(text, str) or not text.strip():
            raise ValueError("Il testo non può essere vuoto")

        # File temporanei
        raw_file = self.output_dir / f"tts_{uuid.uuid4().hex}_raw.wav"
        clean_file = self.output_dir / f"{raw_file.stem}_clean.wav"
        final_file = self.output_dir / f"{raw_file.stem}_final.wav"

        try:
            # 1️⃣ Sintesi raw
            safe_text = "… " + text.strip()

            self.tts.tts_to_file(
                text=safe_text,
                file_path=str(raw_file)
            )


            # 2️⃣ De-metal + anti-caverna (EQ + compand leggero)
            subprocess.run(
                [
                    "sox",
                    str(raw_file),
                    str(clean_file),
                    "highpass", "80",
                    "lowpass", "7200",
                    "compand", "0.3,1", "6:-70,-60,-20", "-5", "-90", "0.2"
                ],
                check=True
            )

            # 3️⃣ Micro-silenzio umano (respiro)
            subprocess.run(
                [
                    "sox",
                    str(clean_file),
                    str(final_file),
                    "pad", "0.05", "0.05"
                ],
                check=True
            )

            return str(final_file.resolve())

        except Exception as e:
            raise RuntimeError(f"Errore durante la sintesi vocale: {e}")

        finally:
            # Pulizia file temporanei
            try:
                if raw_file.exists():
                    raw_file.unlink()
                if clean_file.exists():
                    clean_file.unlink()
            except Exception:
                pass


# Istanza globale (singleton)
_tts_model = TTSModel()


def synthesize(text: str) -> str:
    """
    Funzione pubblica per la sintesi vocale.

    Args:
        text (str): testo da sintetizzare

    Returns:
        str: percorso assoluto del file WAV finale
    """
    return _tts_model.synthesize(text)


# Test locale manuale
if __name__ == "__main__":
    audio = synthesize("Ciao. Questa voce ora è più naturale e meno metallica.")
    print("Audio generato:", audio)
