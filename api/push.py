# api/push.py
# Router per gestione subscription push e invio notifiche.
# NON modificare altri file API. NON toccare proactor, auth, AI Engineer OS.

import os
import json
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pywebpush import webpush, WebPushException

from auth.router import require_auth
from auth.models import AuthUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/push", tags=["push"])

# ── Config VAPID ──────────────────────────────────────────────
VAPID_PRIVATE_KEY   = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY    = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_CLAIMS_EMAIL  = os.getenv("VAPID_CLAIMS_EMAIL", "admin@genesi.app")

# ── Storage subscription ──────────────────────────────────────
SUBS_DIR = Path("data/push_subscriptions")
SUBS_DIR.mkdir(parents=True, exist_ok=True)


def _sub_path(user_id: str) -> Path:
    return SUBS_DIR / f"{user_id}.json"


def save_subscription(user_id: str, subscription: dict):
    with open(_sub_path(user_id), "w") as f:
        json.dump(subscription, f)
    logger.info(f"PUSH_SUB_SAVED user_id={user_id}")


def load_subscription(user_id: str) -> dict | None:
    p = _sub_path(user_id)
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def delete_subscription(user_id: str):
    p = _sub_path(user_id)
    if p.exists():
        p.unlink()
        logger.info(f"PUSH_SUB_DELETED user_id={user_id}")


# ── Modelli ───────────────────────────────────────────────────
class PushSubscription(BaseModel):
    endpoint : str
    keys     : dict  # {auth: str, p256dh: str}


# ── Route: ottieni public key VAPID ──────────────────────────
@router.get("/vapid-public-key")
async def get_vapid_public_key():
    """Restituisce la public key VAPID per il frontend."""
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=503, detail="VAPID non configurato")
    return JSONResponse({"public_key": VAPID_PUBLIC_KEY})


# ── Route: salva subscription ─────────────────────────────────
@router.post("/subscribe")
async def subscribe(
    sub: PushSubscription,
    user: AuthUser = Depends(require_auth)
):
    user_id = user.id if hasattr(user, 'id') else str(user)
    save_subscription(user_id, sub.dict())
    logger.info(f"PUSH_SUBSCRIBE_OK user_id={user_id}")
    return JSONResponse({"status": "subscribed"})


# ── Route: cancella subscription ─────────────────────────────
@router.delete("/unsubscribe")
async def unsubscribe(
    user: AuthUser = Depends(require_auth)
):
    user_id = user.id if hasattr(user, 'id') else str(user)
    delete_subscription(user_id)
    return JSONResponse({"status": "unsubscribed"})


# ── Funzione pubblica: invia notifica a un utente ─────────────
def send_push_notification(user_id: str, title: str, body: str, data: dict = None):
    """
    Chiamata dal Reminder Engine quando REMINDER_TRIGGERED.
    Non è una route HTTP — è una funzione interna.
    """
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        logger.warning("PUSH_SKIP_NO_VAPID")
        return False

    sub = load_subscription(user_id)
    if not sub:
        logger.info(f"PUSH_SKIP_NO_SUB user_id={user_id}")
        return False

    payload = json.dumps({
        "title"  : title,
        "body"   : body,
        "icon"   : "/static/icon.png",
        "badge"  : "/static/icon.png",
        "data"   : data or {},
        "tag"    : f"reminder-{user_id}",
        "renotify": True,
    })

    try:
        webpush(
            subscription_info=sub,
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={
                "sub": f"mailto:{VAPID_CLAIMS_EMAIL}"
            }
        )
        logger.info(f"PUSH_SENT_OK user_id={user_id} title='{title}'")
        return True

    except WebPushException as e:
        logger.error(f"PUSH_SEND_ERROR user_id={user_id} error={e}")
        # Subscription scaduta o invalida: rimuovila
        if e.response and e.response.status_code in (404, 410):
            delete_subscription(user_id)
            logger.info(f"PUSH_SUB_EXPIRED_REMOVED user_id={user_id}")
        return False
