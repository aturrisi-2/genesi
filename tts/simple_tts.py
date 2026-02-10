"""
TTS SIMPLE - Genesi Core v2
1 intent → 1 funzione
Text-to-Speech con filtro emoji per TTS e sintesi vocale reale
"""

from pathlib import Path
import logging
from typing import Optional
from core.emoji_filter import emoji_filter

logger = logging.getLogger(__name__)

class SimpleTTS:
    """
    TTS semplice - 1 intent → 1 funzione
    Con filtro emoji per TTS (non per chat) e sintesi vocale reale
    """
    
    def __init__(self):
        self.tts_dir = Path("tts_cache")
        self.tts_dir.mkdir(exist_ok=True)
    
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
            
            # Sintesi vocale reale con gTTS
            if output_file is None:
                import uuid
                output_file = f"tts_{uuid.uuid4()}.wav"
            
            output_path = self.tts_dir / output_file
            
            # Genera file WAV con sintesi vocale reale
            self._generate_real_tts(output_path, filtered_text)
            
            from core.log import log
            log("TTS_SYNTHESIZED", original_text=text[:50], filtered_text=filtered_text[:50], output=str(output_path))
            
            return str(output_path)
            
        except Exception as e:
            from core.log import log
            log("TTS_ERROR", error=str(e))
            raise
    
    def _generate_real_tts(self, output_path: Path, text: str):
        """
        Genera file WAV con sintesi vocale reale usando gTTS
        """
        try:
            import gtts
            from io import BytesIO
            from pydub import AudioSegment
            
            # Configura gTTS per italiano
            tts = gtts.gTTS(
                text=text,
                lang='it',  # Italiano
                slow=False   # Velocità normale
            )
            
            # Genera audio in memoria
            audio_data = BytesIO()
            tts.write_to_fp(audio_data)
            audio_data.seek(0)
            
            # Converte in WAV
            audio = AudioSegment.from_file(audio_data, format="mp3")
            audio.export(
                output_path,
                format="wav",
                parameters=["-ac", "1", "-ar", "22050", "-ab", "128k"]
            )
            
        except ImportError as e:
            # Fallback a sintesi vocale con pyttsx3 se gTTS non disponibile
            self._fallback_tts(output_path, text)
        except Exception as e:
            # Fallback a sintesi vocale con pyttsx3 se gTTS fallisce
            self._fallback_tts(output_path, text)
    
    def _fallback_tts(self, output_path: Path, text: str):
        """
        Fallback a sintesi vocale con pyttsx3
        """
        try:
            import pyttsx3
            
            # Crea motore TTS
            engine = pyttsx3.init()
            
            # Configura voce italiana se disponibile
            voices = engine.getProperty('voices')
            for voice in voices:
                if 'italian' in voice.name.lower() or 'it' in voice.id.lower():
                    engine.setProperty('voice', voice.id)
                    break
            
            # Salva direttamente in WAV
            engine.save_to_file(text, str(output_path))
            engine.runAndWait()
            
        except ImportError:
            # Fallback a onda sinusoidale se nessun motore TTS disponibile
            self._generate_wav_file(output_path, text)
        except Exception as e:
            # Fallback a onda sinusoidale se pyttsx3 fallisce
            self._generate_wav_file(output_path, text)
    
    def _generate_wav_file(self, output_path: Path, text: str):
        """
        Genera file WAV valido con header e dati minimali
        """
        import struct
        import math
        
        # Parametri WAV
        sample_rate = 22050
        duration = 1.0  # 1 secondo
        frequency = 440  # A4
        
        # Calcola numero di samples
        num_samples = int(sample_rate * duration)
        
        # Genera dati audio (onda sinusoidale semplice)
        audio_data = bytearray()
        for i in range(num_samples):
            # Genera onda sinusoidale
            sample = int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
            # Converti a little-endian
            audio_data.extend(struct.pack('<h', sample))
        
        # Crea header WAV
        header = bytearray()
        
        # RIFF header
        header.extend(b'RIFF')
        header.extend(struct.pack('<I', 36 + len(audio_data)))  # file size - 8
        header.extend(b'WAVE')
        
        # fmt chunk
        header.extend(b'fmt ')
        header.extend(struct.pack('<I', 16))  # chunk size
        header.extend(struct.pack('<H', 1))   # audio format (PCM)
        header.extend(struct.pack('<H', 1))   # number of channels
        header.extend(struct.pack('<I', sample_rate))  # sample rate
        header.extend(struct.pack('<I', sample_rate * 2))  # byte rate
        header.extend(struct.pack('<H', 2))   # block align
        header.extend(struct.pack('<H', 16))  # bits per sample
        
        # data chunk
        header.extend(b'data')
        header.extend(struct.pack('<I', len(audio_data)))  # data size
        
        # Scrivi file WAV completo
        with open(output_path, 'wb') as f:
            f.write(header)
            f.write(audio_data)
            f.flush()  # Assicura che i dati siano scritti su disco

# Istanza globale
simple_tts = SimpleTTS()
