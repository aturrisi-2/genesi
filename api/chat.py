from core.intent_engine import IntentEngine
from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel
from datetime import datetime
from typing import Dict, List, Optional
import json

from core.state import CognitiveState
# from core.response_generator import ResponseGenerator  # Sostituito da surgical_pipeline
from core.log import log

from memory.episodic import store_event, get_recent_events, search_events
from memory.affective import compute_affect
from memory.salience import compute_salience

# Memoria identitaria
from core.identity_memory import save_user_name, get_user_name, extract_name_from_message, is_name_query

from core.relational_interpreter import RelationalInterpreter
from core.relational.accumulator import RelationalAccumulator

from core.tone import compute_tone

# Import per document context persistente
from api.upload import last_document_context

# Import per nuova pipeline chirurgica
from core.surgical_pipeline import surgical_pipeline

# Import per ramo psicologico
from core.psychological_detector import detect as psy_detect
from core.psychological_memory import store as psy_store, get_context as psy_get_context
from core.psychological_responder import generate_psychological_response
from core.text_post_processor import text_post_processor
from core.intent_router import intent_router
from core.verified_knowledge import verified_knowledge
from core.post_llm_filter import post_llm_filter
from core.human_fallback import human_fallback

router = APIRouter()


class ChatRequest(BaseModel):
    user_id: str
    message: str


async def _handle_verified_response(
    routing_info: Dict,
    request: ChatRequest,
    state,
    recent_memories: List[Dict],
    relevant_memories: List[Dict],
    tone
) -> Dict:
    """
    GESTIONE RISPOSTE VERIFICATE - NESSUN LLM CREATIVO
    Solo fonti verificate, deterministico
    """
    intent_type = routing_info['intent']
    print(f"[VERIFIED_RESPONSE] Handling intent={intent_type}", flush=True)
    
    response_text = ""
    
    # Info mediche → Wikipedia con disclaimer
    if intent_type == "medical_info":
        print(f"[VERIFIED_RESPONSE] Using medical knowledge", flush=True)
        medical_data = verified_knowledge.get_medical_info(request.message)
        
        if medical_data.get("verified", False):
            content = medical_data.get("content", "")
            disclaimer = medical_data.get("disclaimer", "")
            
            if disclaimer and content:
                response_text = f"{content} {disclaimer}"
            else:
                response_text = content
        else:
            response_text = medical_data.get("content", "Per questioni mediche consulta un professionale.")
    
    # Info storiche → Wikipedia
    elif intent_type == "historical_info":
        print(f"[VERIFIED_RESPONSE] Using historical knowledge", flush=True)
        historical_data = verified_knowledge.get_historical_info(request.message)
        
        if historical_data.get("verified", False):
            response_text = historical_data.get("content", "Informazione storica non disponibile.")
        else:
            # DELEGA AL LLM se verified non ha dati certi
            print(f"[VERIFIED_RESPONSE] No verified data, delegating to LLM", flush=True)
            try:
                from core.local_llm import LocalLLM
                llm = LocalLLM()
                response_text = await llm.generate_chat_response(
                    message=request.message,
                    user_id=request.user_id,
                    context={"intent": intent_type, "source": "verified_fallback"}
                )
            except Exception as e:
                print(f"[VERIFIED_RESPONSE] LLM delegation failed: {e}", flush=True)
                response_text = "Non posso fornire informazioni su questo argomento in questo momento."
    
    # Meteo → Tools (stub per ora)
    elif intent_type == "weather":
        print(f"[VERIFIED_RESPONSE] Using weather tools", flush=True)
        try:
            from core.tools import resolve_tools
            tool_result = await resolve_tools(request.message)
            if tool_result and tool_result.get("data") and not tool_result["data"].get("error"):
                # Template semplice per meteo
                data = tool_result["data"]
                city = data.get("city", "la tua zona")
                current = data.get("current", {})
                if current:
                    temp = current.get("temp", "")
                    desc = current.get("description", "")
                    response_text = f"A {city} ci sono {temp}°C con {desc}."
                else:
                    response_text = "Non riesco a ottenere informazioni meteo in questo momento."
            else:
                # FALLBACK UMANO - non esporre errore tecnico
                response_text = human_fallback.get_fallback("weather", request.message)
        except Exception as e:
            print(f"[VERIFIED_RESPONSE] Weather tool error: {e}", flush=True)
            # FALLBACK UMANO - nascondi completamente l'errore
            response_text = human_fallback.get_fallback("weather", request.message)
    
    # News → Tools (stub per ora)
    elif intent_type == "news":
        print(f"[VERIFIED_RESPONSE] Using news tools", flush=True)
        try:
            from core.tools import resolve_tools
            tool_result = await resolve_tools(request.message)
            if tool_result and tool_result.get("data") and not tool_result["data"].get("error"):
                # Template semplice per news
                data = tool_result["data"]
                articles = data.get("articles", [])
                if articles:
                    title = articles[0].get("title", "").strip()
                    response_text = f"Notizia principale: {title}"
                else:
                    response_text = "Non ci sono notizie disponibili in questo momento."
            else:
                # FALLBACK UMANO - non esporre errore tecnico
                response_text = human_fallback.get_fallback("news", request.message)
        except Exception as e:
            print(f"[VERIFIED_RESPONSE] News tool error: {e}", flush=True)
            # FALLBACK UMANO - nascondi completamente l'errore
            response_text = human_fallback.get_fallback("news", request.message)
    
    # Supporto emotivo → ramo psicologico (senza LLM creativo)
    elif intent_type == "emotional_support":
        print(f"[VERIFIED_RESPONSE] Using psychological support", flush=True)
        try:
            # Usa il ramo psicologico esistente ma senza LLM creativo
            from core.genesi_response_engine import genesi_engine
            result = genesi_engine.generate_response_from_text(request.message)
            response_text = result.get("final_text", "")
            
            # FILTRO POST-LLM PER SUPPORTO EMOTIVO
            if response_text:
                context = {"intent": intent_type, "user_state": state}
                filtered_response = post_llm_filter.filter_response(response_text, context)
                
                if filtered_response and len(filtered_response.strip()) > 0:
                    response_text = filtered_response
                else:
                    # FALLBACK EMPATICO SE FILTRO INVALIDA
                    response_text = human_fallback.get_fallback("emotional_distress", request.message)
            else:
                # FALLBACK EMPATICO SE RESPONSE VUOTA
                response_text = human_fallback.get_fallback("emotional_distress", request.message)
                
        except Exception as e:
            print(f"[VERIFIED_RESPONSE] Psychological error: {e}", flush=True)
            # FALLBACK EMPATICO IN CASO DI ERRORE
            response_text = human_fallback.get_fallback("emotional_distress", request.message)
    
    # Identità → memoria nome utente
    elif intent_type == "identity":
        print(f"[VERIFIED_RESPONSE] Handling identity", flush=True)
        
        # 1. Controlla se l'utente sta fornendo il proprio nome
        extracted_name = extract_name_from_message(request.message)
        if extracted_name:
            # Salva il nome in memoria
            if save_user_name(request.user_id, extracted_name):
                response_text = f"Piacere, {extracted_name}! Ricorderò il tuo nome."
            else:
                response_text = f"Piacere, {extracted_name}!"
        else:
            # 2. Controlla se l'utente chiede il proprio nome
            if is_name_query(request.message):
                saved_name = get_user_name(request.user_id)
                if saved_name:
                    response_text = f"Sì, ti chiami {saved_name}."
                else:
                    response_text = human_fallback.get_fallback("identity", request.message)
            else:
                # 3. Altre domande identitarie
                response_text = "Sono Genesi, la tua assistente personale."
    
    # Tempo e date → sistema
    elif intent_type == "other":
        print(f"[VERIFIED_RESPONSE] Using system time", flush=True)
        now = datetime.now()
        
        # Mapping mesi in italiano
        mesi_italiani = {
            'January': 'gennaio', 'February': 'febbraio', 'March': 'marzo',
            'April': 'aprile', 'May': 'maggio', 'June': 'giugno',
            'July': 'luglio', 'August': 'agosto', 'September': 'settembre',
            'October': 'ottobre', 'November': 'novembre', 'December': 'dicembre'
        }
        
        mese_italiano = mesi_italiani.get(now.strftime('%B'), now.strftime('%B'))
        
        # Pattern per riconoscere tipo di richiesta temporale
        message_lower = request.message.lower()
        
        if "giorno" in message_lower or "data" in message_lower:
            # Formato italiano: 9 febbraio 2026
            response_text = f"Oggi è {now.day} {mese_italiano} {now.year}."
        elif "ora" in message_lower or "ore" in message_lower:
            # Formato italiano: 14:30
            response_text = f"Sono le {now.strftime('%H:%M')}."
        elif "anno" in message_lower:
            response_text = f"Siamo nel {now.year}."
        else:
            # Risposta generica
            response_text = f"Sono le {now.strftime('%H:%M')} del {now.day} {mese_italiano} {now.year}."
    
    # Fallback sicuro
    else:
        print(f"[VERIFIED_RESPONSE] Using safe fallback", flush=True)
        response_text = "Non posso aiutarti con questa richiesta in modo specifico."
    
    # POST-PROCESSOR LINGUISTICO - Pulisci anche risposte verificate
    if response_text:
        original_text = response_text
        response_text = text_post_processor.clean_response(response_text)
        if original_text != response_text:
            log("TEXT_POST_PROCESSOR", user_id=request.user_id, branch="verified",
                original_len=len(original_text), cleaned_len=len(response_text))
    
    # Salva in memoria se appropriato
    if response_text and intent_type != "other":
        system_affect = compute_affect("system_response", {"text": response_text})
        store_event(
            user_id=request.user_id,
            type="system_response",
            content={"text": response_text},
            salience=1.0,
            affect=system_affect
        )
        log("MEMORY_SAVE", type="verified", user_id=request.user_id, intent=intent_type)
    
    # Determina tts_mode
    tts_mode = "informative" if intent_type in ["medical_info", "historical_info", "weather", "news"] else "normal"
    
    print(f"[VERIFIED_RESPONSE] Final response: '{response_text}'", flush=True)
    
    # RITORNA RISPOSTA UNICA - NESSUN DOPPIO OUTPUT
    return {
        "response": response_text,
        "user_id": request.user_id,
        "timestamp": datetime.now().isoformat(),
        "tts_mode": tts_mode,
        "intent": intent_type,
        "source": routing_info['source'],
        "verified": True
    }


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
    # INTENT ENGINE (solo per context, non più routing)
    # ===============================
    # NOTA: La pipeline chirurgica gestisce internamente intent e routing
    # Questo codice è mantenuto solo per context e memory
    state = CognitiveState.build(request.user_id)
    recent_memories = get_recent_events(request.user_id, limit=5)
    relevant_memories = search_events(request.user_id, request.message, limit=3)
    tone = compute_tone(recent_memories)
    
    # Intent engine solo per context storico
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
    # VECCHIO ROUTING COMMENTATO - ora gestito da surgical_pipeline
    # ===============================
    # Il routing deterministico è ora gestito internamente dalla pipeline chirurgica
    # per evitare doppie generazioni e garantire il flusso obbligatorio
    
    # routing_info = intent_router.get_routing_info(request.message)
    # if routing_info['block_creative_llm']:
    #     return await _handle_verified_response(...)
    
    print(f"[CHAT] Using surgical pipeline (replaces old routing)", flush=True)

    # ===============================
    # CLOSURE HANDLING - ora gestito da surgical_pipeline
    # ===============================
    # NOTA: Anche closure è gestito internamente dalla pipeline chirurgica
    # per garantire flusso obbligatorio e evitare doppie generazioni
    
    # if intent.get("type") == "closure":
    #     log("INTENT_CLOSURE", user_id=request.user_id, level=intent.get("closure_level"))
    #     # Vecchio codice con ResponseGenerator - sostituito da pipeline
    
    print(f"[CHAT] Closure handling delegated to surgical pipeline", flush=True)

    # ===============================
    # RAMO PSICOLOGICO — RILEVAZIONE AUTOMATICA
    # ===============================
    # NOTA: Anche il ramo psicologico è gestito internamente dalla pipeline chirurgica
    # per garantire flusso obbligatorio e evitare doppie generazioni
    
    # if request.user_id:
    #     try:
    #         psy_detection = psy_detect(request.user_id, request.message)
    #         # ... vecchio codice psicologico
    
    print(f"[CHAT] Psychological handling delegated to surgical pipeline", flush=True)

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
            
            # POST-PROCESSOR LINGUISTICO - Pulisci anche risposte image
            if response_text:
                original_text = response_text
                response_text = text_post_processor.clean_response(response_text)
                if original_text != response_text:
                    log("TEXT_POST_PROCESSOR", user_id=request.user_id, branch="image",
                        original_len=len(original_text), cleaned_len=len(response_text))
            
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

    # 6. PIPELINE CHIRURGICA - Flusso obbligatorio
    print(f"[CHAT] Using surgical pipeline", flush=True)
    final_result = await surgical_pipeline.process_message(
        user_message=request.message,
        cognitive_state=state,
        recent_memories=recent_memories,
        relevant_memories=relevant_memories,
        tone=tone,
        intent={"should_respond": True},  # Pipeline decide internamente
        document_context=document_context
    )
    
    response_text = final_result.get("final_text", "")
    engine_used = final_result.get("engine_used", "unknown")
    
    print(f"[CHAT] Engine used: {engine_used}", flush=True)
    print(f"[CHAT] Response: '{response_text[:50]}...'", flush=True)
    
    # POST-PROCESSOR LINGUISTICO - Pulisci metatesto teatrale prima di tutto
    if response_text:
        original_text = response_text
        response_text = text_post_processor.clean_response(response_text)
        # Log silenzioso solo se c'è stata pulizia
        if original_text != response_text:
            log("TEXT_POST_PROCESSOR", user_id=request.user_id, 
                original_len=len(original_text), cleaned_len=len(response_text))
    
    log("PIPELINE_COMPLETED", user_id=request.user_id, 
        path="surgical",
        engine=engine_used,
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
        "response": response_text,  # CAMBIATO: final_text -> response
        "confidence": "ok",  # Default per pipeline chirurgica
        "style": "standard",  # Default per pipeline chirurgica
        "tts_mode": tts_mode,
        "should_respond": True,  # Pipeline sempre risponde
        "user_id": request.user_id,
        "timestamp": datetime.now().isoformat(),
        "state": {
            "user": state.user.to_dict(),
            "recent_events": [e.to_dict() for e in state.recent_events[-5:]],
            "context": state.context
        }
    }
