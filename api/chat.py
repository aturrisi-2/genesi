from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from core.state import CognitiveState
from memory.episodic import store_event

router = APIRouter(prefix="/chat")

class ChatRequest(BaseModel):
    user_id: str
    message: str

@router.post("")
async def chat_endpoint(request: ChatRequest):
    # 1. Costruisci lo stato cognitivo
    state = CognitiveState.build(request.user_id)
    
    # 2. Salva l'evento del messaggio utente
    user_event = store_event(
        user_id=request.user_id,
        type="user_message",
        content={"text": request.message},
        salience=0.5
    )
    
    # 3. Genera risposta echo
    response_text = f"Hai detto: {request.message}"
    
    # 4. Salva l'evento di risposta del sistema
    system_event = store_event(
        user_id=request.user_id,
        type="system_response",
        content={"text": response_text},
        salience=0.5
    )
    
    # 5. Restituisci la risposta
    return {
        "response": response_text,
        "state": {
            "user": state.user.to_dict(),
            "recent_events": [e.to_dict() for e in state.recent_events],
            "context": state.context
        }
    }