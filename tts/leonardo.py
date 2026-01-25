# == LEONARDO VEIRSIONE WINDSURF TEST 001 ==

import asyncio
import json
import shutil
import uuid
from pathlib import Path
from typing import Optional

# Configurazione
MODEL_PATH = "/opt/leonardo/models/leonardo.onnx"
MODEL_CONFIG_PATH = "/opt/leonardo/models/leonardo.onnx.json"
OUTPUT_DIR = Path("data/tts")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Verifica che il modello esista
if not Path(MODEL_PATH).exists():
    raise FileNotFoundError(f"Modello non trovato in {MODEL_PATH}")

if not Path(MODEL_CONFIG_PATH).exists():
    raise FileNotFoundError(f"Configurazione modello non trovata in {MODEL_CONFIG_PATH}")

class TTSError(Exception):
    """Eccezione personalizzata per errori di sintesi vocale"""
    pass

async def synthesize(text: str) -> str:
    """
    Sintetizza il testo in parlato usando Piper TTS.
    
    Args:
        text: Testo da sintetizzare (max 1000 caratteri)
        
    Returns:
        Percorso assoluto del file WAV generato
        
    Raises:
        ValueError: Se il testo è vuoto o troppo lungo
        TTSError: In caso di errore durante la sintesi
    """
    if not text or not isinstance(text, str):
        raise ValueError("Il testo non può essere vuoto")
        
    text = text.strip()
    if not text:
        raise ValueError("Il testo non può contenere solo spazi vuoti")
        
    if len(text) > 1000:
        raise ValueError("Il testo non può superare i 1000 caratteri")
    
    # Genera un nome file univoco
    output_file = OUTPUT_DIR / f"tts_{uuid.uuid4()}.wav"
    
    try:
        # Esegui il comando piper
        process = await asyncio.create_subprocess_exec(
            "python", "-m", "piper",
            "--model", MODEL_PATH,
            "--config", MODEL_CONFIG_PATH,
            "--output_file", str(output_file),
            "--length-scale", "1.0",
            "--noise-scale", "0.20",
            "--noise-w-scale", "0.6",
            "--sentence-silence", "1.0",
            "--sentence-gap", "0.15",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Invia il testo a piper
        stdout, stderr = await process.communicate(input=text.encode('utf-8'))
        
        # Verifica lo stato di uscita
        if process.returncode != 0:
            error_msg = stderr.decode('utf-8', errors='replace')
            raise TTSError(f"Errore durante la sintesi: {error_msg}")
            
        # Verifica che il file sia stato creato
        if not output_file.exists():
            raise TTSError("Il file audio non è stato generato correttamente")
            
        return str(output_file.absolute())
        
    except asyncio.TimeoutError:
        raise TTSError("Timeout durante la sintesi vocale")
    except Exception as e:
        raise TTSError(f"Errore durante la sintesi vocale: {str(e)}")

async def main():
    """Funzione di test per la sintesi vocale"""
    try:
        test_text = "Ciao, questo è un test di sintesi vocale con la voce di Leonardo."
        print(f"Sintetizzando: {test_text}")
        output_file = await synthesize(test_text)
        print(f"File generato: {output_file}")
    except Exception as e:
        print(f"Errore: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())