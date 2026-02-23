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

@router.get("/notifications/pending")
async def get_pending_notifications(current_user: AuthUser = Depends(require_auth)):
    """Ritorna notifiche reminder triggered non ancora lette dall'utente."""
    user_id = str(current_user.id)
    
    try:
        triggered = await reminder_engine.list_reminders(user_id, status_filter="triggered")
        
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

@router.post("/notifications/ack/{reminder_id}")
async def ack_notification(
    reminder_id: str,
    current_user: AuthUser = Depends(require_auth)
):
    """Marca una notifica reminder come letta (status done)."""
    user_id = str(current_user.id)
    
    try:
        reminder_engine.mark_reminder_done(user_id, reminder_id)
        log("REMINDER_ACK", user_id=user_id, reminder_id=reminder_id)
        return {"status": "ok"}
        
    except Exception as e:
        log("REMINDER_ACK_ERROR", user_id=user_id, reminder_id=reminder_id, error=str(e))
        return {"status": "error", "error": str(e)}
