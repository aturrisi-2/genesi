"""SIMPLE CHAT HANDLER - Genesi Cognitive System v2
Proactor orchestrator centrale - intent classification + routing.
Identity filtering handled internally by evolution_engine.
"""

from typing import Optional
from core.intent_classifier import intent_classifier
from core.proactor import proactor
from core.user_manager import user_manager
from core.chat_memory import chat_memory
from core.log import log
from core.fallback_engine import fallback_engine

async def simple_chat_handler(user_id: str, message: str, conversation_id: str = None) -> str:
    """
    Chat handler — Proactor orchestrator centrale.
    Identity filtering avviene dentro evolution_engine (no doppio filtro).
    Returns: response_text (string only)
    """
    try:
        # Validazione user_id
        if not user_id:
            raise ValueError("simple_chat_handler received empty user_id")
        
        if len(user_id) > 50:
            raise ValueError("Invalid user_id: too long")
        
        if " " in user_id:
            raise ValueError("Invalid user_id: contains spaces")
        
        log("CHAT_INPUT", message=message[:100], user_id=user_id)

        # 2. Proactor orchestration (brain update + evolution engine)
        # Pass intent=None to allow Proactor to use its new multi-intent classification
        response = await proactor.handle(
            user_id=user_id,
            message=message,
            intent=None, 
            conversation_id=conversation_id
        )
        
        # Ensure we return only the response string, not the tuple
        if isinstance(response, tuple):
            response = response[0]

        # 3. Chat memory logging (volatile, per UI history)
        if not user_manager.get_user(user_id):
            user_manager.create_user(user_id)
        user_manager.increment_messages(user_id)
        chat_memory.add_message(user_id, message, response, "multi")

        log("CHAT_OUTPUT", response=response[:100], intent="multi", user_id=user_id)
        return response

    except Exception as e:
        log("CHAT_ERROR", error=str(e), user_id=user_id)
        msg_error = "Mi dispiace, ho avuto un problema. Riprova più tardi."
        import asyncio
        asyncio.create_task(fallback_engine.log_event(
            user_id=user_id,
            message=message,
            fallback_type="simple_chat_fatal",
            response_given=msg_error,
            reason=str(e)
        ))
        return msg_error

