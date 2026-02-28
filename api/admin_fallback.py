"""
ADMIN FALLBACK API - Monitoring and Improvement tool
Espone i fallback del sistema per l'analisi tecnica.
"""

from fastapi import APIRouter, Header, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from typing import List, Optional
import io
import csv
from datetime import datetime

from core.fallback_engine import fallback_engine
from auth.router import get_current_user
from auth.models import User

router = APIRouter(prefix="/admin/fallbacks", tags=["admin"])

# Nota: per ora usiamo get_current_user, ma in futuro potremmo aggiungere un check is_admin
# Per semplicità in questa fase, chiunque sia loggato può vedere i fallback (se ha token).

@router.get("/summary")
async def get_fallback_summary(user: User = Depends(get_current_user)):
    """Raggruppa fallbacks per eventi simili."""
    summary = fallback_engine.get_summary()
    return {"total_groups": len(summary), "groups": summary}

@router.get("/raw")
async def get_raw_fallbacks(user: User = Depends(get_current_user), limit: int = 100):
    """Lista completa degli ultimi eventi registrati."""
    events = fallback_engine.get_all_raw()
    # Ritorna gli ultimi 'limit' eventi
    return {"total": len(events), "events": sorted(events, key=lambda x: x["timestamp"], reverse=True)[:limit]}

@router.get("/download")
async def download_fallbacks_csv(user: User = Depends(get_current_user)):
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
async def clear_all_logs(user: User = Depends(get_current_user)):
    """Pulisce la cronologia dei fallback."""
    fallback_engine.clear_logs()
    return {"status": "success", "message": "Log dei fallback eliminati."}
