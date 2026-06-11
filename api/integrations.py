"""
INTEGRATIONS API - Genesi Core v2
Router per la gestione delle integrazioni esterne (Gmail, Telegram, Facebook, ecc.)

ISOLAMENTO UTENTI:
  - Ogni endpoint autenticato usa user.id dal JWT (mai dal body).
  - I token sono salvati per chiave integration:{platform}:{user_id} → separati per utente.
  - Il webhook Telegram risolve chat_id → user_id prima di processare qualsiasi messaggio.

Endpoints:
  GET    /api/integrations/status                → stato di tutte le integrazioni
  GET    /api/integrations/telegram/link-token   → genera token per collegare il bot
  GET    /api/integrations/{platform}/connect    → avvia OAuth (redirect)
  GET    /api/integrations/{platform}/callback   → callback OAuth
  DELETE /api/integrations/{platform}/disconnect → revoca
  POST   /api/integrations/telegram/webhook      → webhook pubblico Telegram (no auth)
"""

import asyncio
import os
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from auth.models import AuthUser
from auth.router import require_auth
from core.integrations import integrations_registry
from core.log import log

router = APIRouter(prefix="/integrations", tags=["integrations"])

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


# ─── Helper: pagine HTML di conferma (stesso stile di calendar_auth.py) ──────

def _success_page(platform_name: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
  <title>Connessione Genesi</title>
  <style>
    body {{ font-family: -apple-system, sans-serif; background: #0c0c14; color: #fff;
           display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }}
    .card {{ background: #161625; padding: 40px; border-radius: 20px; text-align: center;
             max-width: 400px; border: 1px solid #232335; }}
    h1 {{ color: #00e5ff; margin-bottom: 16px; }}
    p {{ color: #b4b4c3; line-height: 1.6; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>✅ Connesso!</h1>
    <p>Genesi ha ora accesso a <strong>{platform_name}</strong>.</p>
    <p>Puoi chiudere questa scheda e tornare nella chat.</p>
  </div>
  <script>setTimeout(() => window.close(), 4000);</script>
</body>
</html>"""


def _error_page(msg: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
  <title>Errore - Genesi</title>
  <style>
    body {{ font-family: -apple-system, sans-serif; background: #0c0c14; color: #fff;
           display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }}
    .card {{ background: #161625; padding: 40px; border-radius: 20px; text-align: center;
             max-width: 400px; border: 1px solid #ff4444; }}
    h1 {{ color: #ff4444; margin-bottom: 16px; }}
    p {{ color: #b4b4c3; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>❌ Errore</h1>
    <p>{msg}</p>
  </div>
</body>
</html>"""


def _info_page(title: str, msg: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
  <title>{title} - Genesi</title>
  <style>
    body {{ font-family: -apple-system, sans-serif; background: #0c0c14; color: #fff;
           display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }}
    .card {{ background: #161625; padding: 40px; border-radius: 20px; text-align: center;
             max-width: 420px; border: 1px solid #232335; }}
    h1 {{ color: #00e5ff; margin-bottom: 16px; font-size: 1.4rem; }}
    p {{ color: #b4b4c3; line-height: 1.6; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>ℹ️ {title}</h1>
    <p>{msg}</p>
    <p style="margin-top:20px;font-size:0.85rem;color:#6b6b7e;">Puoi chiudere questa scheda.</p>
  </div>
</body>
</html>"""


# ─── GET /api/integrations/status ───────────────────────────────────────────

@router.get("/status")
async def integrations_status(user: AuthUser = Depends(require_auth)):
    """Ritorna lo stato di tutte le integrazioni per l'utente corrente (isolato per JWT)."""
    statuses = []
    for platform, integration in integrations_registry.items():
        try:
            status = await integration.get_status(user.id)
        except Exception as e:
            log("INTEGRATION_STATUS_ERROR", platform=platform, error=str(e), user_id=user.id)
            status = {
                "platform": platform,
                "display_name": integration.display_name,
                "icon": integration.icon,
                "connected": False,
                "error": str(e),
            }
        statuses.append(status)
    return {"integrations": statuses, "user_id": user.id}


# ─── GET /api/integrations/telegram/link-token ───────────────────────────────
# NOTA: questo endpoint deve stare PRIMA di /{platform}/connect per non essere
# intercettato dalla route generica.

@router.get("/telegram/link-token")
async def telegram_link_token(user: AuthUser = Depends(require_auth)):
    """
    Genera un token one-shot per collegare il bot Telegram all'account Genesi.
    Il token è legato allo user_id del JWT — ogni utente genera il proprio.
    L'utente deve inviare al bot Telegram: /start {token}
    """
    from core.integrations.telegram_integration import telegram_integration
    if not telegram_integration._bot_token():
        return JSONResponse(status_code=503, content={
            "error": "Bot Telegram non configurato sul server (TELEGRAM_BOT_TOKEN mancante nel .env)"
        })
    token = await telegram_integration.generate_link_token(user.id)
    bot_status = await telegram_integration.get_status(user.id)
    bot_username = bot_status.get("bot_username", "GenesiBot")
    return {
        "token": token,
        "instruction": f"Apri Telegram e invia al bot @{bot_username}:",
        "command": f"/start {token}",
        "deep_link": f"https://t.me/{bot_username}?start={token}",
        "user_id": user.id,
    }


# ─── GET /api/integrations/{platform}/connect ────────────────────────────────

@router.get("/{platform}/connect")
async def integration_connect(platform: str, user: AuthUser = Depends(require_auth)):
    """Avvia il flusso OAuth per la piattaforma specificata. user_id dal JWT."""
    integration = integrations_registry.get(platform)
    if not integration:
        return JSONResponse(status_code=404, content={"error": f"Piattaforma '{platform}' non trovata"})

    auth_url = await integration.get_auth_url(user.id, BASE_URL)
    if not auth_url:
        # Piattaforme senza OAuth standard: mostra pagina HTML con istruzioni
        if platform == "telegram":
            msg = (
                "Per collegare Telegram, vai in <strong>Impostazioni → Integrazioni → Telegram</strong> "
                "e segui le istruzioni per il bot."
            )
        elif platform == "whatsapp":
            msg = (
                "WhatsApp è gestito automaticamente tramite <strong>OpenClaw</strong>.<br>"
                "Assicurati che OpenClaw sia in esecuzione sul tuo PC."
            )
        else:
            msg = (
                f"Il collegamento a <strong>{integration.display_name}</strong> non è ancora configurato sul server.<br>"
                "Contatta l'amministratore per aggiungere le credenziali necessarie nel file .env."
            )
        return HTMLResponse(_info_page(integration.display_name, msg))

    log("INTEGRATION_CONNECT_START", platform=platform, user_id=user.id)
    return RedirectResponse(auth_url)


# ─── GET /api/integrations/{platform}/callback ───────────────────────────────

@router.get("/{platform}/callback")
async def integration_callback(platform: str, request: Request, code: str = "", state: str = ""):
    """
    Gestisce il callback OAuth.
    `state` contiene lo user_id (passato nel get_auth_url di ogni integrazione).
    Lo user_id viene estratto dallo state — mai da cookie o sessione lato server.
    """
    integration = integrations_registry.get(platform)
    if not integration:
        return HTMLResponse(_error_page(f"Piattaforma '{platform}' non supportata"), status_code=404)

    if not code:
        return HTMLResponse(_error_page("Codice OAuth mancante dalla risposta del provider"), status_code=400)

    user_id = state
    if not user_id:
        return HTMLResponse(_error_page("Session state mancante — riprova il collegamento"), status_code=400)

    success = await integration.handle_callback(user_id=user_id, code=code, state=state)
    if success:
        log("INTEGRATION_CALLBACK_OK", platform=platform, user_id=user_id)
        return HTMLResponse(_success_page(integration.display_name))
    else:
        log("INTEGRATION_CALLBACK_FAIL", platform=platform, user_id=user_id)
        return HTMLResponse(_error_page(f"Errore durante il collegamento a {integration.display_name}"), status_code=400)


# ─── DELETE /api/integrations/{platform}/disconnect ──────────────────────────

@router.delete("/{platform}/disconnect")
async def integration_disconnect(platform: str, user: AuthUser = Depends(require_auth)):
    """Revoca i token dell'utente corrente. Non tocca i dati degli altri utenti."""
    integration = integrations_registry.get(platform)
    if not integration:
        return JSONResponse(status_code=404, content={"error": f"Piattaforma '{platform}' non trovata"})

    success = await integration.disconnect(user.id)
    log("INTEGRATION_DISCONNECT", platform=platform, user_id=user.id, success=success)
    return {"platform": platform, "disconnected": success, "user_id": user.id}


# ─── POST /api/integrations/telegram/webhook (endpoint pubblico) ─────────────

@router.post("/telegram/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Riceve gli update dal bot Telegram (endpoint pubblico — Telegram non invia JWT).
    ISOLAMENTO: risolve chat_id → user_id prima di fare qualsiasi elaborazione.
    Risponde sempre {"ok": True} entro 3s per evitare timeout Telegram (retry ogni 5s).
    L'elaborazione pesante (proactor) viene delegata a un background task.
    """
    from core.integrations.telegram_integration import telegram_integration

    try:
        update = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False})

    parsed = telegram_integration.handle_update(update)
    if not parsed:
        return {"ok": True}  # Update ignorato (non testuale: foto, sticker, ecc.)

    chat_id = parsed["chat_id"]
    text = parsed.get("text", "").strip()
    from_user = parsed.get("from", {})

    log("TELEGRAM_WEBHOOK_UPDATE", chat_id=chat_id, text=text[:50], from_id=from_user.get("id"))

    if not text:
        return {"ok": True}

    # ── Flusso di linking: /start {token} ────────────────────────────────────
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            token = parts[1].strip()
            user_id = await telegram_integration.resolve_link_token(token)
            if user_id:
                await telegram_integration.save_chat_binding(user_id, chat_id)
                await telegram_integration.send_message(
                    user_id=user_id,
                    to=chat_id,
                    text="✅ Telegram collegato a Genesi!\n\nOra puoi scrivermi direttamente qui.",
                )
                log("TELEGRAM_LINKED_VIA_WEBHOOK", user_id=user_id, chat_id=chat_id)
                return {"ok": True}

        # Token mancante o non valido
        await telegram_integration.send_message(
            user_id="system",
            to=chat_id,
            text="👋 Per collegare questo bot al tuo account Genesi, apri l'app e vai in *Impostazioni → Integrazioni → Telegram*.",
        )
        return {"ok": True}

    # ── Messaggio normale: risolvi chat_id → user_id ─────────────────────────
    user_id = await telegram_integration.get_user_id_for_chat(chat_id)
    if not user_id:
        await telegram_integration.send_message(
            user_id="system",
            to=chat_id,
            text="⚠️ Account non collegato\\. Apri Genesi → Impostazioni → Integrazioni → Telegram per connetterti\\.",
        )
        return {"ok": True}

    # ── Delega al proactor dell'utente in background ──────────────────────────
    background_tasks.add_task(_process_telegram_message, user_id, chat_id, text)
    return {"ok": True}


async def _process_telegram_message(user_id: str, chat_id: str, text: str) -> None:
    """
    Elabora un messaggio Telegram in background:
    - Chiama simple_chat_handler con lo user_id corretto (isolato)
    - Invia la risposta al chat_id Telegram
    """
    from core.integrations.telegram_integration import telegram_integration
    from core.simple_chat import simple_chat_handler

    try:
        log("TELEGRAM_PROCESS_START", user_id=user_id, chat_id=chat_id, text=text[:50])
        response = await simple_chat_handler(user_id=user_id, message=text)
        if response:
            await telegram_integration.send_message(user_id=user_id, to=chat_id, text=response)
            log("TELEGRAM_RESPONSE_SENT", user_id=user_id, chat_id=chat_id)
    except Exception as e:
        log("TELEGRAM_PROCESS_ERROR", user_id=user_id, chat_id=chat_id, error=str(e))
        await telegram_integration.send_message(
            user_id=user_id,
            to=chat_id,
            text="⚠️ Si è verificato un errore. Riprova tra poco.",
        )
