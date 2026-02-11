"""
SIMPLE CHAT HANDLER - Genesi Core v2
Relational Engine v1 integration - 1 intent → 1 funzione
"""

from typing import Dict, Optional
from core.relational_engine import generate_relational_response
from core.user_manager import user_manager
from core.chat_memory import chat_memory
from core.log import log

async def simple_chat_handler(message: str, user_id: Optional[str] = None) -> str:
    """
    Chat handler - Relational Engine v1
    
    Args:
        message: Messaggio utente
        user_id: ID utente opzionale
        
    Returns:
        Risposta evolutiva dal Relational Engine
    """
    try:
        # Log input
        log("CHAT_INPUT", message=message[:100], user_id=user_id or "anonymous")
        
        # Relational Engine v1 - generazione risposta evolutiva
        user_data = user_manager.get_user(user_id) if user_id else {}
        response = await generate_relational_response(
            user_id=user_id or "anonymous",
            user_profile=user_data,
            message=message
        )
        
        # Salva in memoria se user_id presente
        if user_id:
            # Crea utente se non esiste
            if not user_manager.get_user(user_id):
                user_manager.create_user(user_id)
            
            # Incrementa contatore messaggi
            user_manager.increment_messages(user_id)
            
            # Salva messaggio nella chat memory
            chat_memory.add_message(user_id, message, response, "relational")
        
        # Log output
        log("CHAT_OUTPUT", response=response[:100], intent="relational", user_id=user_id or "anonymous")
        
        return response
        
    except Exception as e:
        log("CHAT_ERROR", error=str(e), user_id=user_id or "anonymous")
        return "Mi dispiace, ho avuto un problema. Riprova più tardi."
