from fastapi import APIRouter, HTTPException, Depends, Request
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

@router.api_route("/icloud/status", methods=["GET", "DELETE"])
async def handle_icloud_status(user: AuthUser = Depends(require_auth), request: Request = None):
    """Gestisce lo stato o la disconnessione di iCloud."""
    user_id = user.id
    profile = await storage.load(f"profile:{user_id}", default={})
    
    if request.method == "DELETE":
        profile.pop("icloud_user", None)
        profile.pop("icloud_password", None)
        profile.pop("icloud_verified", None)
        await storage.save(f"profile:{user_id}", profile)
        return {"status": "ok", "message": "Account scollegato."}
    
    # GET logic
    email = profile.get("icloud_user")
    is_verified = profile.get("icloud_verified", False)
    return {
        "configured": bool(email),
        "email": email,
        "verified": is_verified,
        "last_sync": profile.get("last_icloud_sync")
    }

@router.post("/icloud/setup")
async def setup_icloud(req: ICloudSetupRequest, user: AuthUser = Depends(require_auth)):
    """Configura credenziali iCloud (CalDAV con Password specifica)."""
    try:
        user_id = user.id
        profile = await storage.load(f"profile:{user_id}", default={})
        
        # Inizializza il servizio per testare la connessione
        svc = ICloudService(username=req.email, password=req.password)
        if svc.validate_credentials():
            profile["icloud_user"] = req.email
            profile["icloud_password"] = req.password
            profile["icloud_verified"] = True
            await storage.save(f"profile:{user_id}", profile)
            
            # Sincronizza subito
            from core.reminder_engine import reminder_engine
            await reminder_engine.fetch_icloud_reminders(user_id, force=True)
            
            return {"status": "ok", "message": "Connessione stabilita con successo."}
        else:
            return {"status": "error", "message": "Credenziali non valide. Assicurati di usare una 'Password specifica per le app'."}
            
    except Exception as e:
        log("ICLOUD_SETUP_ERROR", error=str(e))
        return {"status": "error", "message": str(e)}

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
