"""
GENESI — Telegram Webhook Router
Riceve gli aggiornamenti da Telegram e li gestisce in background.
"""

import asyncio
import logging
from fastapi import APIRouter, Request

from core.telegram_bot import handle_update, get_bot_link

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """Endpoint chiamato da Telegram ad ogni messaggio."""
    try:
        update = await request.json()
        asyncio.create_task(handle_update(update))
    except Exception as e:
        logger.error("TELEGRAM_WEBHOOK_ERROR err=%s", e)
    return {"ok": True}


@router.get("/bot-link")
async def telegram_bot_link():
    """Ritorna il link diretto al bot Telegram (usato dalla webapp dopo la registrazione)."""
    return {"bot_link": get_bot_link()}
