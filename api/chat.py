from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from core.state import CognitiveState
from core.tone import compute_tone
from memory.episodic import store_event
from memory.salience import compute_salience
from memory.affective import compute_affect

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
    user_affect = compute_affect("user_message", {"text": request.message})
    user_event = store_event(
        user_id=request.user_id,
        type="user_message",
        content={"text": request.message},
        salience=user_salience,
        affect=user_affect
    )
    
    # 3. Calcola il tono basato sugli eventi recenti
    tone = compute_tone(state.recent_events)
    
    # 4. Genera risposta basata sul tono
    base_response = f"Hai detto: {request.message}"
    
    if tone.directness > 0.7:
        response_text = base_response
    else:
        response_text = base_response + ". Capisco cosa intendi." if "grazie" in request.message.lower() else base_response
    
    if tone.empathy > 0.7 and tone.directness <= 0.7:
        if "grazie" in request.message.lower():
            response_text += " È stato un piacere aiutarti!"
        elif any(word in request.message.lower() for word in ["triste", "preoccupato", "preoccupata"]):
            response_text = "Mi dispiace sentire che non ti senti bene. " + response_text
    
    if tone.verbosity < 0.4:
        response_text = response_text.replace("Hai detto: ", "")
    
    # 5. Salva l'evento di risposta del sistema
    system_salience = compute_salience(
        event_type="system_response",
        content={"text": response_text},
        past_events=[e.to_dict() for e in state.recent_events]
    )
    system_affect = compute_affect("system_response", {"text": response_text})
    system_event = store_event(
        user_id=request.user_id,
        type="system_response",
        content={"text": response_text},
        salience=system_salience,
        affect=system_affect
    )
    
    # 6. Restituisci la risposta con il tono
    return {
        "response": response_text,
        "tone": tone.to_dict(),
        "state": {
            "user": state.user.to_dict(),
            "recent_events": [e.to_dict() for e in state.recent_events],
            "context": state.context
        }
    }