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

@router.post("", response_model=ChatResponse)
@router.post("/", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, user: AuthUser = Depends(require_auth)):
    try:
        user_id = user.id

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
        normalized = normalize_profile_dict(raw_profile)
        profile = UserProfile(**normalized)
        profile_changed = False

        # Cognitive memory: explicit identity fields
        if decision.get('persist'):
            if decision.get('memory_type') == 'profile':
                key = decision['key']
                val = decision['value']

                if key == "name":
                    profile.name = val
                elif key == "city":
                    # City is not in UserProfile model, save in raw dict
                    raw_profile["city"] = val
                    profile_changed = True
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

        # Deterministic Reminder Creation Handler (Smarter Version)
        intent = intent_classifier.classify(request.message)
        if intent == "reminder_create":
            from core.icloud_reminder_creator import ICloudReminderCreator
            import re, os, dateparser
            from dateparser.search import search_dates
            
            # 1. Trova la data nel messaggio usando dateparser.search (molto più robusto della regex)
            found = search_dates(request.message, languages=['it'], settings={'PREFER_DATES_FROM': 'future'})
            
            title = None
            due_date = None
            
            if found:
                # Prendiamo l'ultima data trovata (di solito la più specifica)
                date_text, due_date = found[-1]
                
                # 2. Estrai il titolo pulendo il messaggio
                title = request.message
                # Rimuovi la parte della data trovata
                title = title.replace(date_text, "")
                # Rimuovi verbi e keywords comuni (case-insensitive)
                keywords = [
                    "aggiungi", "metti", "crea", "un", "promemoria", "ricorda", "ricordami", 
                    "di", "per", "il", "a", "alle", "ai", "al"
                ]
                for kw in keywords:
                    title = re.sub(rf'(?i)\b{kw}\b', '', title)
                
                # Pulizia finale
                title = re.sub(r'[:\-]', '', title).strip()
            
            if title and due_date:
                # Se il titolo è rimasto vuoto o troppo corto per errore di pulizia, usa il messaggio originale troncato
                if len(title) < 2:
                    title = request.message.split(":")[1].strip() if ":" in request.message else request.message
                
                # Credenziali
                user_creds = raw_profile.get('icloud_user') or os.environ.get("ICLOUD_USER")
                pass_creds = raw_profile.get('icloud_password') or os.environ.get("ICLOUD_PASSWORD")
                
                if user_creds and pass_creds:
                    creator = ICloudReminderCreator(user=user_creds, password=pass_creds)
                    success = await creator.create_reminder(title, due_date)
                    
                    if success:
                        response = f"✅ Promemoria creato su iCloud: '{title}' per {due_date.strftime('%d/%m %H:%M')}"
                        # Log locale per persistenza
                        from core.reminder_engine import reminder_engine
                        reminder_engine.create_reminder(user_id, title, due_date)
                        chat_memory.add_message(user_id, request.message, response, intent)
                    else:
                        response = f"❌ Errore durante la creazione su iCloud. Ho comunque salvato il promemoria localmente: '{title}'"
                        from core.reminder_engine import reminder_engine
                        reminder_engine.create_reminder(user_id, title, due_date)
                else:
                    response = "❌ Account iCloud non configurato. Non posso salvare il promemoria online."
            else:
                # Fallback al Proactor se il parsing fallisce
                response = await simple_chat_handler(user_id, request.message, request.conversation_id)
        else:
            response = await simple_chat_handler(user_id, request.message, request.conversation_id)
        
        # Defensive normalization: ensure response is always a string
        if isinstance(response, tuple):
            response = response[0]
        if not isinstance(response, str):
            response = str(response)
        
        # Get intent for emoji enrichment
        intent = intent_classifier.classify(request.message)
        
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

        return ChatResponse(
            response=response,
            status="ok",
            intent=intent,
            user_id=user_id
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
