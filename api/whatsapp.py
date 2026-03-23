"""
GENESI — WhatsApp Webhook Router (Meta Business Cloud API)

GET  /api/whatsapp/webhook  → verifica challenge Meta
POST /api/whatsapp/webhook  → riceve messaggi in ingresso
"""

import asyncio
import logging
from fastapi import APIRouter, Request, Response, Query
from fastapi.responses import PlainTextResponse

from core.whatsapp_bot import handle_update, verify_webhook, get_wa_link

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


@router.get("/webhook")
async def whatsapp_verify(
    hub_mode: str      = Query("", alias="hub.mode"),
    hub_token: str     = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    """Verifica iniziale del webhook da parte di Meta."""
    challenge = verify_webhook(hub_mode, hub_token, hub_challenge)
    if challenge is not None:
        return PlainTextResponse(challenge)
    return Response(status_code=403)


@router.post("/webhook")
async def whatsapp_webhook(request: Request):
    """Riceve aggiornamenti da WhatsApp e li processa in background."""
    try:
        payload = await request.json()
        asyncio.create_task(handle_update(payload))
    except Exception as e:
        logger.error("WA_WEBHOOK_ERROR err=%s", e)
    # Meta richiede sempre 200 OK, altrimenti riprova
    return {"status": "ok"}


@router.get("/wa-link")
async def whatsapp_link():
    """Ritorna il link diretto alla chat WhatsApp (usato dalla webapp dopo login/registrazione)."""
    return {"wa_link": get_wa_link()}
