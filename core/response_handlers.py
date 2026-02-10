"""
RESPONSE HANDLERS - Genesi Core v2
1 intent → 1 funzione
Ogni intent ha la sua funzione dedicata
"""

from datetime import datetime
from typing import Dict, Optional
from core.local_llm import LocalLLM
from core.log import log

# Istanza globale
local_llm = LocalLLM()

async def handle_greeting(message: str) -> str:
    """Handler per saluti"""
    responses = [
        "Ciao! Come posso aiutarti?",
        "Salve! Sono qui per te.",
        "Ciao! Dimmi pure.",
    ]
    import random
    return random.choice(responses)

async def handle_how_are_you(message: str) -> str:
    """Handler per 'come stai'"""
    responses = [
        "Sto bene, grazie! E tu?",
        "Tutto ok, grazie per aver chiesto!",
        "Bene, grazie! Come va a te?",
    ]
    import random
    return random.choice(responses)

async def handle_identity(message: str) -> str:
    """Handler per identità"""
    return "Sono Genesi, la tua assistente personale. Sono qui per aiutarti."

async def handle_time(message: str) -> str:
    """Handler per ora"""
    now = datetime.now()
    return f"Sono le {now.strftime('%H:%M')}."

async def handle_date(message: str) -> str:
    """Handler per data"""
    now = datetime.now()
    mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", 
            "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    return f"Oggi è {now.day} {mesi[now.month-1]} {now.year}."

async def handle_weather(message: str) -> str:
    """Handler per meteo - semplice"""
    return "Al momento non posso controllare il meteo. Scusa!"

async def handle_help(message: str) -> str:
    """Handler per aiuto"""
    return "Posso aiutarti a conversare, rispondere domande semplici e darti l'ora e la data."

async def handle_goodbye(message: str) -> str:
    """Handler per arrivederci"""
    responses = [
        "A dopo! Buona giornata!",
        "Arrivederci!",
        "Ci vediamo presto!",
    ]
    import random
    return random.choice(responses)

async def handle_chat_free(message: str) -> str:
    """
    Handler per chat libera - 1 intent → 1 funzione
    Chiamata diretta al modello senza orchestrazione
    """
    try:
        # Prompt semplice per chat libera
        prompt = f"""Sei Genesi. Parli in italiano.

Rispondi a questo messaggio in modo naturale e breve:
{message}

Rispondi in modo diretto, senza presentazioni non richieste."""
        
        response = local_llm.generate(prompt)
        return response
        
    except Exception as e:
        log("CHAT_FREE_ERROR", error=str(e))
        return "Mi dispiace, ho avuto un problema. Riprova più tardi."

# Mapping intent → handler
INTENT_HANDLERS = {
    "greeting": handle_greeting,
    "how_are_you": handle_how_are_you,
    "identity": handle_identity,
    "time": handle_time,
    "date": handle_date,
    "weather": handle_weather,
    "help": handle_help,
    "goodbye": handle_goodbye,
    "chat_free": handle_chat_free,
}

async def handle_by_intent(intent: str, message: str) -> str:
    """
    Handler universale - 1 intent → 1 funzione
    
    Args:
        intent: Intent classificato
        message: Messaggio originale
        
    Returns:
        Risposta dal handler specifico
    """
    handler = INTENT_HANDLERS.get(intent, handle_chat_free)
    return await handler(message)
