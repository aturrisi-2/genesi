from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from core.state import CognitiveState
from memory.episodic import store_event
from memory.salience import compute_salience

router = APIRouter(prefix="/chat")

class ChatRequest(BaseModel):
    user_id: str
    message: str

@router.post("")
async def chat_endpoint(request: ChatRequest):
    # 1. Costruisci lo stato cognitivo
    state = CognitiveState.build(request.user_id)
    
    # 2. Salva l'evento del messaggio utente
    user_salience = compute_salience(
        event_type="user_message",
        content={"text": request.message},
        past_events=[e.to_dict() for e in state.recent_events]
    )
    user_event = store_event(
        user_id=request.user_id,
        type="user_message",
        content={"text": request.message},
        salience=user_salience
    )
    
    # 3. Genera risposta echo
    response_text = f"Hai detto: {request.message}"
    
    # 4. Salva l'evento di risposta del sistema
    system_salience = compute_salience(
        event_type="system_response",
        content={"text": response_text},
        past_events=[e.to_dict() for e in state.recent_events]
    )
    system_event = store_event(
        user_id=request.user_id,
        type="system_response",
        content={"text": response_text},
        salience=system_salience
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