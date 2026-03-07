"""
EMOTION ADAPTER - Genesi Core v2
Modula il tono della risposta in base allo stato emotivo rilevato.
Lavora sulla struttura della risposta, non solo sulla coda.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def adapt_tone(response: str, user_mood: str, user_name: str = "", intensity: float = 0.3, needs: str = "") -> str:
    """
    Modula la risposta in base all'umore e al bisogno rilevato.
    Lavora sul tono complessivo, non aggiunge suffissi meccanici.
    """
    if not response:
        return response

    mood_lower = user_mood.lower() if user_mood else ""

    # Stato di forte vulnerabilità o urgenza — tono raccolto, niente entusiasmo
    if any(kw in mood_lower for kw in ["sad", "triste", "depressed", "depresso", "lonely", "solo", "desperate", "desperato"]):
        # Rimuovi esclamativi — non appropriati
        response = response.replace("!", ".")
        response = response.replace("!!", ".")
        # Evita emoji troppo vivaci
        response = re.sub(r'[🚀🎉🔥⚡💪🏆]', '', response)
        return response.strip()

    elif any(kw in mood_lower for kw in ["anxious", "ansioso", "stressed", "stressato", "worried", "preoccupato"]):
        # Tono calmo e rassicurante — rimuovi urgenza e punti esclamativi sparsi
        response = re.sub(r'(?<![A-Z])!', '.', response)
        response = re.sub(r'[🚀🔥⚡]', '', response)
        return response.strip()

    elif any(kw in mood_lower for kw in ["tired", "stanco", "exhausted", "esausto"]):
        # Tono conciso e pratico — taglia eventuali code lunghe
        sentences = re.split(r'(?<=[.!?])\s+', response.strip())
        if len(sentences) > 3:
            response = " ".join(sentences[:3])
        return response.strip()

    elif any(kw in mood_lower for kw in ["angry", "arrabbiato", "frustrated", "frustrato"]):
        # Tono pacato e diretto — nessun entusiasmo forzato
        response = re.sub(r'(?<![A-Z])!', '.', response)
        response = re.sub(r'[🎉🚀💪]', '', response)
        return response.strip()

    elif any(kw in mood_lower for kw in ["happy", "felice", "excited", "entusiasta", "great", "ottimo"]) and intensity > 0.5:
        # Tono energico — già gestito dal LLM, mantieni com'è
        return response

    # Default: restituisci invariata (il LLM ha già il tono giusto dal system prompt)
    return response


def format_for_needs(response: str, needs: str, user_name: str = "") -> str:
    """
    Adatta la struttura della risposta in base al bisogno rilevato.
    needs: conforto|soluzione|ascolto|sfogo|informazione|motivazione|condivisione
    """
    if not response or not needs:
        return response

    needs_lower = needs.lower()

    if needs_lower == "sfogo":
        # L'utente vuole solo sfogarsi: risposta breve, nessuna soluzione proposta
        sentences = re.split(r'(?<=[.!?])\s+', response.strip())
        # Mantieni solo le prime 2 frasi (ascolto, non consigli)
        if len(sentences) > 2:
            response = " ".join(sentences[:2])

    elif needs_lower == "ascolto":
        # Risposta empatica, poca lunghezza
        sentences = re.split(r'(?<=[.!?])\s+', response.strip())
        if len(sentences) > 3:
            response = " ".join(sentences[:3])

    elif needs_lower == "motivazione":
        # Risposta proattiva e diretta — mantieni lunghezza normale
        pass

    return response.strip()
