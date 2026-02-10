"""
PROACTOR API - Genesi Core v2
API per gestione Proactor e statistiche motori
"""

from fastapi import APIRouter, HTTPException
from core.proactor import proactor
from core.log import log

router = APIRouter(prefix="/proactor")

@router.get("/stats")
async def get_proactor_stats():
    """
    Statistiche Proactor - 1 intent → 1 funzione
    """
    try:
        stats = proactor.get_engine_stats()
        return {
            "status": "ok",
            "proactor": "active",
            "engines": stats
        }
        
    except Exception as e:
        log("PROACTOR_STATS_ERROR", error=str(e))
        raise HTTPException(status_code=500, detail="Proactor stats error")

@router.get("/decision/{intent}")
async def get_engine_decision(intent: str, message: str = ""):
    """
    Decisione motore per intent - 1 intent → 1 funzione
    """
    try:
        engine = proactor.decide_engine(intent, message)
        return {
            "intent": intent,
            "message": message,
            "engine": engine
        }
        
    except Exception as e:
        log("PROACTOR_DECISION_ERROR", intent=intent, error=str(e))
        raise HTTPException(status_code=500, detail="Proactor decision error")
