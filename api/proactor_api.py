from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from core.proactor import proactor
from core.log import log
from core.storage import storage
from core.icloud_service import ICloudService
from core.reminder_engine import reminder_engine
from auth.router import require_auth
from auth.models import AuthUser

router = APIRouter(prefix="/proactor")

class ICloudSetupRequest(BaseModel):
    email: str
    password: str

class ICloud2FARequest(BaseModel):
    code: str

@router.get("/icloud/status")
async def get_icloud_status(user: AuthUser = Depends(require_auth)):
    """Ottiene lo stato dell'integrazione iCloud del profilo."""
    try:
        user_id = user.id
        profile = await storage.load(f"profile:{user_id}", default={})
        
        email = profile.get("icloud_user")
        is_verified = profile.get("icloud_verified", False)
        
        # Se configurato, controlliamo se serve 2FA attualmente
        needs_2fa = False
        error_msg = None
        if email:
            password = profile.get("icloud_password")
            svc = ICloudService(username=email, password=password, cookie_directory=f"memory/icloud_sessions/{user_id}")
            try:
                api = svc._get_client()
                if api and api.requires_2fa:
                    needs_2fa = True
                if not api:
                    error_msg = "Impossibile inizializzare il servizio iCloud."
            except Exception as e:
                error_msg = str(e)
        
        return {
            "configured": bool(email),
            "email": email,
            "verified": is_verified,
            "needs_2fa": needs_2fa,
            "error": error_msg,
            "last_sync": profile.get("last_icloud_sync")
        }
    except Exception as e:
        log("ICLOUD_STATUS_API_ERROR", error=str(e))
        return {"error": str(e)}

@router.post("/icloud/setup")
async def setup_icloud(req: ICloudSetupRequest, user: AuthUser = Depends(require_auth)):
    """Configura credenziali iCloud."""
    try:
        user_id = user.id
        profile = await storage.load(f"profile:{user_id}", default={})
        
        profile["icloud_user"] = req.email
        profile["icloud_password"] = req.password
        profile["icloud_verified"] = False # Richiede verifica/2FA
        
        await storage.save(f"profile:{user_id}", profile)
        
        # Tenta inizializzazione per triggerare eventuale 2FA
        svc = ICloudService(username=req.email, password=req.password, cookie_directory=f"memory/icloud_sessions/{user_id}")
        try:
            api = svc._get_client()
            return {
                "status": "ok",
                "needs_2fa": api.requires_2fa if api else False,
                "error": None if api else "Autenticazione fallita (controlla credenziali o 2FA)."
            }
        except Exception as api_e:
            return {
                "status": "error",
                "error": str(api_e)
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/icloud/2fa")
async def validate_icloud_2fa(req: ICloud2FARequest, user: AuthUser = Depends(require_auth)):
    """Invia codice 2FA."""
    try:
        user_id = user.id
        profile = await storage.load(f"profile:{user_id}", default={})
        
        email = profile.get("icloud_user")
        password = profile.get("icloud_password")
        
        svc = ICloudService(username=email, password=password, cookie_directory=f"memory/icloud_sessions/{user_id}")
        success = svc.validate_2fa(req.code)
        
        if success:
            profile["icloud_verified"] = True
            await storage.save(f"profile:{user_id}", profile)
            return {"status": "ok", "message": "Autenticazione completata."}
        else:
            return {"status": "error", "message": "Codice errato o scaduto."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/icloud/sync")
async def sync_icloud(user: AuthUser = Depends(require_auth)):
    """Sincronizza manualmente i promemoria."""
    try:
        user_id = user.id
        # Forza sync ignorando il cooldown
        new_reminders = await reminder_engine.fetch_icloud_reminders(user_id, force=True)
        return {
            "status": "ok",
            "count": len(new_reminders)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
