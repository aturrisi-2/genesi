"""
SIMPLE CHAT HANDLER - Genesi Core v2
1 intent → 1 funzione
Nessun orchestrazione, nessun fallback, nessun post-processing
"""

from typing import Dict, Optional
from core.intent_classifier import intent_classifier
from core.response_handlers import handle_by_intent
from core.log import log

async def simple_chat_handler(message: str) -> str:
    """
    Chat handler - 1 intent → 1 funzione
    
    Args:
        message: Messaggio utente
        
    Returns:
        Risposta diretta dal handler specifico
    """
    try:
        # Log input
        log("CHAT_INPUT", message=message[:100])
        
        # 1 intent → 1 funzione: classificazione + handler diretto
        intent = intent_classifier.classify(message)
        response = await handle_by_intent(intent, message)
        
        # Log output
        log("CHAT_OUTPUT", response=response[:100], intent=intent)
        
        return response
        
    except Exception as e:
        log("CHAT_ERROR", error=str(e))
        return "Mi dispiace, ho avuto un problema. Riprova più tardi."
