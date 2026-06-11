"""
GENESI — Meta Messaging Webhook Router (Facebook Messenger + Instagram DM)

GET  /api/messenger/webhook  → verifica challenge Meta
POST /api/messenger/webhook  → riceve messaggi Messenger (object="page")
GET  /api/instagram/webhook  → verifica challenge Meta
POST /api/instagram/webhook  → riceve DM Instagram (object="instagram")

Sicurezza:
- Firma X-Hub-Signature-256 verificata sul body RAW prima del parsing JSON.
  Firma invalida → 403, payload mai processato.
- Il parsing e il processing avvengono in background: Meta riceve sempre
  200 OK entro pochi ms (altrimenti ritenta e disabilita il webhook).
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Request, Response, Query
from fastapi.responses import PlainTextResponse

from core.meta_messaging_bot import handle_update, verify_webhook, verify_signature

logger = logging.getLogger(__name__)
router = APIRouter(tags=["meta-messaging"])


async def _receive(request: Request, platform: str):
    """Gestione comune POST webhook: firma → parse → dispatch background."""
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(body, signature, platform):
        return Response(status_code=403)
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("payload non è un oggetto JSON")
        asyncio.create_task(handle_update(payload, platform))
    except Exception as e:
        logger.error("META_WEBHOOK_PARSE_ERROR platform=%s err=%s body=%.300s",
                     platform, e, body)
    # Meta richiede sempre 200 OK, altrimenti riprova
    return {"status": "ok"}


# ── Facebook Messenger ───────────────────────────────────────────────────────

@router.get("/api/messenger/webhook")
async def messenger_verify(
    hub_mode: str      = Query("", alias="hub.mode"),
    hub_token: str     = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    """Verifica iniziale del webhook Messenger da parte di Meta."""
    challenge = verify_webhook(hub_mode, hub_token, hub_challenge)
    if challenge is not None:
        return PlainTextResponse(challenge)
    return Response(status_code=403)


@router.post("/api/messenger/webhook")
async def messenger_webhook(request: Request):
    """Riceve messaggi Facebook Messenger e li processa in background."""
    return await _receive(request, "messenger")


# ── Instagram DM ─────────────────────────────────────────────────────────────

@router.get("/api/instagram/webhook")
async def instagram_verify(
    hub_mode: str      = Query("", alias="hub.mode"),
    hub_token: str     = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    """Verifica iniziale del webhook Instagram da parte di Meta."""
    challenge = verify_webhook(hub_mode, hub_token, hub_challenge)
    if challenge is not None:
        return PlainTextResponse(challenge)
    return Response(status_code=403)


@router.post("/api/instagram/webhook")
async def instagram_webhook(request: Request):
    """Riceve DM Instagram e li processa in background."""
    return await _receive(request, "instagram")
