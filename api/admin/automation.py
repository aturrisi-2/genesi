"""
ADMIN AUTOMATION API - Genesi

Endpoint per mettere in pausa o riattivare le automazioni proattive senza
modificare manualmente le variabili ambiente.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth.models import AuthUser
from auth.router import require_admin
from core import automation_flags

router = APIRouter(prefix="/admin/automation", tags=["admin-automation"])


class AutomationConfigPayload(BaseModel):
    values: dict[str, bool]


@router.get("/status")
async def automation_status(_: AuthUser = Depends(require_admin)):
    return {
        "registry": automation_flags.registry(),
        "state": automation_flags.snapshot(),
    }


@router.post("/config")
async def automation_config(payload: AutomationConfigPayload, _: AuthUser = Depends(require_admin)):
    return {
        "registry": automation_flags.registry(),
        "state": automation_flags.set_config(payload.values),
    }


@router.post("/reset")
async def automation_reset(_: AuthUser = Depends(require_admin)):
    return {
        "registry": automation_flags.registry(),
        "state": automation_flags.reset_config(),
    }
