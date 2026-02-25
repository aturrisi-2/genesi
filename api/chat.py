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

router = APIRouter(prefix="/chat")

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    status: str
    intent: Optional[str] = None
    user_id: Optional[str] = None
    tts_text: Optional[str] = None

# Anti-bounce per evitare invii doppi
LAST_MESSAGES = {}

@router.post("", response_model=ChatResponse)
@router.post("/", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, user: AuthUser = Depends(require_auth)):
    try:
        user_id = user.id
        
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

        # Identity extractor: stable interests, preferences, traits, pets, children, spouse
        history = chat_memory.get_messages(user_id, limit=3) if user_id else []
        history_text = "\n".join([f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in history])
        identity_update = await extract_identity_updates(request.message, history_text)
        
        if identity_update.interests or identity_update.preferences or \
           identity_update.traits or identity_update.pets or \
           identity_update.children or identity_update.spouse:
            merge_identity_update(profile, identity_update)
            profile_changed = True

        # Save profile if any update occurred
        if profile_changed:
            profile.updated_at = datetime.utcnow()
            await storage.save(f"profile:{user_id}", profile.model_dump(mode="json"))
            log("STORAGE_SAVE", key=f"profile:{user_id}")

        # 2. Pipeline Relazionale / Tecnico (Orchestrata dal Proactor)
        response = await simple_chat_handler(user_id, request.message, request.conversation_id)
        
        # Defensive normalization: ensure response is always a string
        if isinstance(response, tuple):
            response = response[0]
        if not isinstance(response, str):
            response = str(response)
        
        # Use 'multi' for general emoji enrichment as we now support multiple intents
        intent = "multi"
        
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

        return ChatResponse(
            response=response,
            status="ok",
            intent=intent,
            user_id=user_id,
            tts_text=tts_text
        )

    except Exception as e:
        log("API_CHAT_ERROR", error=str(e), user_id=user.id if user else "unknown")
        raise HTTPException(status_code=500, detail="Chat error")

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
