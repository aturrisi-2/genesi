# api/user.py

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from core.user import User
from storage.users import load_user, save_user, create_user as create_storage_user

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
        user = load_user(request.user_id)
        if not user:
            user = User(user_id=request.user_id)
    else:
        user = create_storage_user()

    # solo touch temporale
    user.touch()

    save_user(user)

    return {
        "user_id": user.user_id,
        "profile": user.profile or {},
        "created_at": user.created_at,
        "last_seen": user.last_seen
    }

