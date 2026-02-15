"""
TTS SANITIZER - Genesi Core
Sanitizza testo per sintesi vocale (TTS).
Rimuove emoji e simboli che non vengono letti correttamente.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def normalize_for_tts(text: str, intent: Optional[str] = None) -> str:
    """
    Normalizza testo per TTS in modo intelligente basato sul contesto.
    
    Args:
        text: Testo originale da normalizzare
        intent: Intent opzionale per normalizzazione context-aware
        
    Returns:
        Testo normalizzato per TTS
    """
    if not text or not isinstance(text, str):
        return text
    
    normalized = text
    
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
    normalized = emoji_pattern.sub('', normalized)
    
    # 2. Espandi mesi abbreviati
    normalized = _expand_month_abbreviations(normalized)
    
    # 3. Espandi titoli con punto
    normalized = _expand_titles(normalized)
    
    # 4. Espandi sigle nazioni isolate
    normalized = _expand_country_acronyms(normalized)
    
    # 5. Converti unità di misura
    normalized = _convert_units(normalized)
    
    # 6. Gestisci sigle (altre sigle non nazioni)
    normalized = _expand_acronyms(normalized)
    
    # 7. Cleanup specifico per intent
    if intent == "weather":
        normalized = _weather_cleanup(normalized)
    elif intent == "news":
        normalized = _news_cleanup(normalized)
    
    # 8. Rimuovi simboli problematici
    symbol_replacements = {
        "→": "",
        "←": "",
        "↔": "",
        "⇒": "",
        "⇐": "",
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
    
    for old, new in symbol_replacements.items():
        normalized = normalized.replace(old, new)
    
    # 9. Rimuovi spazi multipli
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # 10. Rimuovi spazi all'inizio e alla fine
    normalized = normalized.strip()
    
    return normalized


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


def _convert_units(text: str) -> str:
    """Converte unità di misura in linguaggio parlato."""
    replacements = {
        # Temperature
        r'°C\b': 'gradi Celsius',
        r'°C': 'gradi Celsius',
        r'°c': 'gradi Celsius',
        r'°F\b': 'gradi Fahrenheit',
        r'°F': 'gradi Fahrenheit',
        r'°f': 'gradi Fahrenheit',
        r'°': 'gradi',
        
        # Velocità
        r'\bkm/h\b': 'chilometri orari',
        r'\bkmh\b': 'chilometri orari',
        r'\bm/s\b': 'metri al secondo',
        r'\bms\b': 'metri al secondo',
        
        # Pressione
        r'\bPa\b': 'pascal',
        r'\bhPa\b': 'ettopascal',
        r'\bkPa\b': 'chilopascal',
        
        # Lunghezza
        r'\bmm\b': 'millimetri',
        r'\bcm\b': 'centimetri',
        r'\bkm\b': 'chilometri',
        r'\bm\b': 'metri',
        
        # Percentuale
        r'\b%\b': 'percento',
        
        # Altre unità comuni
        r'\bkg\b': 'chilogrammi',
        r'\bg\b': 'grammi',
        r'\bl\b': 'litri',
        r'\bml\b': 'millilitri',
    }
    
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)
    
    return text


def _expand_acronyms(text: str) -> str:
    """Espande sigle comuni."""
    # Sigle di paesi (escluse quelle gestite da _expand_country_acronyms)
    country_acronyms = {
        r'\bUSA\b': 'Stati Uniti',
        r'\bEU\b': 'Unione Europea',
        r'\bUK\b': 'Regno Unito',
        r'\bGB\b': 'Regno Unito',
        r'\bFR\b': 'Francia',
        r'\bDE\b': 'Germania',
        r'\bES\b': 'Spagna',
    }
    
    # Altre sigle comuni (escluse IT, US, UE già gestite)
    other_acronyms = {
        r'\bDNA\b': 'DNA',
        r'\bRNA\b': 'RNA',
        r'\bCEO\b': 'CEO',
        r'\bCFO\b': 'CFO',
        r'\bCTO\b': 'CTO',
        # r'\bIT\b': 'Information Technology',  # Rimosso per non confliggere con IT=Italia
        r'\bAI\b': 'Intelligenza Artificiale',
        r'\bML\b': 'Machine Learning',
        r'\bIoT\b': 'Internet of Things',
    }
    
    # Prima espandi le sigle di paesi (escluse IT, US, UE già gestite)
    for pattern, replacement in country_acronyms.items():
        text = re.sub(pattern, replacement, text)
    
    # Poi espandi le altre sigle (solo se non sono già state espanse)
    for pattern, replacement in other_acronyms.items():
        text = re.sub(pattern, replacement, text)
    
    return text


def _weather_cleanup(text: str) -> str:
    """Pulizia specifica per testo meteo."""
    # Rimuovi eventuali prefissi GPT-style
    prefixes_to_remove = [
        r'^Ecco il meteo:\s*',
        r'^Ecco le previsioni:\s*',
        r'^Meteo:\s*',
        r'^Previsioni:\s*',
        r'^A\s+(?:Roma|Milano|Firenze|Bologna|Torino|Napoli|Palermo|Genova|Bari|Catania):\s*',
    ]
    
    for prefix in prefixes_to_remove:
        text = re.sub(prefix, '', text)
    
    # Assicurati che il formato sia coerente
    # Se non inizia con "A {city}:", non modificare
    if not re.match(r'^A\s+\w+:', text):
        return text
    
    return text


def _news_cleanup(text: str) -> str:
    """Pulizia specifica per testo news."""
    # Rimuovi URL
    text = re.sub(r'https?://[^\s]+', '', text)
    
    # Rimuovi eventuali simboli strani
    text = re.sub(r'[^\w\s\.,;:!?\'"-àèéìòù]', '', text)
    
    # Rimuovi prefissi comuni
    prefixes_to_remove = [
        r'^Ecco le ultime notizie:\s*',
        r'^Notizie:\s*',
        r'^Ultime notizie:\s*',
        r'^News:\s*',
    ]
    
    for prefix in prefixes_to_remove:
        text = re.sub(prefix, '', text)
    
    return text


def _expand_month_abbreviations(text: str) -> str:
    """Espande abbreviazioni dei mesi."""
    MONTH_MAP = {
        "GEN": "gennaio",
        "FEB": "febbraio",
        "FEBB": "febbraio",
        "MAR": "marzo",
        "APR": "aprile",
        "MAG": "maggio",
        "GIU": "giugno",
        "LUG": "luglio",
        "AGO": "agosto",
        "SET": "settembre",
        "OTT": "ottobre",
        "NOV": "novembre",
        "DIC": "dicembre",
    }
    
    # Sostituisci solo se parola intera
    for abbr, full in MONTH_MAP.items():
        text = re.sub(rf"\b{abbr}\b", full, text, flags=re.IGNORECASE)
    
    return text


def _expand_titles(text: str) -> str:
    """Espande titoli con punto."""
    TITLE_MAP = {
        "Sig.": "Signor",
        "Sig.ra": "Signora",
        "Dott.": "Dottor",
        "Ing.": "Ingegnere",
        "Prof.": "Professore",
        "Avv.": "Avvocato",
    }
    
    # Sostituisci in modo semplice
    for abbr, full in TITLE_MAP.items():
        text = text.replace(abbr, full)
    
    return text


def _expand_country_acronyms(text: str) -> str:
    """Espande sigle nazioni isolate."""
    COUNTRY_MAP = {
        "IT": "Italia",
        "US": "Stati Uniti",
        "UE": "Unione Europea",
    }
    
    # Sostituisci SOLO se parola isolata, NON seguita da numero, NON preceduta o seguita da trattino
    for abbr, full in COUNTRY_MAP.items():
        # Regex più precisa: parola intera non seguita da - o numero
        text = re.sub(rf"\b{abbr}\b(?!(?:-|\d))", full, text)
    
    return text
