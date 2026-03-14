"""
TRAINING ADMIN API — Genesi Training System
Endpoint REST per il cruscotto di training (solo admin).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth.router import require_admin
from auth.models import AuthUser
from core.capability_tracker import capability_tracker
from core.training_engine import training_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/training", tags=["admin-training"])


# ═══════════════════════════════════════════════════════
#  METRICS
# ═══════════════════════════════════════════════════════

@router.get("/metrics")
async def get_metrics(
    days: int = Query(30, ge=1, le=90),
    user: AuthUser = Depends(require_admin),
):
    """Metriche correnti + storico N giorni."""
    current = await capability_tracker.compute_current()
    history = await capability_tracker.get_history(days=days)
    counters = await capability_tracker.get_counters(days=days)
    return {
        "current":  current,
        "history":  history,
        "counters": counters,
    }


@router.post("/metrics/snapshot")
async def save_snapshot(user: AuthUser = Depends(require_admin)):
    """Forza salvataggio snapshot manuale."""
    await capability_tracker.save_snapshot()
    return {"ok": True, "message": "Snapshot salvato"}


# ═══════════════════════════════════════════════════════
#  CORRECTIONS
# ═══════════════════════════════════════════════════════

class CorrectionCreate(BaseModel):
    input_message:    str
    bad_response:     str
    correct_response: str
    category:         str  = "altro"
    admin_note:       str  = ""
    user_id:          str  = ""


@router.get("/corrections")
async def list_corrections(
    category: Optional[str] = Query(None),
    user: AuthUser = Depends(require_admin),
):
    corrections = await training_engine.get_corrections(category=category)
    stats       = await training_engine.get_stats()
    return {"corrections": corrections, "stats": stats}


@router.post("/corrections")
async def add_correction(
    body: CorrectionCreate,
    user: AuthUser = Depends(require_admin),
):
    correction = await training_engine.add_correction(
        input_message=body.input_message,
        bad_response=body.bad_response,
        correct_response=body.correct_response,
        category=body.category,
        admin_note=body.admin_note,
        user_id=body.user_id,
    )
    return {"ok": True, "correction": correction}


@router.delete("/corrections/{correction_id}")
async def delete_correction(
    correction_id: str,
    user: AuthUser = Depends(require_admin),
):
    ok = await training_engine.delete_correction(correction_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Correzione non trovata")
    return {"ok": True}


@router.patch("/corrections/{correction_id}/lesson")
async def toggle_lesson(
    correction_id: str,
    active: bool   = Query(...),
    user: AuthUser = Depends(require_admin),
):
    """Attiva/disattiva una correction come few-shot lesson."""
    ok = await training_engine.toggle_lesson(correction_id, active)
    if not ok:
        raise HTTPException(status_code=404, detail="Correzione non trovata")
    return {"ok": True, "active": active}


# ═══════════════════════════════════════════════════════
#  LESSONS
# ═══════════════════════════════════════════════════════

@router.get("/lessons")
async def list_lessons(user: AuthUser = Depends(require_admin)):
    """Lista lessons attive (subset delle corrections)."""
    lessons = await training_engine.get_active_lessons()
    return {"lessons": lessons, "count": len(lessons)}
