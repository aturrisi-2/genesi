"""
CHAT API - Genesi Core v2
1 intent → 1 funzione
Nessun orchestrazione, nessun fallback, nessun post-processing
Storage in-memory per validazione comportamento
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
from core.simple_chat import simple_chat_handler
from core.user_manager import user_manager
from core.chat_memory import chat_memory
from core.log import log
from core.cognitive_memory_engine import CognitiveMemoryEngine

router = APIRouter(prefix="/chat")

class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    status: str
    intent: Optional[str] = None
    user_id: Optional[str] = None

@router.post("/", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        if not request.user_id:
            raise ValueError("Chat endpoint received empty user_id")

        log("API_CHAT", message=request.message[:100], user_id=request.user_id)

        # Cognitive Memory Evaluation
        cognitive_engine = CognitiveMemoryEngine()
        decision = cognitive_engine.evaluate_event(request.user_id, request.message, {})

        if decision['persist']:
            # Update memory via cognitive engine
            log("COGNITIVE_DECISION", user_id=request.user_id, persist=True, type=decision['memory_type'], confidence=decision['confidence'])
        else:
            log("COGNITIVE_DECISION", user_id=request.user_id, persist=False, reason="low_relevance")

        response = await simple_chat_handler(request.message, request.user_id)

        return ChatResponse(
            response=response,
            status="ok",
            user_id=request.user_id
        )

    except Exception as e:
        log("API_CHAT_ERROR", error=str(e), user_id=request.user_id or "unknown")
        raise HTTPException(status_code=500, detail="Chat error")

@router.get("/user/{user_id}/info")
async def get_user_info(user_id: str):
    """
    Ottieni info utente - 1 intent → 1 funzione
    """
    try:
        user_data = user_manager.get_user(user_id)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Aggiungi statistiche chat
        message_count = chat_memory.get_message_count(user_id)
        intents_summary = chat_memory.get_intents_summary(user_id)
        
        return {
            "user": user_data,
            "message_count": message_count,
            "intents_summary": intents_summary
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log("USER_INFO_ERROR", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail="User info error")

@router.get("/user/{user_id}/messages")
async def get_user_messages(user_id: str, limit: Optional[int] = 10):
    """
    Ottieni messaggi utente - 1 intent → 1 funzione
    """
    try:
        messages = chat_memory.get_messages(user_id, limit)
        return {
            "user_id": user_id,
            "messages": messages,
            "count": len(messages)
        }
        
    except Exception as e:
        log("USER_MESSAGES_ERROR", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail="User messages error")

@router.delete("/user/{user_id}/messages")
async def clear_user_messages(user_id: str):
    """
    Pulisci messaggi utente - 1 intent → 1 funzione
    """
    try:
        success = chat_memory.clear_messages(user_id)
        return {
            "user_id": user_id,
            "cleared": success
        }
        
    except Exception as e:
        log("USER_CLEAR_ERROR", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail="User clear error")

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": "v2", "storage": "in-memory"}
