# api/user.py
"""
USER API - Genesi Core v2
Bootstrap utente autenticato. user_id estratto SOLO dal JWT.
Nessun bootstrap anonimo. Nessun user_id dal client.
"""

from fastapi import APIRouter, Depends

from core.user_manager import user_manager
from auth.router import require_auth
from auth.models import AuthUser

router = APIRouter(prefix="/user")


@router.post("/bootstrap")
async def bootstrap_user(user: AuthUser = Depends(require_auth)):
    """
    Bootstrap = carica stato persistente per utente autenticato.
    user_id estratto dal JWT. Mai dal client.
    """
    user_id = user.id

    user_data = user_manager.get_user(user_id)
    if not user_data:
        user_data = user_manager.create_user(user_id)

    # Carica profilo persistente da storage per flag di sincronizzazione
    from core.storage import storage
    profile = await storage.load(f"profile:{user_id}", default={})

    # Aggiorna last_seen
    user_manager.update_user(user_id, {"last_seen": "now"})

    return {
        "user_id": user_id,
        "profile": user_data.get("preferences", {}),
        "created_at": user_data["created_at"],
        "last_seen": user_data["last_seen"],
        "sync_status": {
            "google_synced": bool(profile.get("google_token")),
            "icloud_synced": bool(profile.get("icloud_user") and profile.get("icloud_verified")),
            "icloud_dismissed": bool(profile.get("icloud_sync_dismissed", False))
        }
    }


@router.post("/icloud/dismiss")
async def dismiss_icloud_sync(user: AuthUser = Depends(require_auth)):
    """Marca il popup iCloud come ignorato per questo utente."""
    user_id = user.id
    from core.storage import storage
    profile = await storage.load(f"profile:{user_id}", default={})
    profile["icloud_sync_dismissed"] = True
    await storage.save(f"profile:{user_id}", profile)
    return {"status": "ok"}

