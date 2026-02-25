"""
EMOTION ADAPTER - Genesi Core
Varia il tono della risposta LLM in base allo stato emotivo rilevato.
"""

import re
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

EMOTION_TONES = {
    "stanco": "empatico-calmo",
    "felice": "entusiasta-amichevole", 
    "urgente": "proattivo-preciso",
    "neutro": "naturale-ironico",
    "triste": "empatico-profondo",
    "arrabbiato": "calmo-riflessivo"
}

def adapt_tone(response: str, user_mood: str, user_name: str = "") -> str:
    """
    Varia la risposta per aumentarne la naturalezza in base all'umore dell'utente.
    """
    if not response:
        return response
        
    mood_lower = user_mood.lower()
    
    if any(kw in mood_lower for kw in ["stanco", "esausto", "distrutto", "triste", "giù"]):
        # Tono più calmo, meno esclamativo
        adapted = re.sub(r"!", "...", response)
        if "stanco" in mood_lower or "esausto" in mood_lower:
            suffix = " Rilassati un po' 😌"
        else:
            suffix = " Ti sono vicino 🤍"
        
        # Evita duplicazione se già presente
        if suffix.strip() not in adapted:
            adapted += suffix
        return adapted
        
    elif any(kw in mood_lower for kw in ["felice", "contento", "entusiasta", "grande", "ottimo"]):
        # Tono più energico
        suffix = f" Grande {user_name}! 🚀" if user_name else " Grande! 🚀"
        if suffix.strip() not in response:
            return response.rstrip(".! ") + suffix
        return response
        
    elif "urgente" in mood_lower or "fretta" in mood_lower:
        # Tono asciutto e proattivo
        return response + " Dimmi se serve altro subito. ⚡"
        
    return response
