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
from auth.router import require_auth
from auth.models import AuthUser
from datetime import datetime

router = APIRouter(prefix="/chat")

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    status: str
    intent: Optional[str] = None
    user_id: Optional[str] = None

@router.post("/", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, user: AuthUser = Depends(require_auth)):
    try:
        user_id = user.id

        log("API_CHAT", message=request.message[:100], user_id=user_id)

        # Cognitive Memory Evaluation
        cognitive_engine = CognitiveMemoryEngine()
        decision = await cognitive_engine.evaluate_event(user_id, request.message, {})

        # Load profile once for all updates
        raw_profile = await storage.load(f"profile:{user_id}", default={})
        normalized = normalize_profile_dict(raw_profile)
        profile = UserProfile(**normalized)
        profile_changed = False

        # Cognitive memory: explicit identity fields
        if decision['persist']:
            if decision['memory_type'] == 'profile':
                key = decision['key']
                val = decision['value']

                if key == "name":
                    profile.name = val
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

        # Identity extractor: stable interests, preferences, traits
        identity_update = await extract_identity_updates(request.message)
        if identity_update.interests or identity_update.preferences or identity_update.traits:
            merge_identity_update(profile, identity_update)
            profile_changed = True

        # Save profile if any update occurred
        if profile_changed:
            profile.updated_at = datetime.utcnow()
            await storage.save(f"profile:{user_id}", profile.model_dump(mode="json"))
            log("STORAGE_SAVE", key=f"profile:{user_id}")

        response = await simple_chat_handler(request.message, user_id)

        return ChatResponse(
            response=response,
            status="ok",
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
