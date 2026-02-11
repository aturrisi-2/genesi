"""
TTS SIMPLE - Genesi Core v2
1 intent → 1 funzione
Text-to-Speech con XTTS v2 - Alexandra Hisakawa 24000Hz CPU OTTIMIZZATA
"""

from pathlib import Path
import logging
from typing import Optional, Dict
from core.emoji_filter import emoji_filter
import re
import torch
import hashlib
import time

logger = logging.getLogger(__name__)

# CONFIGURAZIONE VOCE ORIGINALE
VOICE_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"
VOICE_SPEAKER = "Alexandra Hisakawa"
VOICE_LANGUAGE = "it"
VOICE_SAMPLE_RATE = 24000  # FISSO - NON MODIFICARE

# 2️⃣ TORCH THREADS OTTIMIZZATI per VPS 4 core
torch.set_num_threads(2)  # Ottimizzazione per CPU multi-core
torch.set_num_interop_threads(1)  # Riduci overhead

# 5️⃣ CACHE INTELLIGENTE
_tts_cache: Dict[str, str] = {}
_cache_max_size = 50

def clean_tts_text(text: str) -> str:
    """
    4️⃣ PRE-SANIFICAZIONE TESTO (no punteggiatura parlata)
    Rimuove problemi prima di passare a XTTS
    """
    original = text
    
    # Rimuovi caratteri ripetuti
    text = re.sub(r'([!?.,])\1+', r'\1', text)
    
    # Rimuovi spazi multipli
    text = re.sub(r'\s+', ' ', text)
    
    # Sostituisci punteggiatura problematica
    text = text.replace(':', ' ')  # Pausa leggera invece di ":"
    text = text.replace(';', ' ')
    text = text.replace('...', '.')  # Normalizza puntini sospensivi
    
    # Rimuovi caratteri strani che XTTS potrebbe leggere
    text = re.sub(r'[^\w\s\.,!?\'-]', ' ', text)
    
    # Converti numeri semplici (base)
    text = re.sub(r'\b(\d{1,2}):(\d{2})\b', lambda m: f"{_numero_italiano(int(m.group(1)))} e {_numero_italiano(int(m.group(2)))}", text)
    
    # Rimuovi punto finale su testi brevi
    if len(text) < 40 and text.endswith('.'):
        text = text[:-1]
    
    # Trim finale
    text = text.strip()
    
    print(f"CLEAN_TTS_TEXT original={original[:50]}... cleaned={text[:50]}...")
    return text

def _numero_italiano(n: int) -> str:
    """Converte numero semplice in italiano"""
    numeri = {
        0: 'zero', 1: 'uno', 2: 'due', 3: 'tre', 4: 'quattro', 5: 'cinque',
        6: 'sei', 7: 'sette', 8: 'otto', 9: 'nove', 10: 'dieci', 11: 'undici',
        12: 'dodici', 13: 'tredici', 14: 'quattordici', 15: 'quindici', 16: 'sedici',
        17: 'diciassette', 18: 'diciotto', 19: 'diciannove', 20: 'venti', 21: 'ventuno',
        22: 'ventidue', 23: 'ventitre', 24: 'ventiquattro', 25: 'venticinque',
        30: 'trenta', 40: 'quaranta', 50: 'cinquanta'
    }
    return numeri.get(n, str(n))

def smart_chunk_text(text: str) -> list:
    """
    3️⃣ DISABILITARE SPLIT AGGRESSIVO - chunk per lunghezza, non per punteggiatura
    """
    if len(text) < 180:
        print("SMART_CHUNK_COUNT 1 (no chunk)")
        return [text]
    
    # Split in blocchi 180-220 caratteri mantenendo parole intere
    chunks = []
    current_chunk = ""
    words = text.split()
    
    for word in words:
        test_chunk = current_chunk + " " + word if current_chunk else word
        
        if len(test_chunk) <= 220:  # Max 220 char
            current_chunk = test_chunk
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = word
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    print(f"SMART_CHUNK_COUNT {len(chunks)}")
    return chunks

def _get_cache_key(text: str) -> str:
    """Genera cache key per testo"""
    return hashlib.md5(text.encode()).hexdigest()

def _get_cached_audio(cache_key: str) -> Optional[str]:
    """Ottiene audio dalla cache se esiste"""
    if cache_key in _tts_cache:
        cached_path = _tts_cache[cache_key]
        if Path(cached_path).exists():
            print(f"CACHE_HIT: {cache_key}")
            return cached_path
        else:
            # Rimuovi cache non valido
            del _tts_cache[cache_key]
    return None

def _cache_audio(cache_key: str, audio_path: str):
    """Aggiunge audio alla cache"""
    global _tts_cache
    if len(_tts_cache) >= _cache_max_size:
        # Rimuovi elemento più vecchio (semplice FIFO)
        oldest_key = next(iter(_tts_cache))
        del _tts_cache[oldest_key]
    
    _tts_cache[cache_key] = audio_path
    print(f"CACHE_STORE: {cache_key} -> {audio_path}")

class SimpleTTS:
    """
    TTS semplice - 1 intent → 1 funzione
    Con filtro emoji per TTS (non per chat) e XTTS v2 CPU OTTIMIZZATA
    """
    
    def __init__(self):
        self.tts_dir = Path("tts_cache")
        self.tts_dir.mkdir(exist_ok=True)
        # 1️⃣ CARICAMENTO MODELLO UNA SOLA VOLTA (Warm Load)
        self.tts = None
        self._init_xtts()
    
    def _init_xtts(self):
        """1️⃣ Inizializza XTTS v2 - UNICA VOLTA con ottimizzazioni CPU"""
        try:
            from TTS.api import TTS
            
            print("VOICE_WARM_LOAD: Starting XTTS v2 initialization...")
            start_time = time.time()
            
            # CONFIGURAZIONE ORIGINALE - XTTS v2 con ottimizzazioni
            self.tts = TTS(
                model_name=VOICE_MODEL,
                use_cuda=False,  # Forza CPU per stabilità
                gpu=False
            )
            
            init_time = time.time() - start_time
            print(f"VOICE_WARM_LOAD: XTTS v2 initialized in {init_time:.2f}s")
            
            # LOG DI CONFERMA BOOT
            print("VOICE MODEL ACTIVE: XTTS v2 (CPU optimized)")
            print(f"VOICE SPEAKER ACTIVE: {VOICE_SPEAKER}")
            print(f"VOICE SAMPLE RATE: {VOICE_SAMPLE_RATE}")
            print(f"TORCH THREADS: {torch.get_num_threads()}")
            
            logger.info(f"[VOICE_LOCK] Model: {VOICE_MODEL}")
            logger.info(f"[VOICE_LOCK] Speaker: {VOICE_SPEAKER}")
            logger.info(f"[VOICE_LOCK] Language: {VOICE_LANGUAGE}")
            logger.info(f"[VOICE_LOCK] Sample Rate: {VOICE_SAMPLE_RATE}Hz (FISSO)")
            
        except ImportError:
            logger.error("TTS package not available - install with: pip install TTS==0.22.0")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize XTTS v2: {e}")
            raise
    
    def synthesize(self, text: str, output_file: Optional[str] = None) -> str:
        """
        Sintesi vocale - 1 intent → 1 funzione con cache
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
            
            # Verifica XTTS disponibile
            if not self.tts:
                logger.error("XTTS v2 not available - cannot synthesize")
                raise RuntimeError("XTTS v2 not initialized")
            
            # 5️⃣ CACHE INTELLIGENTE
            cache_key = _get_cache_key(filtered_text)
            cached_path = _get_cached_audio(cache_key)
            if cached_path:
                return cached_path
            
            # Genera filename se non fornito
            if output_file is None:
                import uuid
                output_file = f"tts_{uuid.uuid4()}.wav"
            
            output_path = self.tts_dir / output_file
            
            # Sintesi OTTIMIZZATA
            self._synthesize_ottimizzato(output_path, filtered_text)
            
            # 5️⃣ CACHE RESULT
            _cache_audio(cache_key, str(output_path))
            
            from core.log import log
            log("TTS_SYNTHESIZED", original_text=text[:50], filtered_text=filtered_text[:50], output=str(output_path))
            
            return str(output_path)
            
        except Exception as e:
            from core.log import log
            log("TTS_ERROR", error=str(e))
            raise
    
    def _synthesize_ottimizzato(self, output_path: Path, text: str):
        """
        Sintesi OTTIMIZZATA - Alexandra Hisakawa 24000Hz
        """
        try:
            start_time = time.time()
            
            # 4️⃣ NORMALIZZAZIONE TESTO
            text = clean_tts_text(text)
            
            # 3️⃣ CHUNKING INTELLIGENTE (no split frase)
            chunks = smart_chunk_text(text)
            
            if len(chunks) == 1:
                # Testo breve: sintesi diretta
                self._synthesize_single_chunk(output_path, chunks[0])
            else:
                # Testo lungo: gestisci primo chunk
                self._synthesize_first_chunk(output_path, chunks[0])
            
            total_time = time.time() - start_time
            print(f"SYNTHESIS_TIME: {total_time:.2f}s for {len(text)} chars")
            
        except Exception as e:
            logger.error(f"Optimized synthesis failed: {e}")
            raise
    
    def _synthesize_single_chunk(self, output_path: Path, text: str):
        """Sintesi singolo chunk - ottimizzata con parametri velocità"""
        try:
            # 6️⃣ PARAMETRI XTTS VELOCITÀ (senza cambiare timbro)
            wav = self.tts.tts(
                text=text,
                speaker=VOICE_SPEAKER,
                language=VOICE_LANGUAGE,
                # Parametri ottimizzazione velocità
                speed=1.1,  # Leggermente più veloce
                # NON tocchiamo: speaker, sample_rate, modello
            )
            
            # SALVATAGGIO ORIGINALE - 24000Hz FISSO
            import soundfile as sf
            sf.write(str(output_path), wav, VOICE_SAMPLE_RATE)
            
            # LOG SINTESI ORIGINALE
            duration = len(wav) / VOICE_SAMPLE_RATE
            rtf = duration / (len(text) / 10.0)  # RTF approssimativo (10 char/sec)
            logger.info(f"[VOICE_OPT_SINGLE] speaker={VOICE_SPEAKER} lang={VOICE_LANGUAGE} sr={VOICE_SAMPLE_RATE}Hz duration={duration:.2f}s samples={len(wav)} rtf={rtf:.2f}")
            
        except Exception as e:
            logger.error(f"Single chunk synthesis failed: {e}")
            raise
    
    def _synthesize_first_chunk(self, output_path: Path, text: str):
        """Sintesi primo chunk per streaming - ottimizzata"""
        # Sintesi primo chunk (gli altri verranno gestiti dallo streaming)
        self._synthesize_single_chunk(output_path, text)
    
    def _generate_wav_file(self, output_path: Path, text: str):
        """
        Metodo legacy - NON USATO
        """
        raise NotImplementedError("Use XTTS v2 with Alexandra Hisakawa lock")

# 1️⃣ ISTANZA GLOBALE - CARICATA UNA VOLTA
print("VOICE_INIT: Starting global TTS instance...")
simple_tts = SimpleTTS()
print("VOICE_INIT: Global TTS instance ready")
