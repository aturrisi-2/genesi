"""
ADMIN CAPABILITY GAPS — Genesi
Endpoint per visualizzare il taccuino virtuale dei gap di capacità
e generare proposte di integrazione via LLM.
"""

from fastapi import APIRouter, Depends
from auth.router import require_admin
from auth.models import AuthUser
from core.capability_awareness import get_gaps_summary, generate_proposals

router = APIRouter(prefix="/admin/capability-gaps", tags=["admin-capability"])


@router.get("")
async def list_gaps(_: AuthUser = Depends(require_admin)):
    """Ritorna il sommario dei gap rilevati (taccuino virtuale)."""
    return await get_gaps_summary()


@router.post("/generate-proposals")
async def propose_integrations(_: AuthUser = Depends(require_admin)):
    """Genera proposte di integrazione basate sui gap registrati."""
    from core.llm_service import llm_service
    return await generate_proposals(llm_service)
