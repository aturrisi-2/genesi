"""
CHAT API - Genesi Core v2
1 intent → 1 funzione
Nessun orchestrazione, nessun fallback, nessun post-processing
Storage in-memory per validazione comportamento

SICUREZZA: user_id estratto SOLO dal JWT. Mai dal body/client.
"""

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Dict, Optional
from core.simple_chat import simple_chat_handler, strip_group_ctx
from core.user_manager import user_manager
from core.chat_memory import chat_memory
from core.log import log
from core.cognitive_memory_engine import CognitiveMemoryEngine
from core.storage import storage
from core.models.profile_model import UserProfile, Pet, Child
from core.identity_service import normalize_profile_dict
from core.identity_extractor import extract_identity_updates, merge_identity_update
from core.emoji_engine import apply
from core.intent_classifier import intent_classifier
from auth.router import require_auth
from auth.models import AuthUser
from datetime import datetime
import json
import re as _re
import asyncio as _asyncio_mod

router = APIRouter(prefix="/chat")


def _strip_tables_for_tts(text: str) -> str:
    """Rimuove la sintassi delle tabelle Markdown dal testo destinato al TTS."""
    lines = text.split('\n')
    result = []
    for line in lines:
        s = line.strip()
        # Rimuovi righe separatore |---|---|
        if s and _re.match(r'^\|([-| :]+\|)+$', s):
            continue
        # Converti righe tabella in testo leggibile
        if s.startswith('|') and s.endswith('|'):
            cells = [c.strip() for c in s.split('|')[1:-1] if c.strip()]
            if cells:
                result.append(', '.join(cells))
                continue
        result.append(line)
    return '\n'.join(result)

# Semaforo per limitare LLM calls in background (max 5 concurrent)
_BACKGROUND_LLM_SEM = _asyncio_mod.Semaphore(5)

MAX_MESSAGE_LENGTH = 12000  # caratteri massimi per messaggio (widget invia contesto pagina + subpage ~5k char)

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    platform: Optional[str] = None   # "widget" → blocca iniezione storico conversazioni personali

class ChatResponse(BaseModel):
    response: str
    status: str
    intent: Optional[str] = None
    user_id: Optional[str] = None
    tts_text: Optional[str] = None
    mic_control: Optional[Dict] = None

# Anti-bounce per evitare invii doppi
LAST_MESSAGES = {}

@router.post("", response_model=ChatResponse)
@router.post("/", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, user: AuthUser = Depends(require_auth)):
    try:
        user_id = user.id

        if len(request.message) > MAX_MESSAGE_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Messaggio troppo lungo. Massimo {MAX_MESSAGE_LENGTH} caratteri."
            )

        # 1. Anti-bounce: blocca messaggi identici < 2 secondi
        import time
        now = time.time()
        last = LAST_MESSAGES.get(user_id, {"msg": "", "time": 0})
        if request.message == last["msg"] and (now - last["time"]) < 2:
            log("CHAT_DUPLICATE_IGNORED", user_id=user_id, message=request.message[:50])
            return ChatResponse(response="Sto già elaborando la tua richiesta...", status="ok", intent="duplicate")
        LAST_MESSAGES[user_id] = {"msg": request.message, "time": now}

        log("API_CHAT", message=request.message[:100], user_id=user_id)

        # Handle commands like /cal
        if request.message.startswith("/cal"):
            from calendar_manager import calendar_manager
            parts = request.message.split(" ", 2)
            if len(parts) < 2:
                response = "Usa: /cal [provider] [titolo] [data ISO]\nEsempio: /cal apple \"Cena\" 2026-03-01T20:00:00"
            else:
                # Basic command: /cal apple "Evento" 2026-03-01T10:00:00
                cmd_parts = request.message.split(" ")
                provider = cmd_parts[1] if len(cmd_parts) > 1 else "detect"
                
                # Try to extract title and date
                # We'll use a simple approach for this urgent task
                try:
                    msg = request.message
                    if '"' in msg:
                        title = msg.split('"')[1]
                        dt_str = msg.split('"')[2].strip()
                    else:
                        title = cmd_parts[2] if len(cmd_parts) > 2 else "Evento"
                        dt_str = cmd_parts[3] if len(cmd_parts) > 3 else datetime.now().isoformat()
                    
                    dt = datetime.fromisoformat(dt_str)
                    success = calendar_manager.add_event(title, dt, provider)
                    response = f"✅ Evento '{title}' aggiunto a {provider}!" if success else f"❌ Errore aggiunta a {provider}."
                except Exception as e:
                    response = f"⚠️ Errore: {str(e)}. Usa: /cal apple \"Titolo\" 2026-03-01T10:00:00"
            
            return ChatResponse(response=response, status="ok", intent="calendar", user_id=user_id)

        # Cognitive Memory Evaluation
        cognitive_engine = CognitiveMemoryEngine()
        decision = await cognitive_engine.evaluate_event(user_id, request.message, {})

        # Load profile once for all updates
        raw_profile = await storage.load(f"profile:{user_id}", default={})
        
        profile_changed = False

        normalized = normalize_profile_dict(raw_profile)
        profile = UserProfile(**normalized)
        
        # Ensure critical context is present in model
        if not profile.email and user.email:
            profile.email = user.email
            profile_changed = True
        if not profile.user_id:
            profile.user_id = user_id
            profile_changed = True

        # Cognitive memory: explicit identity fields
        if decision.get('persist'):
            if decision.get('memory_type') == 'profile':
                key = decision['key']
                val = decision['value']

                if key == "name":
                    profile.name = val
                elif key == "city":
                    profile.city = val
                elif key == "profession":
                    profile.profession = val
                elif key == "spouse":
                    profile.spouse = val
                elif key == "children":
                    profile.children = [Child(**c) if isinstance(c, dict) else c for c in val]
                elif key == "pets":
                    if isinstance(val, list):
                        profile.pets.extend([Pet(**p) if isinstance(p, dict) else p for p in val])
                    else:
                        pet = Pet(**val) if isinstance(val, dict) else val
                        profile.pets.append(pet)

                profile_changed = True

        # Save profile if cognitive memory update occurred (no identity yet)
        if profile_changed:
            profile.updated_at = datetime.utcnow()
            await storage.save(f"profile:{user_id}", profile.model_dump(mode="json"))
            log("STORAGE_SAVE", key=f"profile:{user_id}")

        # Identity extractor: runs in BACKGROUND while proactor generates response.
        # Saves ~1-2s per message (avoids blocking on gpt-4o-mini call).
        async def _extract_and_save_identity():
            async with _BACKGROUND_LLM_SEM:
                try:
                    history = chat_memory.get_messages(user_id, limit=3) if user_id else []
                    history_text = "\n".join([f"utente: {msg.get('user_message', '')}\ngenesi: {msg.get('system_response', '')}" for msg in history])
                    identity_update = await extract_identity_updates(request.message, history_text)
                    if identity_update.interests or identity_update.preferences or \
                       identity_update.traits or identity_update.pets or \
                       identity_update.children or identity_update.spouse:
                        fresh_raw = await storage.load(f"profile:{user_id}", default={})
                        fresh_profile = UserProfile(**normalize_profile_dict(fresh_raw))
                        merge_identity_update(fresh_profile, identity_update)
                        fresh_profile.updated_at = datetime.utcnow()
                        await storage.save(f"profile:{user_id}", fresh_profile.model_dump(mode="json"))
                        log("IDENTITY_SAVE_BACKGROUND", user_id=user_id)
                except Exception as _e:
                    log("IDENTITY_SAVE_BACKGROUND_ERROR", user_id=user_id, error=str(_e))

        import asyncio as _asyncio

        # Testo utente pulito (senza group_ctx) — usato da tutti i sistemi di memoria.
        # Il messaggio completo (con group_ctx) serve solo al proactor per rispondere.
        _clean_msg = strip_group_ctx(request.message)

        # Predictive engine: assess sorpresa dell'input rispetto alla predizione attesa
        # (lightweight: storage read + Jaccard, nessuna chiamata LLM)
        _assess_input = _clean_msg
        async def _assess_prediction_input():
            try:
                from core.predictive_engine import predictive_engine as _pe
                await _pe.assess(user_id, _assess_input)
            except Exception:
                pass
        _asyncio.create_task(_assess_prediction_input())

        # Episode extractor: estrae eventi personali temporali in BACKGROUND
        # Usa _clean_msg (senza group_ctx) per evitare che lo storico gruppo inquini gli episodi
        _ep_msg = _clean_msg
        async def _extract_and_save_episode():
            async with _BACKGROUND_LLM_SEM:
                try:
                    from core.episode_extractor import extract_episodes
                    from core.episode_memory import episode_memory as _em
                    episodes = await extract_episodes(_ep_msg, user_id)
                    for ep in episodes:
                        await _em.add(user_id, ep)
                        log("EPISODE_SAVED", user_id=user_id, text=ep['text'][:60])
                except Exception as _ep_e:
                    log("EPISODE_SAVE_ERROR", user_id=user_id, error=str(_ep_e))

        # Gruppi: episodi attivi ma solo se il testo ha contenuto semantico (>10 chars)
        if _clean_msg and len(_clean_msg) > 10:
            _asyncio.create_task(_extract_and_save_episode())

        # 2. Pipeline Relazionale / Tecnico (Orchestrata dal Proactor)
        # Capability context: se l'utente chiede cosa Genesi sa fare, inietta la mappa capacità
        _chat_message = request.message
        try:
            from core.capability_awareness import is_meta_query, load_capability_map, build_capability_context_block
            if is_meta_query(request.message):
                _cap_map = load_capability_map()
                _cap_block = build_capability_context_block(_cap_map)
                if _cap_block:
                    _chat_message = f"{request.message}\n\n{_cap_block}"
                    log("CAPABILITY_CONTEXT_INJECTED", user_id=user_id, msg_len=len(_chat_message))
        except Exception:
            pass
        _handler_result = await simple_chat_handler(user_id, _chat_message, request.conversation_id, platform=request.platform)
        if isinstance(_handler_result, tuple):
            response, classified_intent = _handler_result[0], _handler_result[1]
        else:
            response, classified_intent = _handler_result, "chat_free"

        # Identity extractor: gira DOPO simple_chat_handler per evitare race condition
        # con _handle_memory_correction (che salva il profilo dentro simple_chat_handler).
        if request.platform != "telegram_group":
            _asyncio.create_task(_extract_and_save_identity())

        # Defensive normalization: ensure response is always a string
        if not isinstance(response, str):
            response = str(response)

        # Consolidazione memoria globale in background (max 1 volta/24h per utente)
        try:
            from core.global_memory_service import global_memory_service
            async def _consolidate_global_memory():
                async with _BACKGROUND_LLM_SEM:
                    await global_memory_service.consolidate_if_needed(user_id)
            _asyncio.create_task(_consolidate_global_memory())
        except Exception:
            pass

        # Personal facts extraction: fatti rivelati in conversazione (abitudini, preferenze, familiari...)
        # Usa _clean_msg per evitare che il group_ctx (contiene nomi di tutti i membri) inquini i fatti
        _raw_response = response
        _pf_msg = _clean_msg
        async def _extract_and_save_personal_facts():
            async with _BACKGROUND_LLM_SEM:
                try:
                    from core.personal_facts_service import personal_facts_service as _pfs
                    await _pfs.extract_and_save(_pf_msg, _raw_response, user_id)
                except Exception as _pf_e:
                    log("PERSONAL_FACTS_SAVE_ERROR", user_id=user_id, error=str(_pf_e))
        # Gruppi: personal facts attivi su testo pulito (>10 chars)
        if _clean_msg and len(_clean_msg) > 10:
            _asyncio.create_task(_extract_and_save_personal_facts())

        # Predictive engine: aggiorna predizione prossimo turno (background)
        _pred_msg  = _clean_msg
        _pred_resp = _raw_response
        async def _update_prediction():
            async with _BACKGROUND_LLM_SEM:
                try:
                    from core.predictive_engine import predictive_engine as _pe
                    await _pe.update_prediction(user_id, _pred_msg, _pred_resp)
                except Exception:
                    pass
        _asyncio.create_task(_update_prediction())

        # Behavioral memory update in background (zero-cost, no LLM)
        _beh_msg = _clean_msg
        _beh_resp = _raw_response
        async def _update_behavioral_memory():
            try:
                from core.behavioral_memory import behavioral_memory as _bm
                await _bm.update(
                    user_id=user_id,
                    user_msg=_beh_msg,
                    assistant_msg=_beh_resp,
                )
            except Exception:
                pass
        _asyncio.create_task(_update_behavioral_memory())

        # Audit automatico ogni 100 turni di chat (background, silenzioso)
        async def _maybe_audit():
            try:
                from core.genesi_auditor import genesi_auditor as _auditor
                _counter_file = "monitor_trigger_count.txt"
                try:
                    with open(_counter_file, "r") as _cf:
                        _count = int(_cf.read().strip())
                except Exception:
                    _count = 0
                _count += 1
                with open(_counter_file, "w") as _cf:
                    _cf.write(str(_count))
                if _count % 100 == 0:
                    log("AUDIT_AUTO_TRIGGER", turn=_count, user_id=user_id)
                    await _auditor.generate_report()
            except Exception:
                pass
        _asyncio.create_task(_maybe_audit())

        # Capability gap detection in background (fail-silent, nessun impatto sul flusso)
        _gap_msg  = _clean_msg
        _gap_resp = _raw_response
        _gap_intent = classified_intent
        async def _detect_capability_gap():
            try:
                from core.capability_awareness import detect_gap, log_gap
                is_gap, gap_type = detect_gap(_gap_msg, _gap_resp, _gap_intent)
                if is_gap and gap_type:
                    await log_gap(_gap_msg, _gap_resp, _gap_intent,
                                  platform=request.platform or "web",
                                  user_id=user_id, gap_type=gap_type)
            except Exception:
                pass
        _asyncio.create_task(_detect_capability_gap())

        # Usa il vero intent classificato (surfacato da simple_chat_handler)
        intent = classified_intent
        
        # Apply emoji enrichment to final response (after all routing and fallbacks)
        if response and not response.startswith('{') and not response.startswith('['):
            # Skip structured JSON and responses that already contain emojis
            if not any(ord(c) > 127 and c in '👋😊📅⏰📋✨⚠️🤔✨💬🤝🛠️☀️🌤️🌞🌧️⛅' for c in response):
                original_response = response
                response = apply(response, intent)
                
                # Log emoji application if response was modified
                if response != original_response:
                    # Extract emojis from response for logging
                    emojis = ''.join([c for c in response if ord(c) > 127 and c in '👋😊📅⏰📋✨⚠️🤔✨💬🤝🛠️☀️🌤️🌞🌧️⛅'])
                    log("EMOJI_ENGINE_APPLIED", intent=intent, emoji=emojis, user_id=user_id)

        # Handle silent responses (e.g. lists)
        tts_text = response
        if response.startswith("[NO_TTS]"):
            response = response.replace("[NO_TTS]", "").strip()
            tts_text = ""

        # If backend returned structured payload with images, keep JSON for frontend
        # and set tts_text to plain human text.
        if isinstance(response, str) and response.strip().startswith('{"text"'):
            try:
                parsed = json.loads(response)
                if isinstance(parsed, dict) and parsed.get("text"):
                    tts_text = parsed.get("tts_text") or parsed.get("text")
            except Exception:
                pass

        if tts_text:
            tts_text = _strip_tables_for_tts(tts_text)

        return ChatResponse(
            response=response,
            status="ok",
            intent=intent,
            user_id=user_id,
            tts_text=tts_text,
            mic_control={"type": "TTS_START", "status": "speaking"}
        )

    except Exception as e:
        log("API_CHAT_ERROR", error=str(e), user_id=user.id if user else "unknown")
        raise HTTPException(status_code=500, detail="Chat error")

@router.post("/stream")
@router.post("/stream/")
async def chat_stream_endpoint(request: ChatRequest, user: AuthUser = Depends(require_auth)):
    """
    SSE streaming endpoint — testo LLM arriva in tempo reale.
    Usa ContextVar per iniettare la queue nel llm_service senza modificare il proactor.
    """
    import asyncio as _aio
    from fastapi.responses import StreamingResponse as _SR
    from core.llm_service import _STREAM_QUEUE
    from core.simple_chat import simple_chat_handler as _sch, strip_group_ctx as _sgc

    user_id = user.id
    queue: _aio.Queue = _aio.Queue()

    async def _run_pipeline():
        try:
            # Testo pulito dal group_ctx — usato da tutti i sistemi di memoria dello stream
            _stream_clean_msg = _sgc(request.message)

            # Predictive engine: assess sorpresa input (lightweight, prima del processing)
            _stream_assess_msg = _stream_clean_msg
            async def _stream_assess_prediction():
                try:
                    from core.predictive_engine import predictive_engine as _pe
                    await _pe.assess(user_id, _stream_assess_msg)
                except Exception:
                    pass
            _aio.create_task(_stream_assess_prediction())

            # Capability context injection (meta-query: "cosa sai fare?")
            _stream_chat_message = request.message
            try:
                from core.capability_awareness import is_meta_query as _is_meta, load_capability_map as _lcm, build_capability_context_block as _bccb
                if _is_meta(request.message):
                    _cap_map = _lcm()
                    _cap_block = _bccb(_cap_map)
                    if _cap_block:
                        _stream_chat_message = f"{request.message}\n\n{_cap_block}"
                        log("CAPABILITY_CONTEXT_INJECTED", user_id=user_id, msg_len=len(_stream_chat_message))
            except Exception:
                pass
            resp = await _sch(user_id, _stream_chat_message, request.conversation_id, platform=request.platform)
            if isinstance(resp, tuple):
                resp = resp[0]
            if not isinstance(resp, str):
                resp = str(resp)
            # Consolidazione memoria globale in background (max 1/24h per utente)
            try:
                from core.global_memory_service import global_memory_service
                async def _stream_consolidate_global_memory():
                    async with _BACKGROUND_LLM_SEM:
                        await global_memory_service.consolidate_if_needed(user_id)
                _aio.create_task(_stream_consolidate_global_memory())
            except Exception:
                pass
            # Episode extractor in background (eventi personali temporali)
            # Usa _stream_clean_msg (senza group_ctx) per episodi puliti
            _stream_ep_msg = _stream_clean_msg
            async def _stream_extract_episode():
                async with _BACKGROUND_LLM_SEM:
                    try:
                        from core.episode_extractor import extract_episodes
                        from core.episode_memory import episode_memory as _em
                        episodes = await extract_episodes(_stream_ep_msg, user_id)
                        for ep in episodes:
                            await _em.add(user_id, ep)
                            log("EPISODE_SAVED", user_id=user_id, text=ep['text'][:60])
                    except Exception as _ep_e:
                        log("EPISODE_SAVE_ERROR", user_id=user_id, error=str(_ep_e))
            if _stream_clean_msg and len(_stream_clean_msg) > 10:
                _aio.create_task(_stream_extract_episode())
            # Personal facts extraction in background (abitudini, preferenze, familiari...)
            _stream_resp = resp
            _stream_pf_msg = _stream_clean_msg
            async def _stream_extract_personal_facts():
                async with _BACKGROUND_LLM_SEM:
                    try:
                        from core.personal_facts_service import personal_facts_service as _pfs
                        await _pfs.extract_and_save(_stream_pf_msg, _stream_resp, user_id)
                    except Exception as _pf_e:
                        log("PERSONAL_FACTS_SAVE_ERROR", user_id=user_id, error=str(_pf_e))
            if _stream_clean_msg and len(_stream_clean_msg) > 10:
                _aio.create_task(_stream_extract_personal_facts())

            # Predictive engine: aggiorna predizione prossimo turno (background)
            _stream_pred_msg  = _stream_clean_msg
            _stream_pred_resp = resp
            async def _stream_update_prediction():
                async with _BACKGROUND_LLM_SEM:
                    try:
                        from core.predictive_engine import predictive_engine as _pe
                        await _pe.update_prediction(user_id, _stream_pred_msg, _stream_pred_resp)
                    except Exception:
                        pass
            _aio.create_task(_stream_update_prediction())

            # Behavioral memory update in background (zero-cost, no LLM)
            _stream_beh_msg = _stream_clean_msg
            _stream_beh_resp = resp
            async def _stream_update_behavioral():
                try:
                    from core.behavioral_memory import behavioral_memory as _bm
                    await _bm.update(
                        user_id=user_id,
                        user_msg=_stream_beh_msg,
                        assistant_msg=_stream_beh_resp,
                    )
                except Exception:
                    pass
            _aio.create_task(_stream_update_behavioral())

            # Capability gap detection in background (fail-silent)
            _stream_gap_msg  = _stream_clean_msg
            _stream_gap_resp = resp
            async def _stream_detect_gap():
                try:
                    from core.capability_awareness import detect_gap, log_gap
                    is_gap, gap_type = detect_gap(_stream_gap_msg, _stream_gap_resp, "stream")
                    if is_gap and gap_type:
                        await log_gap(_stream_gap_msg, _stream_gap_resp, "stream",
                                      platform=request.platform or "web",
                                      user_id=user_id, gap_type=gap_type)
                except Exception:
                    pass
            _aio.create_task(_stream_detect_gap())

            # Audit automatico ogni 100 turni di chat (background, silenzioso)
            async def _stream_maybe_audit():
                try:
                    from core.genesi_auditor import genesi_auditor as _auditor
                    _counter_file = "monitor_trigger_count.txt"
                    try:
                        with open(_counter_file, "r") as _cf:
                            _count = int(_cf.read().strip())
                    except Exception:
                        _count = 0
                    _count += 1
                    with open(_counter_file, "w") as _cf:
                        _cf.write(str(_count))
                    if _count % 100 == 0:
                        log("AUDIT_AUTO_TRIGGER", turn=_count, user_id=user_id)
                        await _auditor.generate_report()
                except Exception:
                    pass
            _aio.create_task(_stream_maybe_audit())

            await queue.put({"done": True, "response": resp})
        except Exception as _e:
            log("CHAT_STREAM_PIPELINE_ERROR", user_id=user_id, error=str(_e))
            await queue.put({"error": str(_e)})

    # Set the ContextVar BEFORE creating the task (task copies current context)
    _STREAM_QUEUE.set(queue)
    pipeline_task = _aio.create_task(_run_pipeline())

    async def _event_generator():
        try:
            while True:
                try:
                    item = await _aio.wait_for(queue.get(), timeout=45.0)
                except _aio.TimeoutError:
                    yield f"data: {json.dumps({'error': 'timeout'})}\n\n"
                    break

                if "chunk" in item:
                    yield f"data: {json.dumps({'chunk': item['chunk']})}\n\n"
                elif "status" in item:
                    yield f"data: {json.dumps({'status': item['status']})}\n\n"
                elif "done" in item:
                    full = item["response"]
                    tts = full
                    if full.startswith("[NO_TTS]"):
                        full = full.replace("[NO_TTS]", "").strip()
                        tts = ""
                        
                    # Fix: If backend returned structured JSON payload, extract internal tts_text
                    if isinstance(full, str) and full.strip().startswith('{"text"'):
                        try:
                            parsed = json.loads(full)
                            if isinstance(parsed, dict) and parsed.get("text"):
                                tts = parsed.get("tts_text") or parsed.get("text")
                        except Exception:
                            pass

                    if tts:
                        tts = _strip_tables_for_tts(tts)

                    yield f"data: {json.dumps({'done': True, 'tts_text': tts, 'response': full})}\n\n"
                    break
                elif "error" in item:
                    yield f"data: {json.dumps({'error': item['error']})}\n\n"
                    break
        finally:
            if not pipeline_task.done():
                pipeline_task.cancel()

    return _SR(_event_generator(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",   # disabilita buffering nginx
    })


@router.get("/user/info")
async def get_user_info(user: AuthUser = Depends(require_auth)):
    """
    Ottieni info utente autenticato - user_id dal JWT
    """
    try:
        user_id = user.id
        user_data = user_manager.get_user(user_id)
        if not user_data:
            user_data = user_manager.create_user(user_id)
        
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
        log("USER_INFO_ERROR", user_id=user.id, error=str(e))
        raise HTTPException(status_code=500, detail="User info error")


# ── Endpoint gruppo WhatsApp (Baileys) ────────────────────────────────────────

class GroupChatRequest(BaseModel):
    text: str
    sender_name: str
    sender_id: str   # numero telefono o JID
    group_id: str    # JID gruppo WhatsApp

class GroupChatResponse(BaseModel):
    response: str
    status: str

@router.post("/group", response_model=GroupChatResponse)
async def group_chat_endpoint(request: GroupChatRequest, user: AuthUser = Depends(require_auth)):
    """
    Endpoint dedicato ai gruppi WhatsApp (Baileys).
    Usa la stessa logica memoria/contesto del gruppo Telegram:
    - append_raw_message (buffer discussione)
    - build_group_context (contesto famiglia, fatti, dinamiche)
    - update_member_seen (presenza membro)
    - extract_family_relationship (aggiorna albero familiare)
    - append_group_history / record_group_observation (memoria post-risposta)
    """
    import asyncio as _aio
    try:
        from core.telegram_group_memory import (
            append_raw_message, build_group_context,
            update_member_seen, extract_family_relationship,
            append_group_history, record_group_observation,
            consolidate_group_insights_if_needed,
            summarize_group_discussion_if_needed,
        )

        # Normalizza group_id e sender_id a interi (come fa whatsapp_bot.py)
        clean_sender = request.sender_id.replace("@s.whatsapp.net", "").replace("+", "")
        clean_group  = request.group_id.replace("@g.us", "").replace("-", "")
        try:
            sender_int = abs(hash(clean_sender)) % (10**9)
            group_int  = abs(hash(clean_group))  % (10**9)
        except Exception:
            sender_int = 0
            group_int  = 0

        # 0. Auto-match nome → parentela dal family_tree di Alfio
        #    Se il nome corrisponde a un membro noto, pre-popola la relazione subito
        try:
            from core.telegram_group_memory import _member_key, _storage as _tgm_storage
            _tgm_s = await _tgm_storage()
            member = await _tgm_s.load(_member_key(sender_int), default={}) or {}
            if not member.get("relationship_to_owner"):
                owner_profile = await storage.load(f"profile:{user.id}", default={})
                ft = owner_profile.get("family_tree", {})
                sender_name_lower = request.sender_name.lower()
                for _v in ft.values():
                    if _v.get("name", "").lower() == sender_name_lower:
                        member["relationship_to_owner"] = _v.get("relationship", "")
                        member["display_name"] = _v.get("name", request.sender_name)
                        member.setdefault("first_name", request.sender_name)
                        await _tgm_s.save(_member_key(sender_int), member)
                        log("WA_GROUP_MEMBER_AUTOLINKED", name=request.sender_name, rel=member["relationship_to_owner"])
                        break
        except Exception:
            pass

        # 1. Salva nel buffer grezzo (sempre, prima di decidere se rispondere)
        _aio.create_task(append_raw_message(group_int, sender_int, request.sender_name, request.text))

        # 2. Aggiorna presenza membro
        _aio.create_task(update_member_seen(sender_int, request.sender_name))

        # 3. Estrai parentela in background
        _aio.create_task(extract_family_relationship(clean_sender, request.sender_name, request.text, "whatsapp"))

        # 3b. Birthday: collega pre-seed e prova a estrarre data nascita dal messaggio
        try:
            from core.birthday_service import link_preseed_to_member, try_extract_birthday
            _aio.create_task(link_preseed_to_member(sender_int, request.sender_name))
            if request.text and len(request.text.strip()) > 8:
                _aio.create_task(try_extract_birthday(sender_int, request.sender_name, request.text))
        except Exception:
            pass

        # 4. Costruisci contesto gruppo (sincrono — serve per la risposta)
        group_ctx = await build_group_context(group_int, sender_int, request.sender_name)

        # 5. Costruisci messaggio arricchito (stesso formato di telegram_bot.py)
        only_emoji = all(ord(c) > 127 or c in (' ', '\n') for c in request.text.strip())
        if only_emoji:
            enriched = (
                f"{request.text}\n\n"
                f"[GRUPPO FAMILIARE: scrive {request.sender_name}. "
                f"Reazione/emoji — risposta brevissima, calore familiare, zero domande.]\n"
                f"{group_ctx}"
            )
        else:
            enriched = (
                f"{request.text}\n\n"
                f"[GRUPPO FAMILIARE: scrive {request.sender_name}. "
                f"Sei un membro della famiglia — rispondi con calore e concretezza, "
                f"senza domande superflue. Usa il nome {request.sender_name}.]\n"
                f"{group_ctx}"
            )

        log("GROUP_CHAT_WA", sender=request.sender_name, group=request.group_id[:20], msg=request.text[:60])

        # 6. Chiama simple_chat_handler con platform=whatsapp_group
        response, _intent = await simple_chat_handler(
            user_id=user.id,
            message=enriched,
            platform="whatsapp_group",
        )

        # 7. Post-risposta in background
        _aio.create_task(append_group_history(group_int, sender_int, request.sender_name, request.text, response))
        _aio.create_task(record_group_observation(group_int, sender_int, request.sender_name, request.text, response))
        _aio.create_task(consolidate_group_insights_if_needed(group_int))
        _aio.create_task(summarize_group_discussion_if_needed(group_int))

        # 8. Memoria personale del mittente — episodi e fatti su request.text (già pulito)
        if request.text and len(request.text.strip()) > 10:
            _wa_text = request.text
            _wa_resp = response
            _wa_uid  = user.id

            async def _wa_extract_episode():
                async with _BACKGROUND_LLM_SEM:
                    try:
                        from core.episode_extractor import extract_episodes
                        from core.episode_memory import episode_memory as _em
                        # Prefissa il nome per contestualizzare l'episodio
                        _ctx_msg = f"{request.sender_name}: {_wa_text}"
                        for ep in await extract_episodes(_ctx_msg, _wa_uid):
                            await _em.add(_wa_uid, ep)
                            log("EPISODE_SAVED_GROUP", sender=request.sender_name, text=ep['text'][:60])
                    except Exception:
                        pass
            _aio.create_task(_wa_extract_episode())

            async def _wa_extract_personal_facts():
                async with _BACKGROUND_LLM_SEM:
                    try:
                        from core.personal_facts_service import personal_facts_service as _pfs
                        _ctx_msg = f"{request.sender_name}: {_wa_text}"
                        await _pfs.extract_and_save(_ctx_msg, _wa_resp, _wa_uid)
                    except Exception:
                        pass
            _aio.create_task(_wa_extract_personal_facts())

            async def _wa_global_memory():
                async with _BACKGROUND_LLM_SEM:
                    try:
                        from core.global_memory_service import global_memory_service as _gms
                        await _gms.consolidate_if_needed(_wa_uid)
                    except Exception:
                        pass
            _aio.create_task(_wa_global_memory())

        return GroupChatResponse(response=response, status="ok")

    except Exception as e:
        log("GROUP_CHAT_ERROR", error=str(e))
        raise HTTPException(status_code=500, detail="Group chat error")


# ── Endpoint: LLM decide se Genesi deve intervenire nel gruppo ────────────────

_GROUP_INTERVENE_PROMPT = """\
Sei il filtro di intervento di Genesi in un gruppo familiare su WhatsApp.
Genesi è discreta: ascolta in silenzio e interviene solo nelle situazioni indicate.

Leggi il messaggio attuale (e i messaggi recenti se presenti). Decidi se Genesi deve rispondere.

RISPONDI "SI" SOLO se il messaggio rientra in UNO di questi casi:
1. INVOCATA: qualcuno cita Genesi per nome o le pone una domanda diretta
2. SALUTO O AUGURIO: qualcuno saluta o fa un augurio al gruppo (ciao, buongiorno, buonasera, buon pranzo, buona cena, buon natale, buona pasqua, buon anno, auguri, tanti auguri, buon weekend, buone feste, ecc. — in qualsiasi lingua o forma)
3. BUONA NOTIZIA: qualcuno condivide una notizia bella, un successo, un traguardo, qualcosa da celebrare
4. CONTINUAZIONE: è un follow-up diretto a una risposta appena data da Genesi (< 5 min).
   Se nei messaggi recenti vedi "Genesi: ..." seguito da una domanda breve (dove?, come?, perché?, e voi?, ma voi?,
   da dove rispondete?, dove siete?, ecc.) → è quasi certamente un follow-up per Genesi → INTERVIENI.

RISPONDI "NO" in tutti gli altri casi:
- Conversazioni, discussioni, battute solo tra i membri (senza risposta recente di Genesi)
- Domande chiaramente rivolte a un membro specifico del gruppo
- Sfogo o momento difficile (Genesi resta in silenzio)

ATTENZIONE: se nell'elenco dei messaggi recenti compare "Genesi: <risposta>", il messaggio attuale
è probabilmente una reazione o domanda a Genesi → il dubbio va verso SI.
Negli altri casi il dubbio va verso NO.
Rispondi SOLO con JSON: {"intervieni": true, "motivo": "breve"} oppure {"intervieni": false, "motivo": "breve"}
"""

class ShouldRespondRequest(BaseModel):
    text: str
    recent_messages: Optional[list] = None  # [{name, text}]

class ShouldRespondResponse(BaseModel):
    intervieni: bool
    motivo: str

@router.post("/group/should_respond", response_model=ShouldRespondResponse)
async def group_should_respond(request: ShouldRespondRequest, user: AuthUser = Depends(require_auth)):
    """LLM decide se Genesi deve intervenire nel gruppo WhatsApp."""
    try:
        from core.llm_service import llm_service
        import json as _json

        recent = ""
        if request.recent_messages:
            recent = "\nMessaggi recenti:\n" + "\n".join(
                f"  {m.get('name','?')}: {m.get('text','')[:100]}"
                for m in request.recent_messages[-8:]
            )

        user_content = f"Messaggio attuale: {request.text[:300]}{recent}"

        raw = await llm_service._call_model(
            "openai/gpt-4o-mini",
            _GROUP_INTERVENE_PROMPT,
            user_content,
            user_id="group-intervene-filter",
            route="memory",
        )
        if not raw:
            return ShouldRespondResponse(intervieni=False, motivo="no response")

        clean = raw.strip().strip("```").strip()
        if clean.startswith("json"):
            clean = clean[4:]
        parsed = _json.loads(clean)
        return ShouldRespondResponse(
            intervieni=bool(parsed.get("intervieni", False)),
            motivo=parsed.get("motivo", ""),
        )
    except Exception as e:
        log("GROUP_SHOULD_RESPOND_ERROR", error=str(e))
        # Fallback: non intervenire in caso di errore
        return ShouldRespondResponse(intervieni=False, motivo="error")


@router.get("/user/messages")
async def get_user_messages(user: AuthUser = Depends(require_auth), limit: Optional[int] = 10):
    """
    Ottieni messaggi utente autenticato - user_id dal JWT
    """
    try:
        user_id = user.id
        messages = chat_memory.get_messages(user_id, limit)
        return {
            "user_id": user_id,
            "messages": messages,
            "count": len(messages)
        }
        
    except Exception as e:
        log("USER_MESSAGES_ERROR", user_id=user.id, error=str(e))
        raise HTTPException(status_code=500, detail="User messages error")

@router.delete("/user/messages")
async def clear_user_messages(user: AuthUser = Depends(require_auth)):
    """
    Pulisci messaggi utente autenticato - user_id dal JWT
    """
    try:
        user_id = user.id
        success = chat_memory.clear_messages(user_id)
        return {
            "user_id": user_id,
            "cleared": success
        }
        
    except Exception as e:
        log("USER_CLEAR_ERROR", user_id=user.id, error=str(e))
        raise HTTPException(status_code=500, detail="User clear error")

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": "v2", "storage": "in-memory"}

# Global flags for TTS status (if needed by frontend)
is_speaking_global = False
vad_active_global = True

@router.post("/tts-state")
async def tts_state():
    """Endpoint per monitorare lo stato del TTS dal backend."""
    return {"isSpeaking": is_speaking_global, "vadActive": vad_active_global}

async def _generate_human_reminder_list(user_id: str, message: str, reminders: list) -> str:
    """Genera una risposta naturale e umana agli impegni trovati."""
    from core.llm_service import llm_service
    
    # Prepariamoci l'elenco testuale per il prompt
    items_text = ""
    for i, r in enumerate(reminders, 1):
        dt = r.get('datetime') or r.get('due') or 'Non specificato'
        items_text += f"- {r['text']} ({dt})\n"

    prompt = f"""Sei Genesi, l'assistente personale intelligente dell'utente. 
L'utente ti ha appena chiesto dei suoi impegni con questo messaggio: "{message}"

Ecco i dati reali che ho trovato nei tuoi archivi (iCloud, Google e Locale):
{items_text}

Rispondi come farebbe un segretario umano molto efficiente e cordiale:
- Se l'utente chiede cosa fare "oggi" o "stasera", focalizzati sugli impegni imminenti.
- Non elencare i dati in modo freddo (es. non dire "ID: 123, Data: ...").
- Usa frasi naturali: "Per oggi hai in programma...", "Ricordati che domani alle...", "Stasera non dimenticare di...".
- Sii breve ma caldo. Se non ci sono impegni per il periodo richiesto, dillo gentilmente.
- Se ci sono impegni passati non completati, accennali come cose da recuperare.
- Non usare mai liste puntate schematiche, scrivi un unico paragrafo fluido e piacevole da leggere.
"""
    try:
        response = await llm_service._call_with_protection(
            "gpt-4o-mini", prompt, message, user_id=user_id, route="reminder"
        )
        return response or "Ecco i tuoi impegni: " + items_text
    except:
        from core.reminder_engine import reminder_engine
        return "Ecco i tuoi impegni:\n" + reminder_engine.format_reminders_list(reminders)
