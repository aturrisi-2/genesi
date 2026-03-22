"""
GENESI — Telegram Bot
Gestisce le interazioni Telegram come canale alternativo alla webapp.
Ogni utente Telegram si collega al proprio account Genesi via /login.
"""

import asyncio
import logging
import os
import httpx
from core.storage import storage

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API   = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
GENESI_URL     = "http://localhost:8000"

# ── Storage keys ───────────────────────────────────────────────────────────────
def _session_key(telegram_id: int) -> str:
    return f"telegram:session:{telegram_id}"


# ── Telegram API helpers ───────────────────────────────────────────────────────

async def send_message(chat_id: int, text: str, parse_mode: str = None):
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(f"{TELEGRAM_API}/sendMessage", json=payload)
        except Exception as e:
            logger.error("TELEGRAM_SEND_ERROR chat_id=%s err=%s", chat_id, e)


async def send_typing(chat_id: int):
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            await client.post(f"{TELEGRAM_API}/sendChatAction",
                              json={"chat_id": chat_id, "action": "typing"})
        except Exception:
            pass


async def set_webhook(webhook_url: str):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(f"{TELEGRAM_API}/setWebhook",
                                json={"url": webhook_url,
                                      "allowed_updates": ["message"]})
        data = res.json()
        if data.get("ok"):
            logger.info("TELEGRAM_WEBHOOK_SET url=%s", webhook_url)
        else:
            logger.error("TELEGRAM_WEBHOOK_ERROR %s", data)


# ── Auth helpers ───────────────────────────────────────────────────────────────

async def _login(email: str, password: str) -> str | None:
    """Chiama /auth/login e ritorna il token JWT o None."""
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(f"{GENESI_URL}/auth/login",
                                json={"email": email, "password": password})
        if res.status_code == 200:
            return res.json().get("access_token")
    return None


async def _register(email: str, password: str) -> bool:
    """Registra un nuovo account Genesi."""
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(f"{GENESI_URL}/api/auth/register",
                                json={"email": email, "password": password})
        return res.status_code in (200, 201)


async def _chat(token: str, message: str) -> str:
    """Invia un messaggio a Genesi e ritorna la risposta."""
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            f"{GENESI_URL}/api/chat",
            json={"message": message, "platform": "telegram"},
            headers={"Authorization": f"Bearer {token}"},
        )
        if res.status_code == 401:
            return "__TOKEN_EXPIRED__"
        if res.status_code != 200:
            return "Genesi non è disponibile in questo momento. Riprova tra poco."
        data = res.json()
        return data.get("response") or data.get("message") or "Nessuna risposta."


# ── Command handlers ───────────────────────────────────────────────────────────

async def _handle_start(chat_id: int, first_name: str):
    session = await storage.load(_session_key(chat_id))
    if session and session.get("token"):
        await send_message(chat_id,
            f"Bentornato! Sei già collegato come {session.get('email')}.\n"
            f"Scrivimi pure, sono qui.")
    else:
        await send_message(chat_id,
            f"Ciao {first_name}! 👋 Sono Genesi, il tuo assistente AI personale.\n\n"
            f"Per iniziare collegati al tuo account:\n"
            f"  /login tua@email.com password\n\n"
            f"Non hai ancora un account?\n"
            f"  /registrati tua@email.com password\n\n"
            f"Una volta collegato potrai chattare con me esattamente come dalla webapp, "
            f"con tutta la tua memoria e i tuoi dati.")


async def _handle_login(chat_id: int, parts: list[str]):
    if len(parts) < 3:
        await send_message(chat_id, "Uso: /login email password")
        return

    email, password = parts[1], parts[2]
    await send_typing(chat_id)
    token = await _login(email, password)

    if not token:
        await send_message(chat_id,
            "Credenziali non valide. Controlla email e password e riprova.\n"
            "Non hai un account? Usa /registrati email password")
        return

    await storage.save(_session_key(chat_id), {"token": token, "email": email})
    logger.info("TELEGRAM_LOGIN_OK telegram_id=%s email=%s", chat_id, email)
    await send_message(chat_id,
        f"✅ Collegato come {email}!\n\n"
        f"Da ora possiamo parlare. Ricordo tutto ciò che mi hai già detto "
        f"dalla webapp. Scrivimi pure.")


async def _handle_registrati(chat_id: int, parts: list[str]):
    if len(parts) < 3:
        await send_message(chat_id, "Uso: /registrati email password")
        return

    email, password = parts[1], parts[2]
    await send_typing(chat_id)
    ok = await _register(email, password)

    if not ok:
        await send_message(chat_id,
            "Registrazione non riuscita. Forse esiste già un account con questa email.\n"
            "Prova /login email password")
        return

    token = await _login(email, password)
    if not token:
        await send_message(chat_id,
            "Account creato! Ora fai /login email password per collegarti.")
        return

    await storage.save(_session_key(chat_id), {"token": token, "email": email})
    logger.info("TELEGRAM_REGISTER_OK telegram_id=%s email=%s", chat_id, email)
    await send_message(chat_id,
        f"✅ Account creato e collegato!\n\n"
        f"Sono Genesi, il tuo assistente AI personale. "
        f"Scrivimi qualcosa per cominciare.")


async def _handle_logout(chat_id: int):
    await storage.save(_session_key(chat_id), {})
    await send_message(chat_id, "Disconnesso. Usa /login per ricollegarti.")


async def _handle_message(chat_id: int, text: str):
    session = await storage.load(_session_key(chat_id))
    if not session or not session.get("token"):
        await send_message(chat_id,
            "Per chattare con me collegati prima:\n"
            "/login email password\n\n"
            "Non hai un account? /registrati email password")
        return

    await send_typing(chat_id)
    reply = await _chat(session["token"], text)

    if reply == "__TOKEN_EXPIRED__":
        # Token scaduto: chiedi di fare login di nuovo
        await storage.save(_session_key(chat_id), {})
        await send_message(chat_id,
            "La sessione è scaduta. Fai /login email password per ricollegarti.")
        return

    # Telegram ha un limite di 4096 caratteri per messaggio
    if len(reply) > 4000:
        for i in range(0, len(reply), 4000):
            await send_message(chat_id, reply[i:i+4000])
            await asyncio.sleep(0.3)
    else:
        await send_message(chat_id, reply)


# ── Main update handler ────────────────────────────────────────────────────────

async def handle_update(update: dict):
    try:
        msg = update.get("message")
        if not msg:
            return

        chat_id    = msg["chat"]["id"]
        text       = msg.get("text", "").strip()
        first_name = msg.get("from", {}).get("first_name", "")

        if not text:
            return

        logger.info("TELEGRAM_MESSAGE chat_id=%s text=%s", chat_id, text[:60])

        if text.startswith("/start"):
            await _handle_start(chat_id, first_name)
        elif text.startswith("/login"):
            await _handle_login(chat_id, text.split())
        elif text.startswith("/registrati"):
            await _handle_registrati(chat_id, text.split())
        elif text.startswith("/logout"):
            await _handle_logout(chat_id)
        else:
            await _handle_message(chat_id, text)

    except Exception as e:
        logger.error("TELEGRAM_HANDLE_ERROR err=%s", e)
