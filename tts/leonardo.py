import os
import asyncio
import uuid
import shutil
from pathlib import Path
from typing import Optional

# Configurazione
MODEL_PATH = "/opt/leonardo/models/leonardo.onnx"
MODEL_CONFIG_PATH = "/opt/leonardo/models/leonardo.onnx.json"
OUTPUT_DIR = "data/tts"
DEFAULT_TIMEOUT = 30

# Crea la directory di output se non esiste
os.makedirs(OUTPUT_DIR, exist_ok=True)

async def synthesize(text: str) -> str:
    """
    Genera un file WAV con la voce Leonardo usando Piper
    e restituisce il path assoluto del file.
    
    Args:
        text: Testo da sintetizzare (massimo 1000 caratteri)
        
    Returns:
        str: Path assoluto del file WAV generato
        
    Raises:
        ValueError: Se il testo non è valido
        RuntimeError: Se la sintesi vocale fallisce
    """
    # Validazione input
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Il testo non può essere vuoto")
    
    if len(text) > 1000:
        raise ValueError("Il testo non può superare i 1000 caratteri")
    
    # Genera un nome file univoco
    output_file = Path(OUTPUT_DIR) / f"tts_{uuid.uuid4()}.wav"
    
    try:
        # Esegui il comando piper
        process = await asyncio.create_subprocess_exec(
            "python", "-m", "piper",
            "--model", MODEL_PATH,
            "--config", MODEL_CONFIG_PATH,
            "--output_file", str(output_file),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Invia il testo a piper
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=text.encode('utf-8')),
                timeout=DEFAULT_TIMEOUT
            )
            
            # Verifica l'uscita
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='replace') if stderr else "Errore sconosciuto"
                raise RuntimeError(f"Errore durante la sintesi vocale: {error_msg}")
                
            if not output_file.exists():
                raise RuntimeError("Il file di output non è stato generato correttamente")
                
            return str(output_file.absolute())
            
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError(f"Timeout durante la sintesi vocale (limite: {DEFAULT_TIMEOUT}s)")
            
    except FileNotFoundError as e:
        if "No such file or directory: 'python'" in str(e):
            raise RuntimeError("Impossibile trovare il comando 'python'. Assicurati che Python sia installato e nel PATH.")
        raise RuntimeError(f"Errore durante l'esecuzione di Piper: {str(e)}")
    except Exception as e:
        raise RuntimeError(f"Errore durante la sintesi vocale: {str(e)}")

async def main():
    """Funzione di test per la sintesi vocale"""
    try:
        test_text = "Ciao, questo è un test di sintesi vocale con la voce di Leonardo."
        print(f"Generazione sintesi vocale per: {test_text}")
        wav_path = await synthesize(test_text)
        print(f"File generato con successo: {wav_path}")
    except Exception as e:
        print(f"Errore durante il test: {str(e)}")
        return 1
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))