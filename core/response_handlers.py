"""
RESPONSE HANDLERS - Genesi Core v2
Architettura separata: Chat libera (Qwen) vs Tecnica (GPT)
1 intent → 1 funzione con Proactor orchestratore
"""

from datetime import datetime
from typing import Dict, Optional
from core.proactor import proactor
from core.log import log
from core.fallback_engine import fallback_engine
import asyncio

async def handle_greeting(message: str) -> str:
    """Handler per saluti - Qwen2.5-7B-Instruct"""
    response = proactor.generate_response("greeting", message)
    if not response:
        asyncio.create_task(fallback_engine.log_event("system", message, "hardcoded_fallback", "Ciao! Come posso aiutarti?", "Handler: greeting"))
    return response or "Ciao! Come posso aiutarti?"

async def handle_how_are_you(message: str) -> str:
    """Handler per 'come stai' - Qwen2.5-7B-Instruct"""
    response = proactor.generate_response("how_are_you", message)
    return response or "Sto bene, grazie! E tu?"

async def handle_identity(message: str) -> str:
    """Handler per identità - Qwen2.5-7B-Instruct"""
    response = proactor.generate_response("identity", message)
    return response or "Sono Genesi, la tua assistente personale."

async def handle_time(message: str) -> str:
    """Handler per ora - non usa LLM"""
    now = datetime.now()
    return f"Sono le {now.strftime('%H:%M')}."

async def handle_date(message: str) -> str:
    """Handler per data - non usa LLM"""
    now = datetime.now()
    mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", 
            "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    return f"Oggi è {now.day} {mesi[now.month-1]} {now.year}."

async def handle_weather(message: str) -> str:
    """Handler per meteo - non usa LLM"""
    return "Al momento non posso controllare il meteo. Scusa!"

async def handle_help(message: str) -> str:
    """Handler per aiuto - Qwen2.5-7B-Instruct"""
    response = proactor.generate_response("help", message)
    return response or "Posso aiutarti a conversare e rispondere domande semplici."

async def handle_goodbye(message: str) -> str:
    """Handler per arrivederci - Qwen2.5-7B-Instruct"""
    response = proactor.generate_response("goodbye", message)
    return response or "A dopo! Buona giornata!"

async def handle_chat_free(message: str) -> str:
    """
    Handler per chat libera - Qwen2.5-7B-Instruct
    Chat libera, presenza umana, relazione
    """
    response = proactor.generate_response("chat_free", message)
    if not response:
        asyncio.create_task(fallback_engine.log_event("user_id_needed", message, "hardcoded_fallback", "Mi dispiace, ho avuto un problema. Riprova più tardi.", "Handler: chat_free"))
    return response or "Mi dispiace, ho avuto un problema. Riprova più tardi."

async def handle_technical(message: str) -> str:
    """
    Handler per tecnica - GPT
    Spiegazioni, debugging, architettura, ragionamento
    """
    response = proactor.generate_response("tecnica", message)
    return response or "Non posso gestire richieste tecniche al momento."

async def handle_debug(message: str) -> str:
    """
    Handler per debug - GPT
    """
    response = proactor.generate_response("debug", message)
    return response or "Non posso fare debug al momento."

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
    "tecnica": handle_technical,
    "debug": handle_debug,
}

async def handle_by_intent(intent: str, message: str) -> str:
    """
    Handler universale con Proactor - 1 intent → 1 funzione
    
    Args:
        intent: Intent classificato
        message: Messaggio originale
        
    Returns:
        Risposta dal handler specifico
    """
    handler = INTENT_HANDLERS.get(intent, handle_chat_free)
    return await handler(message)
