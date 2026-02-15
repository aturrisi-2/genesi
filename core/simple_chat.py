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


async def simple_chat_handler(message: str, user_id: Optional[str] = None) -> tuple[str, str]:
    """
    Chat handler — Proactor orchestrator centrale.
    Identity filtering avviene dentro evolution_engine (no doppio filtro).
    Returns: (response_text, response_source)
    """
    try:
        log("CHAT_INPUT", message=message[:100], user_id=user_id or "anonymous")

        # 1. Intent classification
        intent = intent_classifier.classify(message)

        # 2. Proactor orchestration (brain update + evolution engine)
        if not user_id:
            raise ValueError("simple_chat_handler received empty user_id")

        response, source = await proactor.handle(
            message=message,
            intent=intent,
            user_id=user_id
        )

        # 3. Chat memory logging (volatile, per UI history)
        if user_id:
            if not user_manager.get_user(user_id):
                user_manager.create_user(user_id)
            user_manager.increment_messages(user_id)
            chat_memory.add_message(user_id, message, response, intent)

        log("CHAT_OUTPUT", response=response[:100], intent=intent, user_id=user_id or "anonymous")
        return response, source

    except Exception as e:
        log("CHAT_ERROR", error=str(e), user_id=user_id or "anonymous")
        return "Mi dispiace, ho avuto un problema. Riprova più tardi.", "error"
