"""
SIMPLE CHAT HANDLER - Genesi Core v2
Proactor orchestrator centrale - intent classification + routing
"""

from typing import Dict, Optional
from core.intent_classifier import intent_classifier
from core.proactor import proactor
from core.identity_filter import filter_response_identity
from core.user_manager import user_manager
from core.chat_memory import chat_memory
from core.log import log

async def simple_chat_handler(message: str, user_id: Optional[str] = None) -> str:
    """
    Chat handler - Proactor orchestrator centrale
    
    Args:
        message: Messaggio utente
        user_id: ID utente opzionale
        
    Returns:
        Risposta orchestrata da Proactor
    """
    try:
        # Log input
        log("CHAT_INPUT", message=message[:100], user_id=user_id or "anonymous")
        
        # 1️⃣ Intent classification
        intent = intent_classifier.classify(message)
        
        # 2️⃣ Proactor orchestration
        user_data = user_manager.get_user(user_id) if user_id else {}
        response = await proactor.handle(
            message=message,
            user=user_data,
            intent=intent
        )
        
        # 3️⃣ Identity filter POST-PROACTOR
        filtered_response = await filter_response_identity(
            user_id=user_id or "anonymous",
            user_profile=user_data,
            message=message,
            response=response
        )
        
        # Salva in memoria se user_id presente
        if user_id:
            # Crea utente se non esiste
            if not user_manager.get_user(user_id):
                user_manager.create_user(user_id)
            
            # Incrementa contatore messaggi
            user_manager.increment_messages(user_id)
            
            # Salva messaggio nella chat memory
            chat_memory.add_message(user_id, message, filtered_response, intent)
        
        # Log output
        log("CHAT_OUTPUT", response=filtered_response[:100], intent=intent, user_id=user_id or "anonymous")
        
        return filtered_response
        
    except Exception as e:
        log("CHAT_ERROR", error=str(e), user_id=user_id or "anonymous")
        return "Mi dispiace, ho avuto un problema. Riprova più tardi."
