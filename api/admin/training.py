"""
TRAINING ADMIN API — Genesi Training System
Endpoint REST per il cruscotto di training (solo admin).
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth.router import require_admin
from auth.models import AuthUser
from core.capability_tracker import capability_tracker
from core.training_engine import training_engine
from core.training_autopilot import autopilot as training_autopilot
from core.storage import storage

logger = logging.getLogger(__name__)

# ── Adaptive training config ──────────────────────────────────────────────────
_SCRIPT_PATH          = Path(__file__).parent.parent.parent / "scripts" / "training_marathon.py"
_ADAPTIVE_STATUS_KEY  = "admin/adaptive_training_status"
TRAINING_USER_EMAIL   = os.getenv("TRAINING_USER_EMAIL",    "alfio.turrisi@gmail.com")
TRAINING_USER_PWD     = os.getenv("TRAINING_USER_PASSWORD", "ZOEennio0810")
TRAINING_ADMIN_EMAIL  = os.getenv("TRAINING_ADMIN_EMAIL",   "idappleturrisi@gmail.com")
TRAINING_ADMIN_PWD    = os.getenv("TRAINING_ADMIN_PASSWORD","ZOEennio0810")

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
    current   = await capability_tracker.compute_current()
    history   = await capability_tracker.get_history(days=days)
    counters  = await capability_tracker.get_counters(days=days)
    stats     = await training_engine.get_stats()
    autopilot = await training_autopilot.get_status()

    # Predictive engine: lettura leggera (solo storage scan, nessun LLM)
    from pathlib import Path as _Path
    import json as _json
    _pred_dir = _Path("memory/predictions")
    _pred_users = []
    if _pred_dir.exists():
        for _pf in _pred_dir.glob("*.json"):
            try:
                _d = _json.loads(_pf.read_text(encoding="utf-8"))
                _tot = _d.get("total_assessments", 0)
                _hist = _d.get("accuracy_history", [])
                _acc  = sum(_hist) / len(_hist) if _hist else 0.0
                _pred_users.append({"shadow": _tot < 12, "acc": _acc, "total": _tot})
            except Exception:
                pass
    _active_pp = [u for u in _pred_users if not u["shadow"]]
    predictive = {
        "total_users":  len(_pred_users),
        "active_users": len(_active_pp),
        "shadow_users": len(_pred_users) - len(_active_pp),
        "avg_accuracy": round(sum(u["acc"] for u in _active_pp) / len(_active_pp), 3)
                        if _active_pp else 0.0,
    }

    return {
        "current":    current,
        "history":    history,
        "counters":   counters,
        "stats":      stats,
        "autopilot":  autopilot,
        "predictive": predictive,
    }


@router.post("/metrics/snapshot")
async def save_snapshot(user: AuthUser = Depends(require_admin)):
    """Forza salvataggio snapshot manuale."""
    await capability_tracker.save_snapshot()
    return {"ok": True, "message": "Snapshot salvato"}


@router.get("/autopilot-status")
async def get_autopilot_status(user: AuthUser = Depends(require_admin)):
    """Stato corrente dell'autopilot."""
    return await training_autopilot.get_status()


@router.post("/autopilot-tick")
async def force_autopilot_tick(user: AuthUser = Depends(require_admin)):
    """Forza un tick immediato dell'autopilot (gestione lessons + check training)."""
    asyncio.create_task(training_autopilot._tick())
    return {"ok": True, "message": "Autopilot tick avviato"}


@router.get("/predictive-overview")
async def get_predictive_overview(user: AuthUser = Depends(require_admin)):
    """
    Statistiche aggregate del Predictive Processing Engine.
    Scansiona tutti i file predictions:* in storage e aggrega i dati.
    """
    from pathlib import Path
    import json as _json

    pred_dir = Path("memory/predictions")
    users_data = []

    if pred_dir.exists():
        for f in pred_dir.glob("*.json"):
            try:
                raw = _json.loads(f.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    continue
                total   = raw.get("total_assessments", 0)
                history = raw.get("accuracy_history", [])
                avg_acc = sum(history) / len(history) if history else 0.0
                users_data.append({
                    "user_id":       f.stem,
                    "total":         total,
                    "shadow_mode":   total < 12,
                    "avg_accuracy":  round(avg_acc, 3),
                    "last_surprise": raw.get("last_surprise_score"),
                    "last_pred":     raw.get("next_turn_prediction", "")[:100],
                    "updated_at":    raw.get("prediction_updated_at"),
                })
            except Exception:
                pass

    active  = [u for u in users_data if not u["shadow_mode"]]
    shadow  = [u for u in users_data if u["shadow_mode"]]
    avg_all = (
        sum(u["avg_accuracy"] for u in active) / len(active)
        if active else 0.0
    )
    # Ultime 3 predizioni più recenti
    recent_preds = sorted(
        [u for u in users_data if u["last_pred"]],
        key=lambda x: x.get("updated_at") or "",
        reverse=True
    )[:3]

    return {
        "total_users":       len(users_data),
        "active_users":      len(active),
        "shadow_users":      len(shadow),
        "avg_accuracy":      round(avg_all, 3),
        "recent_predictions": recent_preds,
        "all_users":          sorted(users_data, key=lambda x: -x["total"]),
    }


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


# ═══════════════════════════════════════════════════════
#  ADAPTIVE TRAINING
# ═══════════════════════════════════════════════════════

@router.get("/adaptive-status")
async def get_adaptive_status(user: AuthUser = Depends(require_admin)):
    """Stato attuale dell'allenamento adattivo (idle/running/completed/failed)."""
    data = await storage.load(_ADAPTIVE_STATUS_KEY, default={"status": "idle"})
    # Se running, verifica che il PID sia ancora vivo
    if data.get("status") == "running":
        pid = data.get("pid")
        if pid:
            try:
                os.kill(pid, 0)
            except (ProcessLookupError, OSError):
                data["status"] = "failed"
                data["error"]  = "Processo terminato inaspettatamente"
                await storage.save(_ADAPTIVE_STATUS_KEY, data)
    return data


@router.post("/adaptive-run")
async def start_adaptive_run(
    top_n:       int  = Query(3, ge=1, le=6,  description="Quante categorie deboli allenare"),
    auto_lesson: bool = Query(True,            description="Attiva auto-lesson sui fallimenti"),
    pause:       float= Query(4.0, ge=1, le=15,description="Pausa tra messaggi (secondi)"),
    user: AuthUser = Depends(require_admin),
):
    """
    Analizza le categorie più deboli dalle corrections, poi lancia il marathon
    filtrato su quelle categorie in background.
    """
    # Check: processo già in corso?
    current = await storage.load(_ADAPTIVE_STATUS_KEY, default={})
    if current.get("status") == "running":
        pid = current.get("pid")
        if pid:
            try:
                os.kill(pid, 0)
                return {"ok": False, "error": "Allenamento già in corso", "status": current}
            except (ProcessLookupError, OSError):
                pass  # Processo morto → consenti restart

    # Identifica categorie deboli
    weak = await training_engine.get_weak_categories(top_n=top_n)
    cat_names     = [w["category"] for w in weak]
    categories_str = ",".join(cat_names)

    # Costruisci comando
    cmd = [
        sys.executable, str(_SCRIPT_PATH),
        "--email",          TRAINING_USER_EMAIL,
        "--password",       TRAINING_USER_PWD,
        "--admin-email",    TRAINING_ADMIN_EMAIL,
        "--admin-password", TRAINING_ADMIN_PWD,
        "--categories",     categories_str,
        "--pause",          str(pause),
    ]
    if auto_lesson:
        cmd.append("--auto-lesson")

    # Stato iniziale
    status_doc = {
        "status":       "starting",
        "started_at":   datetime.utcnow().isoformat(),
        "categories":   cat_names,
        "weak_analysis": weak,
        "auto_lesson":  auto_lesson,
        "output_lines": [],
        "pid":          None,
    }
    await storage.save(_ADAPTIVE_STATUS_KEY, status_doc)

    # Avvia in background (non bloccante)
    asyncio.create_task(_run_adaptive_subprocess(cmd, status_doc))

    logger.info("ADAPTIVE_TRAINING_STARTED categories=%s", cat_names)
    return {
        "ok":          True,
        "categories":  cat_names,
        "weak":        weak,
        "message":     f"Allenamento adattivo avviato su: {', '.join(cat_names)}",
    }


async def _run_adaptive_subprocess(cmd: list, status_doc: dict):
    """Task background: esegue il marathon, aggiorna lo status file in tempo reale."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        status_doc["status"] = "running"
        status_doc["pid"]    = proc.pid
        await storage.save(_ADAPTIVE_STATUS_KEY, status_doc)

        output_lines = []
        save_tick    = 0
        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            output_lines.append(line)
            if len(output_lines) > 100:
                output_lines = output_lines[-100:]
            save_tick += 1
            if save_tick % 8 == 0:
                status_doc["output_lines"] = output_lines
                await storage.save(_ADAPTIVE_STATUS_KEY, status_doc)

        await proc.wait()
        status_doc.update({
            "status":       "completed" if proc.returncode == 0 else "failed",
            "returncode":   proc.returncode,
            "completed_at": datetime.utcnow().isoformat(),
            "output_lines": output_lines,
        })
        await storage.save(_ADAPTIVE_STATUS_KEY, status_doc)
        logger.info("ADAPTIVE_TRAINING_DONE returncode=%s cats=%s",
                    proc.returncode, status_doc.get("categories"))

    except Exception as exc:
        logger.error("ADAPTIVE_TRAINING_ERROR err=%s", exc)
        status_doc.update({
            "status":       "failed",
            "error":        str(exc),
            "completed_at": datetime.utcnow().isoformat(),
        })
        await storage.save(_ADAPTIVE_STATUS_KEY, status_doc)
