# api/user.py

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import uuid

from core.user_manager import user_manager

router = APIRouter()


class BootstrapRequest(BaseModel):
    user_id: Optional[str] = None


@router.post("/user/bootstrap")
async def bootstrap_user(request: BootstrapRequest):
    """
    Bootstrap = carica stato persistente.
    NON interpreta.
    NON normalizza.
    NON scrive identità.
    """

    if request.user_id:
        user_data = user_manager.get_user(request.user_id)
        if not user_data:
            user_data = user_manager.create_user(request.user_id)
    else:
        # Crea nuovo utente con ID univoco
        new_user_id = str(uuid.uuid4())
        user_data = user_manager.create_user(new_user_id)

    # Aggiorna last_seen
    user_manager.update_user(user_data["user_id"], {"last_seen": "now"})

    return {
        "user_id": user_data["user_id"],
        "profile": user_data.get("preferences", {}),
        "created_at": user_data["created_at"],
        "last_seen": user_data["last_seen"]
    }

