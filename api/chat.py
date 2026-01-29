from core.intent_engine import IntentEngine
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from datetime import datetime
from typing import Dict, List, Optional
import json

from core.state import CognitiveState
from core.response_generator import ResponseGenerator

from memory.episodic import store_event, get_recent_events, search_events
from memory.affective import compute_affect
from memory.salience import compute_salience

from core.relational_interpreter import RelationalInterpreter
from core.relational.accumulator import RelationalAccumulator

from core.tone import compute_tone

router = APIRouter()


class ChatRequest(BaseModel):
    user_id: str
    message: str


@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    print(f"[CHAT_ENDPOINT] incoming_message = '{request.message}'", flush=True)
    print(f"[CHAT_ENDPOINT] user_id = {request.user_id}", flush=True)
    
    # 1. Build cognitive state
    state = CognitiveState.build(request.user_id)

    # 2. Compute message salience and affect
    user_salience = compute_salience(
        event_type="user_message",
        content={"text": request.message},
        past_events=[e.to_dict() for e in state.recent_events]
    )

    user_affect = compute_affect(
        "user_message",
        {"text": request.message}
    )

    # 3. Store the user's message event
    user_event = store_event(
        user_id=request.user_id,
        type="user_message",
        content={"text": request.message},
        salience=user_salience,
        affect=user_affect
    )

    # 🔍 Interpretazione relazionale (FASE OSSERVATIVA)
    interpreter = RelationalInterpreter()
    relational_eval = interpreter.interpret(user_event.to_dict())

    accumulator = RelationalAccumulator()
    relational_state = accumulator.update(
        user_id=request.user_id,
        relational_eval=relational_eval
    )

    print("🧠 RELATIONAL EVAL:", relational_eval, flush=True)
    print("🧠 RELATIONAL STATE:", relational_state, flush=True)

    # 4. Get relevant context
    recent_memories = get_recent_events(request.user_id, limit=5)
    relevant_memories = search_events(request.user_id, request.message, limit=3)

    # 5. Compute conversation tone
    tone = compute_tone(state.recent_events)

    # 6. Generate response
    try:
        intent_engine = IntentEngine()

        intent = intent_engine.decide(
            user_message=request.message,
            user=state.user,
            cognitive_state=state,
            recent_memories=recent_memories,
            relevant_memories=relevant_memories,
            tone=tone
        )

        if not intent["should_respond"]:
            response_text = ""
        else:
            generator = ResponseGenerator()
            response_text = generator.generate_response(
                user_message=request.message,
                cognitive_state=state,
                recent_memories=recent_memories if intent["use_memory"] else [],
                relevant_memories=relevant_memories if intent["use_memory"] else [],
                tone=tone,
                intent=intent
            )

        # 7. Store system response
        system_affect = compute_affect(
            "system_response",
            {"text": response_text}
        )

        store_event(
            user_id=request.user_id,
            type="system_response",
            content={"text": response_text},
            salience=1.0,
            affect=system_affect
        )

        print(f"[CHAT_ENDPOINT] final_response = '{response_text}'", flush=True)
        
        return {
            "response": response_text,
            "state": {
                "user": state.user.to_dict(),
                "recent_events": [e.to_dict() for e in state.recent_events[-5:]],
                "context": state.context
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating response: {str(e)}"
        )
