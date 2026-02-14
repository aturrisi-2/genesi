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

    # Aggiorna last_seen
    user_manager.update_user(user_id, {"last_seen": "now"})

    return {
        "user_id": user_id,
        "profile": user_data.get("preferences", {}),
        "created_at": user_data["created_at"],
        "last_seen": user_data["last_seen"]
    }

