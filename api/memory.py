"""
MEMORY API - Genesi Core v2
API per gestione storage in-memory
1 intent → 1 funzione

SICUREZZA: require_admin su tutti gli endpoint (dati sensibili di sistema).
"""

from fastapi import APIRouter, HTTPException, Depends
from core.memory_storage import memory_storage
from core.log import log
from auth.router import require_admin
from auth.models import AuthUser

router = APIRouter(prefix="/memory")

@router.get("/stats")
async def get_memory_stats(user: AuthUser = Depends(require_admin)):
    """
    Statistiche storage - solo admin
    """
    try:
        stats = memory_storage.get_stats()
        return {
            "status": "ok",
            "storage": "in-memory",
            "stats": stats
        }
        
    except Exception as e:
        log("MEMORY_STATS_ERROR", error=str(e))
        raise HTTPException(status_code=500, detail="Memory stats error")

@router.get("/keys")
async def get_memory_keys(user: AuthUser = Depends(require_admin)):
    """
    Lista chiavi storage - solo admin
    """
    try:
        keys = memory_storage.list_keys()
        return {
            "status": "ok",
            "keys": keys,
            "count": len(keys)
        }
        
    except Exception as e:
        log("MEMORY_KEYS_ERROR", error=str(e))
        raise HTTPException(status_code=500, detail="Memory keys error")

@router.delete("/clear")
async def clear_memory(user: AuthUser = Depends(require_admin)):
    """
    Pulisci storage - solo admin
    """
    try:
        success = memory_storage.clear()
        return {
            "status": "ok",
            "cleared": success
        }
        
    except Exception as e:
        log("MEMORY_CLEAR_ERROR", error=str(e))
        raise HTTPException(status_code=500, detail="Memory clear error")

@router.get("/exists/{key}")
async def key_exists(key: str, user: AuthUser = Depends(require_admin)):
    """
    Verifica esistenza chiave - solo admin
    """
    try:
        exists = memory_storage.exists(key)
        return {
            "key": key,
            "exists": exists
        }
        
    except Exception as e:
        log("MEMORY_EXISTS_ERROR", key=key, error=str(e))
        raise HTTPException(status_code=500, detail="Memory exists error")
