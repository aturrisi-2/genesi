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
from core.simple_chat import simple_chat_handler
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

router = APIRouter(prefix="/chat")

MAX_MESSAGE_LENGTH = 4000  # caratteri massimi per messaggio

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None

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

        # Episode extractor: estrae eventi personali temporali in BACKGROUND
        async def _extract_and_save_episode():
            try:
                from core.episode_extractor import extract_episodes
                from core.episode_memory import episode_memory as _em
                episodes = await extract_episodes(request.message, user_id)
                for ep in episodes:
                    await _em.add(user_id, ep)
                    log("EPISODE_SAVED", user_id=user_id, text=ep['text'][:60])
            except Exception as _ep_e:
                log("EPISODE_SAVE_ERROR", user_id=user_id, error=str(_ep_e))

        _asyncio.create_task(_extract_and_save_episode())

        # 2. Pipeline Relazionale / Tecnico (Orchestrata dal Proactor)
        _handler_result = await simple_chat_handler(user_id, request.message, request.conversation_id)
        if isinstance(_handler_result, tuple):
            response, classified_intent = _handler_result[0], _handler_result[1]
        else:
            response, classified_intent = _handler_result, "chat_free"

        # Identity extractor: gira DOPO simple_chat_handler per evitare race condition
        # con _handle_memory_correction (che salva il profilo dentro simple_chat_handler).
        _asyncio.create_task(_extract_and_save_identity())

        # Defensive normalization: ensure response is always a string
        if not isinstance(response, str):
            response = str(response)

        # Consolidazione memoria globale in background (max 1 volta/24h per utente)
        try:
            from core.global_memory_service import global_memory_service
            import asyncio as _aio_mem
            _aio_mem.create_task(global_memory_service.consolidate_if_needed(user_id))
        except Exception:
            pass

        # Personal facts extraction: fatti rivelati in conversazione (abitudini, preferenze, familiari...)
        _raw_response = response
        async def _extract_and_save_personal_facts():
            try:
                from core.personal_facts_service import personal_facts_service as _pfs
                await _pfs.extract_and_save(request.message, _raw_response, user_id)
            except Exception as _pf_e:
                log("PERSONAL_FACTS_SAVE_ERROR", user_id=user_id, error=str(_pf_e))
        _asyncio.create_task(_extract_and_save_personal_facts())

        # Audit automatico ogni 25 turni di chat (background, silenzioso)
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
                if _count % 25 == 0:
                    log("AUDIT_AUTO_TRIGGER", turn=_count, user_id=user_id)
                    await _auditor.generate_report()
            except Exception:
                pass
        _asyncio.create_task(_maybe_audit())

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
    from core.simple_chat import simple_chat_handler as _sch

    user_id = user.id
    queue: _aio.Queue = _aio.Queue()

    async def _run_pipeline():
        try:
            resp = await _sch(user_id, request.message, request.conversation_id)
            if isinstance(resp, tuple):
                resp = resp[0]
            if not isinstance(resp, str):
                resp = str(resp)
            # Consolidazione memoria globale in background (max 1/24h per utente)
            try:
                from core.global_memory_service import global_memory_service
                _aio.create_task(global_memory_service.consolidate_if_needed(user_id))
            except Exception:
                pass
            # Episode extractor in background (eventi personali temporali)
            async def _stream_extract_episode():
                try:
                    from core.episode_extractor import extract_episodes
                    from core.episode_memory import episode_memory as _em
                    episodes = await extract_episodes(request.message, user_id)
                    for ep in episodes:
                        await _em.add(user_id, ep)
                        log("EPISODE_SAVED", user_id=user_id, text=ep['text'][:60])
                except Exception as _ep_e:
                    log("EPISODE_SAVE_ERROR", user_id=user_id, error=str(_ep_e))
            _aio.create_task(_stream_extract_episode())
            # Personal facts extraction in background (abitudini, preferenze, familiari...)
            _stream_resp = resp
            async def _stream_extract_personal_facts():
                try:
                    from core.personal_facts_service import personal_facts_service as _pfs
                    await _pfs.extract_and_save(request.message, _stream_resp, user_id)
                except Exception as _pf_e:
                    log("PERSONAL_FACTS_SAVE_ERROR", user_id=user_id, error=str(_pf_e))
            _aio.create_task(_stream_extract_personal_facts())

            # Audit automatico ogni 25 turni di chat (background, silenzioso)
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
                    if _count % 25 == 0:
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
