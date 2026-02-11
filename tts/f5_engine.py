"""
F5-TTS ENGINE - Genesi Core v2
Nuovo motore vocale principale alternativo a XTTS
Produzione-ready con logging e ottimizzazione 6-core
"""

import torch
import time
import logging
from pathlib import Path
from typing import Optional
from core.log import log

logger = logging.getLogger(__name__)

# Configurazione F5-TTS
F5_MODEL_NAME = "F5-TTS"  # Modello F5-TTS base
F5_SAMPLE_RATE = 24000  # Sample rate fisso
F5_VOICE_SPEED = 1.0  # Velocità normale

# Cache e configurazione
_f5_model = None
_f5_initialized = False

def _init_f5_model():
    """Inizializza modello F5-TTS globalmente - una sola volta"""
    global _f5_model, _f5_initialized
    
    if _f5_initialized:
        return _f5_model
    
    try:
        print("F5_INIT_START")
        start_time = time.time()
        
        # Import e inizializzazione F5-TTS
        from f5_tts.model import F5TTS
        
        # Carica modello F5-TTS
        _f5_model = F5TTS(
            model_name=F5_MODEL_NAME,
            device="cpu"  # Forza CPU per consistenza
        )
        
        init_time = time.time() - start_time
        print(f"F5_MODEL_LOADED in {init_time:.2f}s")
        
        # Log configurazione
        print(f"F5 THREADS: {torch.get_num_threads()}")
        print(f"F5 INTEROP THREADS: {torch.get_num_interop_threads()}")
        print(f"F5 SAMPLE RATE: {F5_SAMPLE_RATE}Hz")
        
        _f5_initialized = True
        logger.info(f"[F5_ENGINE] Model: {F5_MODEL_NAME} initialized in {init_time:.2f}s")
        
        return _f5_model
        
    except ImportError:
        logger.error("F5-TTS package not available - install with: pip install f5-tts")
        raise
    except Exception as e:
        logger.error(f"Failed to initialize F5-TTS: {e}")
        raise

def synthesize_f5(text: str, output_path: str) -> str:
    """
    Sintesi vocale con F5-TTS
    
    Args:
        text: Testo da sintetizzare
        output_path: Percorso file output
        
    Returns:
        Percorso file audio generato
    """
    try:
        print("F5_SYNTHESIS_START")
        start_time = time.time()
        
        # Verifica modello inizializzato
        model = _init_f5_model()
        
        if not text.strip():
            raise ValueError("Empty text for synthesis")
        
        # Converti percorso in Path
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Sintesi F5-TTS
        with torch.no_grad():
            wav = model.inference(
                text=text,
                speed=F5_VOICE_SPEED,
                sample_rate=F5_SAMPLE_RATE
            )
        
        # Salva file WAV
        import soundfile as sf
        sf.write(str(output_file), wav, F5_SAMPLE_RATE)
        
        # Calcola metriche
        synthesis_time = time.time() - start_time
        duration = len(wav) / F5_SAMPLE_RATE
        rtf = duration / synthesis_time if synthesis_time > 0 else 0
        
        print(f"F5_SYNTHESIS_TIME: {synthesis_time:.2f}s")
        print(f"F5_AUDIO_DURATION: {duration:.2f}s")
        print(f"F5_REAL_TIME_FACTOR: {rtf:.2f}")
        
        # Log completamento
        log("F5_SYNTHESIZED", 
            text_length=len(text), 
            synthesis_time=synthesis_time,
            audio_duration=duration,
            rtf=rtf,
            output_path=str(output_file)
        )
        
        return str(output_file)
        
    except Exception as e:
        print(f"F5_ERROR: {e}")
        log("F5_ERROR", error=str(e))
        raise

def get_f5_info():
    """Informazioni stato motore F5-TTS"""
    return {
        "model": F5_MODEL_NAME,
        "sample_rate": F5_SAMPLE_RATE,
        "initialized": _f5_initialized,
        "threads": torch.get_num_threads(),
        "interop_threads": torch.get_num_interop_threads()
    }

# Inizializzazione globale (lazy)
print("F5_ENGINE: Engine ready (lazy initialization)")

# Funzione di warm-up opzionale
def warm_up_f5():
    """Warm-up del motore F5-TTS"""
    try:
        _init_f5_model()
        print("F5_WARMUP_COMPLETE")
        return True
    except Exception as e:
        print(f"F5_WARMUP_ERROR: {e}")
        return False
