"""
MEMORY API - Genesi Core v2
API per gestione storage in-memory
1 intent → 1 funzione
"""

from fastapi import APIRouter, HTTPException
from core.memory_storage import memory_storage
from core.log import log

router = APIRouter(prefix="/api")

@router.get("/memory/stats")
async def get_memory_stats():
    """
    Statistiche storage - 1 intent → 1 funzione
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

@router.get("/memory/keys")
async def get_memory_keys():
    """
    Lista chiavi storage - 1 intent → 1 funzione
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

@router.delete("/memory/clear")
async def clear_memory():
    """
    Pulisci storage - 1 intent → 1 funzione
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

@router.get("/memory/exists/{key}")
async def key_exists(key: str):
    """
    Verifica esistenza chiave - 1 intent → 1 funzione
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
