"""
TTS SANITIZER - Genesi Core
Sanitizza testo per sintesi vocale (TTS).
Rimuove emoji e simboli che non vengono letti correttamente.
"""

import re
import logging

logger = logging.getLogger(__name__)

def sanitize_for_tts(text: str) -> str:
    """
    Sanitizza testo per TTS, rimuovendo emoji e sostituendo simboli.
    
    Args:
        text: Testo originale da sanitizzare
        
    Returns:
        Testo pulito per TTS
    """
    if not text or not isinstance(text, str):
        return text
    
    sanitized = text
    
    # 1. Rimuovi tutte le emoji (regex unicode)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )
    sanitized = emoji_pattern.sub('', sanitized)
    
    # 2. Sostituisci simboli e abbreviazioni
    replacements = {
        "km/h": "chilometri orari",
        "kmh": "chilometri orari",
        "km/h": "chilometri orari",
        "°C": "gradi Celsius",
        "°c": "gradi Celsius",
        "°": "gradi",
        "%": "percento",
        "→": "",
        "←": "",
        "→": "",
        "←": "",
        "↔": "",
        "⇒": "",
        "⇐": "",
        "⇔": "",
        "•": "",
        "◆": "",
        "◇": "",
        "▪": "",
        "▫": "",
        "○": "",
        "●": "",
        "□": "",
        "■": "",
        "△": "",
        "▽": "",
        "☆": "",
        "★": "",
        "♦": "",
        "♣": "",
        "♠": "",
        "♥": "",
    }
    
    for old, new in replacements.items():
        sanitized = sanitized.replace(old, new)
    
    # 3. Rimuovi spazi multipli
    sanitized = re.sub(r'\s+', ' ', sanitized)
    
    # 4. Rimuovi spazi all'inizio e alla fine
    sanitized = sanitized.strip()
    
    return sanitized


def strip_emojis(text: str) -> str:
    """
    Rimuove solo le emoji dal testo, mantenendo altri simboli.
    Utile per salvare testo pulito nei reminder.
    
    Args:
        text: Testo da cui rimuovere le emoji
        
    Returns:
        Testo senza emoji
    """
    if not text or not isinstance(text, str):
        return text
    
    # Rimuovi tutte le emoji (regex unicode)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )
    
    return emoji_pattern.sub('', text)
