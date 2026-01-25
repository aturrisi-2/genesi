import uuid
import subprocess
from pathlib import Path

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
        1. Coqui raw wav (con pre-buffer testuale)
        2. Pulizia anti-metallo / anti-caverna
        3. Pitch down leggero (calore)
        4. Micro-silenzio umano iniziale e finale
        """
        if not text or not isinstance(text, str) or not text.strip():
            raise ValueError("Il testo non può essere vuoto")

        # File temporanei
        raw_file = self.output_dir / f"tts_{uuid.uuid4().hex}_raw.wav"
        clean_file = self.output_dir / f"{raw_file.stem}_clean.wav"
        warm_file = self.output_dir / f"{raw_file.stem}_warm.wav"
        final_file = self.output_dir / f"{raw_file.stem}_final.wav"

        try:
            # 1️⃣ Pre-buffer per evitare inizio mangiato
            safe_text = "… " + text.strip()

            self.tts.tts_to_file(
                text=safe_text,
                file_path=str(raw_file)
            )

            # 2️⃣ Pulizia anti-metallo / anti-caverna
            subprocess.run(
                [
                    "sox",
                    str(raw_file),
                    str(clean_file),
                    "highpass", "70",
                    "lowpass", "6800",
                    "compand", "0.4,1", "6:-65,-55,-25", "-3", "-80", "0.15"
                ],
                check=True
            )

            # 3️⃣ Calore: pitch leggermente più basso (voce più profonda)
            subprocess.run(
                [
                    "sox",
                    str(clean_file),
                    str(warm_file),
                    "pitch", "-40"
                ],
                check=True
            )

            # 4️⃣ Micro-silenzio umano (respiro)
            subprocess.run(
                [
                    "sox",
                    str(warm_file),
                    str(final_file),
                    "pad", "0.06", "0.06"
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
                if warm_file.exists():
                    warm_file.unlink()
            except Exception:
                pass


# Istanza globale (singleton)
_tts_model = TTSModel()


def synthesize(text: str) -> str:
    """
    Funzione pubblica per la sintesi vocale.
    """
    return _tts_model.synthesize(text)


# Test locale manuale
if __name__ == "__main__":
    audio = synthesize(
        "Questa voce è più profonda, calda e naturale, senza effetto robotico."
    )
    print("Audio generato:", audio)
