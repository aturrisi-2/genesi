from core.intent_engine import IntentEngine
from fastapi import APIRouter, HTTPException, status, Request
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
async def chat_endpoint(request: ChatRequest, http_request: Request):
    print(f"[CHAT_ENDPOINT] incoming_message = '{request.message}'", flush=True)
    print(f"[CHAT_ENDPOINT] user_id = {request.user_id}", flush=True)
    
    # 🔍 DIAGNOSI MEMORIA: check per frasi dichiarative
    is_declarative = any(keyword in request.message.lower() for keyword in ["memorizza", "ricorda", "salva", "ricordati", "tieni a mente"])
    print(f"[CHAT_ENDPOINT] is_declarative = {is_declarative}", flush=True)
    
    # ===============================
    # DOCUMENT CONTEXT TEMPORANEO
    # ===============================
    document_context = None
    force_document_focus = False
    
    # Check per document context attivo (in session state)
    if hasattr(http_request, 'state') and hasattr(http_request.state, 'active_document'):
        active_doc = http_request.state.active_document
        if active_doc and active_doc.get('user_id') == request.user_id:
            # Check per domande generiche sul documento
            vague_questions = ["cosa contiene", "che dice", "riassumi", "spiegami questo", "di cosa parla", "cosa c'è scritto"]
            is_vague_question = any(q in request.message.lower() for q in vague_questions)
            
            if is_vague_question:
                document_context = active_doc.get('content', '')
                force_document_focus = True
                print(f"[CHAT_ENDPOINT] active_document_detected = True", flush=True)
                print(f"[CHAT_ENDPOINT] document_context_used = True", flush=True)
                
                # Rimuovi context dopo uso (one-shot)
                delattr(http_request.state, 'active_document')
                print(f"[CHAT_ENDPOINT] document_context_cleared = True", flush=True)
    
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

        # Se c'è document context, forza focus su documento
        if force_document_focus:
            # Sovrascrivi temporaneamente le memorie con document context
            document_memories = [{
                "content": document_context,
                "type": "document_context",
                "timestamp": datetime.now().isoformat()
            }]
            
            intent = intent_engine.decide(
                user_message=request.message,
                user=state.user,
                cognitive_state=state,
                recent_memories=[],  # Disabilita memoria personale per questa risposta
                relevant_memories=document_memories,
                tone=tone
            )
            
            # Forza focus su documento
            intent["focus"] = "documento"
            print(f"[CHAT_ENDPOINT] document_focus_forced = True", flush=True)
        else:
            intent = intent_engine.decide(
                user_message=request.message,
                user=state.user,
                cognitive_state=state,
                recent_memories=recent_memories,
                relevant_memories=relevant_memories,
                tone=tone
            )

        print(f"[CHAT_ENDPOINT] intent_decided = {intent}", flush=True)
        print(f"[CHAT_ENDPOINT] use_memory = {intent.get('use_memory')}", flush=True)
        
        if not intent["should_respond"]:
            response_text = ""
        else:
            print(f"[CHAT_ENDPOINT] memory_passed_to_generator = {intent.get('use_memory')}", flush=True)
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
