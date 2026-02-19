"""
Notifications API - Genesi Core
Endpoint per notifiche push reminder e altre notifiche utente
"""

from fastapi import APIRouter, Depends, Request
from auth.models import AuthUser
from auth.router import require_auth
from core.reminder_engine import reminder_engine
from core.log import log

router = APIRouter()

@router.get("/api/notifications/pending")
async def get_pending_notifications(current_user: AuthUser = Depends(require_auth)):
    """Ritorna notifiche reminder triggered non ancora lette dall'utente."""
    user_id = str(current_user.id)
    
    try:
        triggered = reminder_engine.list_reminders(user_id, status_filter="triggered")
        
        notifications = [
            {
                "type": "reminder",
                "text": r["text"],
                "triggered_at": r.get("triggered_at"),
                "id": r["id"]
            }
            for r in triggered
        ]
        
        log("NOTIFICATIONS_PENDING", user_id=user_id, count=len(notifications))
        return {"notifications": notifications, "count": len(notifications)}
        
    except Exception as e:
        log("NOTIFICATIONS_ERROR", user_id=user_id, error=str(e))
        return {"notifications": [], "count": 0}
