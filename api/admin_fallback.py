"""
ADMIN FALLBACK API - Monitoring and Improvement tool
Espone i fallback del sistema per l'analisi tecnica.
"""

from fastapi import APIRouter, Header, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import io
import csv
import os
import json
import uuid
from datetime import datetime

from core.fallback_engine import fallback_engine
from core.log import log
from auth.router import require_admin
from auth.models import AuthUser

SUGGESTIONS_PATH = "memory/admin/suggestions.json"

router = APIRouter(prefix="/admin/fallbacks", tags=["admin"])

# Nota: per ora usiamo get_current_user, ma in futuro potremmo aggiungere un check is_admin
# Per semplicità in questa fase, chiunque sia loggato può vedere i fallback (se ha token).

@router.get("/summary")
async def get_fallback_summary(user: AuthUser = Depends(require_admin)):
    """Raggruppa fallbacks per eventi simili."""
    summary = fallback_engine.get_summary()
    return {"total_groups": len(summary), "groups": summary}

@router.get("/raw")
async def get_raw_fallbacks(user: AuthUser = Depends(require_admin), limit: int = 100):
    """Lista completa degli ultimi eventi registrati."""
    events = fallback_engine.get_all_raw()
    # Ritorna gli ultimi 'limit' eventi
    return {"total": len(events), "events": sorted(events, key=lambda x: x["timestamp"], reverse=True)[:limit]}

@router.get("/download")
async def download_fallbacks_csv(user: AuthUser = Depends(require_admin)):
    """Esporta tutti i fallback in formato CSV per analisi esterna."""
    events = fallback_engine.get_all_raw()
    
    if not events:
        raise HTTPException(status_code=404, detail="Nessun fallback registrato.")

    # Crea buffer in memoria per il CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id", "timestamp", "user_id", "user_message", "response_given", "fallback_type", "reason", "group_key", "possible_solution"])
    writer.writeheader()
    writer.writerows(events)
    
    output.seek(0)
    
    filename = f"genesi_fallbacks_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8-sig')), 
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.post("/clear")
async def clear_all_logs(user: AuthUser = Depends(require_admin)):
    """Pulisce la cronologia dei fallback."""
    fallback_engine.clear_logs()
    return {"status": "success", "message": "Log dei fallback eliminati."}


# ─── ADMIN SUGGESTIONS ────────────────────────────────────────────────────────

class SuggestionRequest(BaseModel):
    content: str
    category: str = "generale"        # "prompt" | "memoria" | "tool" | "generale"
    fallback_event_id: Optional[str] = None

def _load_suggestions() -> list:
    if not os.path.exists(SUGGESTIONS_PATH):
        return []
    try:
        with open(SUGGESTIONS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def _save_suggestions(items: list) -> None:
    os.makedirs(os.path.dirname(SUGGESTIONS_PATH), exist_ok=True)
    with open(SUGGESTIONS_PATH, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

@router.post("/suggestions")
async def submit_suggestion(req: SuggestionRequest, user: AuthUser = Depends(require_admin)):
    """Salva un suggerimento di miglioramento inserito dall'admin."""
    if not req.content or not req.content.strip():
        raise HTTPException(status_code=400, detail="Contenuto vuoto.")
    entry = {
        "id": str(uuid.uuid4())[:8],
        "timestamp": datetime.utcnow().isoformat(),
        "content": req.content.strip(),
        "category": req.category,
        "fallback_event_id": req.fallback_event_id,
        "status": "pending",
        "submitted_by": user.id,
    }
    items = _load_suggestions()
    items.append(entry)
    _save_suggestions(items)
    log("ADMIN_SUGGESTION_SAVED", category=req.category, id=entry["id"])
    return {"status": "ok", "id": entry["id"]}

@router.get("/suggestions")
async def get_suggestions(user: AuthUser = Depends(require_admin)):
    """Restituisce tutti i suggerimenti inviati dall'admin."""
    items = _load_suggestions()
    return {"total": len(items), "suggestions": sorted(items, key=lambda x: x["timestamp"], reverse=True)}

@router.delete("/suggestions/{suggestion_id}")
async def delete_suggestion(suggestion_id: str, user: AuthUser = Depends(require_admin)):
    """Elimina un suggerimento per ID."""
    items = _load_suggestions()
    new_items = [s for s in items if s.get("id") != suggestion_id]
    if len(new_items) == len(items):
        raise HTTPException(status_code=404, detail="Suggerimento non trovato.")
    _save_suggestions(new_items)
    return {"status": "ok"}
