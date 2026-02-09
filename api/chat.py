from core.intent_engine import IntentEngine
from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel
from datetime import datetime
from typing import Dict, List, Optional
import json

from core.state import CognitiveState
from core.response_generator import ResponseGenerator
from core.log import log

from memory.episodic import store_event, get_recent_events, search_events
from memory.affective import compute_affect
from memory.salience import compute_salience

from core.relational_interpreter import RelationalInterpreter
from core.relational.accumulator import RelationalAccumulator

from core.tone import compute_tone

# Import per document context persistente
from api.upload import last_document_context

# Import per image handler
from core.image_handler import handle_image

# Import per ramo psicologico
from core.psychological_detector import detect as psy_detect
from core.psychological_memory import store as psy_store, get_context as psy_get_context
from core.psychological_responder import generate_psychological_response

router = APIRouter()


class ChatRequest(BaseModel):
    user_id: str
    message: str


@router.post("/chat")
async def chat_endpoint(request: ChatRequest, http_request: Request):
    # ===============================
    # LOG INGRESSO
    # ===============================
    log("CHAT_IN", user_id=request.user_id, msg=request.message)
    
    # ===============================
    # BLOCCO SEGNALI TECNICI STT
    # ===============================
    stt_technical_markers = [
        "[audio non riconosciuto]",
        "[audio troppo breve]",
        "[errore trascrizione]",
        "[silenzio]",
        "[trascrizione fallita]",
        ""  # Stringa vuota = nessuna trascrizione
    ]
    
    if request.message in stt_technical_markers:
        log("CHAT_STT_TECHNICAL", user_id=request.user_id, marker=request.message)
        # Risposta vuota statica, nessun TTS
        return {
            "response": "",
            "tts_mode": None,
            "should_respond": False,
            "state": {
                "user": {"user_id": request.user_id},
                "recent_events": [],
                "context": {}
            }
        }
    
    # ===============================
    # VALIDAZIONE USER_ID
    # ===============================
    if not request.user_id:
        request.user_id = http_request.headers.get("X-User-ID", "")
        if not request.user_id:
            log("CHAT_IN", error="missing_user_id")
    
    # ===============================
    # INTENT ENGINE (include closure)
    # ===============================
    # Eseguiamo subito per rilevare closure e bypassare tutto il resto
    state = CognitiveState.build(request.user_id)
    recent_memories = get_recent_events(request.user_id, limit=5)
    relevant_memories = search_events(request.user_id, request.message, limit=3)
    tone = compute_tone(recent_memories)
    intent_engine = IntentEngine()
    intent = intent_engine.decide(
        request.message,
        state.user,
        state,
        recent_memories,
        relevant_memories,
        tone
    )

    # ===============================
    # CLOSURE HANDLING: skip psycho, no memory side-effects
    # ===============================
    if intent.get("type") == "closure":
        log("INTENT_CLOSURE", user_id=request.user_id, level=intent.get("closure_level"))
        # Risposta diretta tramite ResponseGenerator (PRE-LLM)
        response_generator = ResponseGenerator()
        response_text = await response_generator.generate_response(
            user_message=request.message,
            cognitive_state=state,
            recent_memories=recent_memories,
            relevant_memories=relevant_memories,
            tone=tone,
            intent=intent
        )
        # Salviamo solo evento minimo in memoria episodica (no psicologica)
        user_affect = compute_affect("user_message", {"text": request.message})
        store_event(
            user_id=request.user_id,
            type="user_message",
            content={"text": request.message},
            salience=0.2,  # Bassa salience per closure
            affect=user_affect
        )
        if response_text.strip():  # Solo se c'è risposta
            store_event(
                user_id=request.user_id,
                type="system_response",
                content={"text": response_text},
                salience=0.2,
                affect=compute_affect("system_response", {"text": response_text})
            )
        return {
            "response": response_text,
            "tts_mode": "normal",
            "user_id": request.user_id,
            "timestamp": datetime.now().isoformat(),
            "closure": True
        }

    # ===============================
    # RAMO PSICOLOGICO — RILEVAZIONE AUTOMATICA
    # ===============================
    # Rileva PRIMA di tutto (tranne immagini attive).
    # Se attivo, devia al responder psicologico dedicato.
    if request.user_id:
        try:
            psy_detection = psy_detect(request.user_id, request.message)
            log("PSYCH_DETECT", user_id=request.user_id,
                active=psy_detection["active"],
                score=psy_detection["score"],
                severity=psy_detection["severity"],
                crisis=psy_detection["crisis"])
            
            if psy_detection["active"]:
                psy_detection["user_id"] = request.user_id
                log("BRANCH_SELECTED", branch="psychological", user_id=request.user_id,
                    severity=psy_detection["severity"], crisis=psy_detection["crisis"])
                
                # Recupera contesto psicologico dedicato
                psy_context = psy_get_context(request.user_id)
                log("MEMORY_LOAD", type="psychological", user_id=request.user_id,
                    entries=psy_context.get("total_interactions", 0))
                
                # Recupera nome utente se disponibile
                user_name = None
                if hasattr(state, 'user') and hasattr(state.user, 'profile'):
                    user_name = (state.user.profile or {}).get('name')
                
                # Genera risposta psicologica
                response_text = await generate_psychological_response(
                    user_message=request.message,
                    detection=psy_detection,
                    psy_context=psy_context,
                    user_name=user_name,
                )
                
                # Salva in memoria psicologica (isolata)
                psy_store(
                    user_id=request.user_id,
                    entry_type="theme" if not psy_detection["crisis"] else "crisis",
                    content=request.message,
                    severity=psy_detection["severity"],
                )
                log("MEMORY_SAVE", type="psychological", user_id=request.user_id,
                    entry_type="crisis" if psy_detection["crisis"] else "theme")
                
                # Salva anche in memoria episodica (per continuità conversazione)
                user_affect = compute_affect("user_message", {"text": request.message})
                store_event(
                    user_id=request.user_id,
                    type="user_message",
                    content={"text": request.message},
                    salience=0.8,
                    affect=user_affect
                )
                store_event(
                    user_id=request.user_id,
                    type="system_response",
                    content={"text": response_text},
                    salience=1.0,
                    affect=compute_affect("system_response", {"text": response_text})
                )
                log("MEMORY_SAVE", type="standard", user_id=request.user_id, event="user_message+system_response")
                
                return {
                    "response": response_text,
                    "tts_mode": "psychological",
                    "user_id": request.user_id,
                    "timestamp": datetime.now().isoformat(),
                    "psy_mode": True
                }
        except Exception as e:
            log("PSYCH_DETECT", error=str(e), user_id=request.user_id)
    
    # ===============================
    # BLOCCO IMMAGINI: PRIORITÀ ASSOLUTA
    # ===============================
    # Se esiste un'immagine attiva, TUTTO va a image_handler
    if request.user_id and request.user_id in last_document_context:
        persistent_doc = last_document_context[request.user_id]
        if persistent_doc.get('document_mode') == 'image':
            log("BRANCH_SELECTED", branch="image", user_id=request.user_id)
            
            # Bypassa COMPLETAMENTE il flusso chat standard
            response_text = await handle_image(
                image_context=persistent_doc,
                user_message=request.message,
                user_id=request.user_id
            )
            
            # NON cancellare l'immagine - rimane attiva per richieste successive
            # NON usare document_context, IntentEngine, ResponseGenerator
            
            return {
                "response": response_text,
                "user_id": request.user_id,
                "timestamp": datetime.now().isoformat(),
                "image_mode": True
            }
    
    # ===============================
    # DOCUMENT CONTEXT TEMPORANEO
    # ===============================
    document_context = None
    force_document_focus = False
    
    # Prima controlla il context persistente da upload
    if request.user_id and request.user_id in last_document_context:
        persistent_doc = last_document_context[request.user_id]
        
        # REGOLA NON NEGOZIABILE: se esiste document_context, usalo SEMPRE
        document_context = persistent_doc.get('content', '')
        force_document_focus = True

        log("BRANCH_SELECTED", branch="document", user_id=request.user_id, doc_len=len(document_context))

        # one-shot: rimuovi dopo l'uso
        del last_document_context[request.user_id]

    
    # Fallback: check per document context attivo (in session state)
    elif hasattr(http_request, 'state') and hasattr(http_request.state, 'active_document'):
        active_doc = http_request.state.active_document
        if active_doc and active_doc.get('user_id') == request.user_id:
            # Check per domande generiche sul documento
            vague_questions = ["cosa contiene", "che dice", "riassumi", "spiegami questo", "di cosa parla", "cosa c'è scritto"]
            is_vague_question = any(q in request.message.lower() for q in vague_questions)
            
            if is_vague_question:
                document_context = active_doc.get('content', '')
                force_document_focus = True
                log("BRANCH_SELECTED", branch="document", user_id=request.user_id, source="session")
                
                # Rimuovi context dopo uso (one-shot)
                delattr(http_request.state, 'active_document')
    else:
        log("PSYCH_DETECT", note="no_distress_detected", user_id=request.user_id) if False else None
    
    # 2. Compute message salience and affect
    user_salience = compute_salience(
        event_type="user_message",
        content={"text": request.message},
        past_events=[e for e in recent_memories if isinstance(e, dict) and e.get("content")]
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

    # 4. Get relevant context
    recent_memories = get_recent_events(request.user_id, limit=5)
    relevant_memories = search_events(request.user_id, request.message, limit=3)
    log("MEMORY_LOAD", type="standard", user_id=request.user_id,
        recent=len(recent_memories), relevant=len(relevant_memories))

    # 5. Compute conversation tone
    tone = compute_tone(state.recent_events)

    # 6. PIPELINE UNICA - Proactor + Generator in un solo passo
    generator = ResponseGenerator()
    final_result = await generator.generate_final_response(
        user_message=request.message,
        cognitive_state=state,
        recent_memories=recent_memories,
        relevant_memories=relevant_memories,
        tone=tone,
        intent={"should_respond": True},  # Pipeline decide internamente
        document_context=document_context
    )
    
    response_text = final_result.get("final_text", "")
    confidence = final_result.get("confidence", "ok")
    style = final_result.get("style", "standard")
    
    log("PIPELINE_COMPLETED", user_id=request.user_id, 
        path=final_result.get("path", "unknown"),
        final_text=response_text[:50])
    
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
    log("MEMORY_SAVE", type="standard", user_id=request.user_id, event="user_message+system_response")
    
    # Determina tts_mode in base al path e tipo risposta
    tts_mode = "normal"
    if final_result.get("path") == "tools":
        tts_mode = "informative"
    elif len(response_text) > 500:
        tts_mode = "informative"
    
    # LOG TTS OBBLIGATORIO
    print(f"[TTS_MANDATORY] user_id={request.user_id} response_len={len(response_text)} tts_mode={tts_mode}", flush=True)
    
    # NUOVO FORMATO API - FINAL_RESPONSE SEMPRE
    return {
        "final_text": response_text,
        "confidence": confidence,
        "style": style,
        "tts_mode": tts_mode,
        "should_respond": True,  # Pipeline sempre risponde
        "state": {
            "user": state.user.to_dict(),
            "recent_events": [e.to_dict() for e in state.recent_events[-5:]],
            "context": state.context
        }
    }
