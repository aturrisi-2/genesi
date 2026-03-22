"""
GENESI — Telegram Bot
Gestisce le interazioni Telegram come canale alternativo alla webapp.
Flusso login conversazionale: il bot chiede email e password separatamente.
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

# Stati conversazionali per il login
STATE_IDLE              = "idle"
STATE_AWAIT_EMAIL       = "await_email"
STATE_AWAIT_PASSWORD    = "await_password"
STATE_AWAIT_REG_EMAIL   = "await_reg_email"
STATE_AWAIT_REG_PASSWORD = "await_reg_password"

def _session_key(telegram_id: int) -> str:
    return f"telegram:session:{telegram_id}"


# ── Telegram API helpers ───────────────────────────────────────────────────────

async def send_message(chat_id: int, text: str):
    payload = {"chat_id": chat_id, "text": text}
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
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(f"{GENESI_URL}/auth/login",
                                json={"email": email, "password": password})
        if res.status_code == 200:
            return res.json().get("access_token")
    return None


async def _register(email: str, password: str) -> bool:
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(f"{GENESI_URL}/api/auth/register",
                                json={"email": email, "password": password})
        return res.status_code in (200, 201)


async def _chat(token: str, message: str) -> str:
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

        session = await storage.load(_session_key(chat_id)) or {}
        state   = session.get("state", STATE_IDLE)

        # ── Comandi globali (sempre disponibili) ───────────────────────────────
        if text == "/start":
            if session.get("token"):
                await send_message(chat_id,
                    f"Bentornato {first_name}! Sono qui, scrivimi pure.")
            else:
                session = {"state": STATE_AWAIT_EMAIL}
                await storage.save(_session_key(chat_id), session)
                await send_message(chat_id,
                    f"Ciao {first_name}! 👋 Sono Genesi, il tuo assistente AI personale.\n\n"
                    f"Inserisci la tua email Genesi:")
            return

        if text in ("/login", "/accedi"):
            session = {"state": STATE_AWAIT_EMAIL}
            await storage.save(_session_key(chat_id), session)
            await send_message(chat_id, "Inserisci la tua email:")
            return

        if text in ("/registrati", "/nuovo"):
            session = {"state": STATE_AWAIT_REG_EMAIL}
            await storage.save(_session_key(chat_id), session)
            await send_message(chat_id, "Scegli un'email per il tuo account Genesi:")
            return

        if text == "/logout":
            await storage.save(_session_key(chat_id), {"state": STATE_IDLE})
            await send_message(chat_id, "Disconnesso. Usa /login per ricollegarti.")
            return

        # ── Flusso LOGIN ───────────────────────────────────────────────────────
        if state == STATE_AWAIT_EMAIL:
            session["pending_email"] = text
            session["state"] = STATE_AWAIT_PASSWORD
            await storage.save(_session_key(chat_id), session)
            await send_message(chat_id, "Inserisci la tua password:")
            return

        if state == STATE_AWAIT_PASSWORD:
            email    = session.get("pending_email", "")
            password = text
            await send_typing(chat_id)
            token = await _login(email, password)
            if not token:
                session["state"] = STATE_AWAIT_EMAIL
                session.pop("pending_email", None)
                await storage.save(_session_key(chat_id), session)
                await send_message(chat_id,
                    "Credenziali non valide. Reinserisci la tua email:")
                return
            session = {"token": token, "email": email, "state": STATE_IDLE}
            await storage.save(_session_key(chat_id), session)
            logger.info("TELEGRAM_LOGIN_OK telegram_id=%s email=%s", chat_id, email)
            await send_message(chat_id,
                f"✅ Collegato!\n\nSono Genesi. Ricordo tutto ciò che mi hai "
                f"già raccontato. Scrivimi pure.")
            return

        # ── Flusso REGISTRAZIONE ───────────────────────────────────────────────
        if state == STATE_AWAIT_REG_EMAIL:
            session["pending_email"] = text
            session["state"] = STATE_AWAIT_REG_PASSWORD
            await storage.save(_session_key(chat_id), session)
            await send_message(chat_id, "Scegli una password (min 8 caratteri):")
            return

        if state == STATE_AWAIT_REG_PASSWORD:
            email    = session.get("pending_email", "")
            password = text
            await send_typing(chat_id)
            ok = await _register(email, password)
            if not ok:
                session["state"] = STATE_AWAIT_REG_EMAIL
                await storage.save(_session_key(chat_id), session)
                await send_message(chat_id,
                    "Registrazione non riuscita. Forse esiste già un account "
                    "con questa email.\n\nInserisci un'altra email, oppure "
                    "usa /login per accedere:")
                return
            token = await _login(email, password)
            session = {"token": token, "email": email, "state": STATE_IDLE}
            await storage.save(_session_key(chat_id), session)
            logger.info("TELEGRAM_REGISTER_OK telegram_id=%s email=%s", chat_id, email)
            await send_message(chat_id,
                f"✅ Account creato!\n\nSono Genesi, il tuo assistente AI "
                f"personale. Scrivimi qualcosa per cominciare.")
            return

        # ── Chat normale ───────────────────────────────────────────────────────
        if not session.get("token"):
            session = {"state": STATE_AWAIT_EMAIL}
            await storage.save(_session_key(chat_id), session)
            await send_message(chat_id,
                "Per chattare con me inserisci prima la tua email:")
            return

        await send_typing(chat_id)
        reply = await _chat(session["token"], text)

        if reply == "__TOKEN_EXPIRED__":
            session = {"state": STATE_AWAIT_EMAIL}
            await storage.save(_session_key(chat_id), session)
            await send_message(chat_id,
                "Sessione scaduta. Inserisci di nuovo la tua email:")
            return

        # Telegram: max 4096 caratteri per messaggio
        if len(reply) > 4000:
            for i in range(0, len(reply), 4000):
                await send_message(chat_id, reply[i:i+4000])
                await asyncio.sleep(0.3)
        else:
            await send_message(chat_id, reply)

    except Exception as e:
        logger.error("TELEGRAM_HANDLE_ERROR err=%s", e)
