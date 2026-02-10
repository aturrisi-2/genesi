"""
SIMPLE CHAT HANDLER - Genesi Core v2
1 intent → 1 funzione
Nessun orchestrazione, nessun fallback, nessun post-processing
Storage in-memory per validazione comportamento
"""

from typing import Dict, Optional
from core.intent_classifier import intent_classifier
from core.response_handlers import handle_by_intent
from core.user_manager import user_manager
from core.chat_memory import chat_memory
from core.log import log

async def simple_chat_handler(message: str, user_id: Optional[str] = None) -> str:
    """
    Chat handler - 1 intent → 1 funzione
    
    Args:
        message: Messaggio utente
        user_id: ID utente opzionale
        
    Returns:
        Risposta diretta dal handler specifico
    """
    try:
        # Log input
        log("CHAT_INPUT", message=message[:100], user_id=user_id or "anonymous")
        
        # 1 intent → 1 funzione: classificazione + handler diretto
        intent = intent_classifier.classify(message)
        response = await handle_by_intent(intent, message)
        
        # Salva in memoria se user_id presente
        if user_id:
            # Crea utente se non esiste
            if not user_manager.get_user(user_id):
                user_manager.create_user(user_id)
            
            # Incrementa contatore messaggi
            user_manager.increment_messages(user_id)
            
            # Salva messaggio nella chat memory
            chat_memory.add_message(user_id, message, response, intent)
        
        # Log output
        log("CHAT_OUTPUT", response=response[:100], intent=intent, user_id=user_id or "anonymous")
        
        return response
        
    except Exception as e:
        log("CHAT_ERROR", error=str(e), user_id=user_id or "anonymous")
        return "Mi dispiace, ho avuto un problema. Riprova più tardi."
