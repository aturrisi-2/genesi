"""
GENESI — Telegram Bot (Full Extension)
Parità completa con la webapp:
- Chat testuale con tutti gli intent (meteo, news, ricerca web, ecc.)
- Invio immagini → analisi automatica tramite /api/upload
- Messaggi vocali → trascrizione STT → risposta Genesi
- Immagini generate/trovate → inviate come foto Telegram
"""

import asyncio
import base64
import json
import logging
import os
import re
import httpx
from core.storage import storage

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API   = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
TELEGRAM_FILES = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}"
GENESI_URL     = "http://localhost:8000"

# Regex meteo
_WEATHER_RE = re.compile(
    r'\b(meteo|tempo|temperatura|piogge?|sole|vento|previsioni?|forecast|'
    r'caldo|freddo|nebbia|neve|nuvoloso|sereno|umidità)\b',
    re.IGNORECASE
)

# Regex per trovare URL immagini nelle risposte di Genesi
_IMG_URL_RE = re.compile(
    r'https?://[^\s\)\"\']+\.(?:jpg|jpeg|png|webp|gif)(?:\?[^\s\)\"\']*)?',
    re.IGNORECASE
)
# Markdown immagine: ![alt](url)
_IMG_MD_RE = re.compile(r'!\[.*?\]\((https?://[^\)]+)\)', re.IGNORECASE)

# Stati conversazionali
STATE_IDLE               = "idle"
STATE_AWAIT_EMAIL        = "await_email"
STATE_AWAIT_PASSWORD     = "await_password"
STATE_AWAIT_REG_EMAIL    = "await_reg_email"
STATE_AWAIT_REG_PASSWORD = "await_reg_password"
STATE_AWAIT_CITY         = "await_city"


def _session_key(telegram_id: int) -> str:
    return f"telegram:session:{telegram_id}"


def _decode_user_id(token: str) -> str | None:
    try:
        payload = token.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        data = json.loads(base64.b64decode(payload))
        return data.get("sub") or data.get("user_id")
    except Exception:
        return None


# ── Profilo ────────────────────────────────────────────────────────────────────

async def _get_city(token: str) -> str:
    user_id = _decode_user_id(token)
    if not user_id:
        return ""
    profile = await storage.load(f"profile:{user_id}", default={})
    return profile.get("city", "") or ""


async def _save_city(token: str, city: str):
    user_id = _decode_user_id(token)
    if not user_id:
        return
    profile = await storage.load(f"profile:{user_id}", default={})
    profile["city"] = city
    await storage.save(f"profile:{user_id}", profile)


# ── Telegram API helpers ───────────────────────────────────────────────────────

async def send_message(chat_id: int, text: str):
    if not text:
        return
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(f"{TELEGRAM_API}/sendMessage", json=payload)
        except Exception as e:
            logger.error("TELEGRAM_SEND_ERROR chat_id=%s err=%s", chat_id, e)


async def send_photo(chat_id: int, photo_url: str, caption: str = ""):
    payload = {"chat_id": chat_id, "photo": photo_url}
    if caption:
        payload["caption"] = caption[:1024]
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            res = await client.post(f"{TELEGRAM_API}/sendPhoto", json=payload)
            return res.status_code == 200
        except Exception as e:
            logger.error("TELEGRAM_SEND_PHOTO_ERROR chat_id=%s err=%s", chat_id, e)
            return False


async def send_typing(chat_id: int):
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            await client.post(f"{TELEGRAM_API}/sendChatAction",
                              json={"chat_id": chat_id, "action": "typing"})
        except Exception:
            pass


async def download_file(file_id: str) -> bytes | None:
    """Scarica un file da Telegram tramite file_id."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            res = await client.get(f"{TELEGRAM_API}/getFile",
                                   params={"file_id": file_id})
            file_path = res.json().get("result", {}).get("file_path")
            if not file_path:
                return None
            res2 = await client.get(f"{TELEGRAM_FILES}/{file_path}")
            return res2.content
        except Exception as e:
            logger.error("TELEGRAM_DOWNLOAD_ERROR file_id=%s err=%s", file_id, e)
            return None


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


# ── Genesi API calls ───────────────────────────────────────────────────────────

async def _chat(token: str, message: str, city: str = "") -> str:
    if city and _WEATHER_RE.search(message) and city.lower() not in message.lower():
        message = f"{message} (sono a {city})"
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            f"{GENESI_URL}/api/chat",
            json={"message": message, "platform": "telegram"},
            headers={"Authorization": f"Bearer {token}"},
        )
        if res.status_code == 401:
            return "__TOKEN_EXPIRED__"
        if res.status_code != 200:
            return "Genesi non è disponibile in questo momento."
        data = res.json()
        return data.get("response") or data.get("message") or "Nessuna risposta."


async def _upload_file(token: str, data: bytes, filename: str,
                       content_type: str) -> str:
    """Carica un file su Genesi e ritorna il testo di analisi."""
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            f"{GENESI_URL}/api/upload/",
            files={"file": (filename, data, content_type)},
            headers={"Authorization": f"Bearer {token}"},
        )
        if res.status_code == 200:
            d = res.json()
            return d.get("analysis") or d.get("summary") or d.get("message") or ""
        return ""


async def _transcribe(token: str, audio_data: bytes,
                      content_type: str = "audio/ogg") -> str:
    """Invia audio all'endpoint STT e ritorna il testo trascritto."""
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            f"{GENESI_URL}/api/stt/",
            files={"audio": ("voice.ogg", audio_data, content_type)},
            headers={"Authorization": f"Bearer {token}"},
        )
        if res.status_code == 200:
            return res.json().get("text", "")
    return ""


# ── Risposta con immagini ──────────────────────────────────────────────────────

async def _send_response(chat_id: int, reply: str):
    """Invia la risposta: se contiene URL immagini le manda come foto Telegram."""
    # Cerca prima markdown immagini: ![alt](url)
    md_urls = _IMG_MD_RE.findall(reply)
    # Poi URL immagini pure nel testo
    raw_urls = _IMG_URL_RE.findall(reply)

    img_urls = md_urls + [u for u in raw_urls if u not in md_urls]

    if img_urls:
        # Rimuovi i link immagine dal testo per non mostrare URL grezze
        clean_text = _IMG_MD_RE.sub("", reply).strip()
        clean_text = _IMG_URL_RE.sub("", clean_text).strip()

        for url in img_urls[:3]:  # max 3 immagini
            sent = await send_photo(chat_id, url, caption=clean_text if clean_text else "")
            if not sent:
                # Fallback: manda il testo con l'URL
                await send_message(chat_id, reply)
            clean_text = ""  # caption solo sulla prima
        return

    # Risposta testuale normale
    if len(reply) > 4000:
        for i in range(0, len(reply), 4000):
            await send_message(chat_id, reply[i:i+4000])
            await asyncio.sleep(0.3)
    else:
        await send_message(chat_id, reply)


# ── Post-login ─────────────────────────────────────────────────────────────────

async def _complete_login(chat_id: int, token: str, email: str):
    city = await _get_city(token)
    session = {"token": token, "email": email, "city": city, "state": STATE_IDLE}
    if not city:
        session["state"] = STATE_AWAIT_CITY
        await storage.save(_session_key(chat_id), session)
        await send_message(chat_id,
            "✅ Collegato!\n\n"
            "Per darti il meteo della tua zona, dimmi in quale città sei:")
    else:
        await storage.save(_session_key(chat_id), session)
        await send_message(chat_id,
            "✅ Collegato!\n\n"
            "Sono Genesi. Puoi scrivermi, mandarmi foto o messaggi vocali. "
            "Sono qui.")


# ── Main update handler ────────────────────────────────────────────────────────

async def handle_update(update: dict):
    try:
        msg = update.get("message")
        if not msg:
            return

        chat_id    = msg["chat"]["id"]
        first_name = msg.get("from", {}).get("first_name", "")
        text       = msg.get("text", "").strip()
        photo      = msg.get("photo")       # lista di dimensioni
        voice      = msg.get("voice")       # messaggio vocale
        audio      = msg.get("audio")       # file audio generico
        document   = msg.get("document")    # documento (pdf, txt, ecc.)
        caption    = msg.get("caption", "").strip()

        session = await storage.load(_session_key(chat_id)) or {}
        state   = session.get("state", STATE_IDLE)

        # ── Comandi globali ────────────────────────────────────────────────────
        if text == "/start":
            if session.get("token"):
                await send_message(chat_id,
                    f"Bentornato {first_name}! Sono qui.\n\n"
                    f"Puoi scrivermi, mandarmi foto o messaggi vocali.")
            else:
                session = {"state": STATE_AWAIT_EMAIL}
                await storage.save(_session_key(chat_id), session)
                await send_message(chat_id,
                    f"Ciao {first_name}! 👋 Sono Genesi, il tuo assistente AI.\n\n"
                    f"Inserisci la tua email:")
            return

        if text in ("/login", "/accedi"):
            session = {"state": STATE_AWAIT_EMAIL}
            await storage.save(_session_key(chat_id), session)
            await send_message(chat_id, "Inserisci la tua email:")
            return

        if text in ("/registrati", "/nuovo"):
            session = {"state": STATE_AWAIT_REG_EMAIL}
            await storage.save(_session_key(chat_id), session)
            await send_message(chat_id, "Scegli un'email per il tuo account:")
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
            email, password = session.get("pending_email", ""), text
            await send_typing(chat_id)
            token = await _login(email, password)
            if not token:
                session.update({"state": STATE_AWAIT_EMAIL, "pending_email": None})
                await storage.save(_session_key(chat_id), session)
                await send_message(chat_id,
                    "Credenziali non valide. Reinserisci la tua email:")
                return
            logger.info("TELEGRAM_LOGIN_OK telegram_id=%s email=%s", chat_id, email)
            await _complete_login(chat_id, token, email)
            return

        # ── Flusso REGISTRAZIONE ───────────────────────────────────────────────
        if state == STATE_AWAIT_REG_EMAIL:
            session["pending_email"] = text
            session["state"] = STATE_AWAIT_REG_PASSWORD
            await storage.save(_session_key(chat_id), session)
            await send_message(chat_id, "Scegli una password (min 8 caratteri):")
            return

        if state == STATE_AWAIT_REG_PASSWORD:
            email, password = session.get("pending_email", ""), text
            await send_typing(chat_id)
            ok = await _register(email, password)
            if not ok:
                session["state"] = STATE_AWAIT_REG_EMAIL
                await storage.save(_session_key(chat_id), session)
                await send_message(chat_id,
                    "Registrazione non riuscita. Forse l'email è già in uso.\n"
                    "Inserisci un'altra email:")
                return
            token = await _login(email, password)
            logger.info("TELEGRAM_REGISTER_OK telegram_id=%s email=%s", chat_id, email)
            await _complete_login(chat_id, token, email)
            return

        # ── Città mancante ─────────────────────────────────────────────────────
        if state == STATE_AWAIT_CITY and text:
            city = text.strip().title()
            await _save_city(session["token"], city)
            session.update({"city": city, "state": STATE_IDLE})
            await storage.save(_session_key(chat_id), session)
            await send_message(chat_id,
                f"Perfetto, ti ricordo a {city}!\n\n"
                f"Scrivimi, mandami foto o vocali — sono qui.")
            return

        # ── Verifica login ─────────────────────────────────────────────────────
        token = session.get("token")
        if not token:
            session = {"state": STATE_AWAIT_EMAIL}
            await storage.save(_session_key(chat_id), session)
            await send_message(chat_id, "Inserisci prima la tua email:")
            return

        city = session.get("city", "")

        # ── FOTO ───────────────────────────────────────────────────────────────
        if photo:
            await send_typing(chat_id)
            file_id   = photo[-1]["file_id"]  # qualità massima
            img_bytes = await download_file(file_id)
            if not img_bytes:
                await send_message(chat_id, "Non riuscito a scaricare la foto.")
                return

            analysis = await _upload_file(token, img_bytes, "photo.jpg", "image/jpeg")
            user_msg  = caption or "Analizza questa immagine che ti ho inviato."
            if analysis:
                user_msg = f"{user_msg}\n\n[Contenuto immagine: {analysis}]"

            reply = await _chat(token, user_msg, city=city)
            if reply == "__TOKEN_EXPIRED__":
                session = {"state": STATE_AWAIT_EMAIL}
                await storage.save(_session_key(chat_id), session)
                await send_message(chat_id, "Sessione scaduta. Reinserisci la tua email:")
                return
            await _send_response(chat_id, reply)
            logger.info("TELEGRAM_PHOTO_OK chat_id=%s", chat_id)
            return

        # ── DOCUMENTO (PDF, TXT, ecc.) ─────────────────────────────────────────
        if document:
            await send_typing(chat_id)
            mime     = document.get("mime_type", "application/octet-stream")
            filename = document.get("file_name", "document")
            doc_bytes = await download_file(document["file_id"])
            if not doc_bytes:
                await send_message(chat_id, "Non riuscito a scaricare il documento.")
                return

            analysis = await _upload_file(token, doc_bytes, filename, mime)
            user_msg  = caption or f"Ho inviato il documento: {filename}."
            if analysis:
                user_msg = f"{user_msg}\n\n[Contenuto: {analysis[:500]}]"

            reply = await _chat(token, user_msg, city=city)
            if reply == "__TOKEN_EXPIRED__":
                session = {"state": STATE_AWAIT_EMAIL}
                await storage.save(_session_key(chat_id), session)
                await send_message(chat_id, "Sessione scaduta. Reinserisci la tua email:")
                return
            await _send_response(chat_id, reply)
            logger.info("TELEGRAM_DOCUMENT_OK chat_id=%s filename=%s", chat_id, filename)
            return

        # ── VOCALE ─────────────────────────────────────────────────────────────
        if voice or audio:
            await send_typing(chat_id)
            media      = voice or audio
            audio_bytes = await download_file(media["file_id"])
            if not audio_bytes:
                await send_message(chat_id, "Non riuscito a scaricare il vocale.")
                return

            transcription = await _transcribe(token, audio_bytes, "audio/ogg")
            if not transcription:
                await send_message(chat_id,
                    "Non sono riuscita a capire il vocale. Prova a scrivere.")
                return

            # Mostra la trascrizione e rispondi
            await send_message(chat_id, f"🎤 {transcription}")
            reply = await _chat(token, transcription, city=city)
            if reply == "__TOKEN_EXPIRED__":
                session = {"state": STATE_AWAIT_EMAIL}
                await storage.save(_session_key(chat_id), session)
                await send_message(chat_id, "Sessione scaduta. Reinserisci la tua email:")
                return
            await _send_response(chat_id, reply)
            logger.info("TELEGRAM_VOICE_OK chat_id=%s transcription=%s",
                        chat_id, transcription[:50])
            return

        # ── TESTO ──────────────────────────────────────────────────────────────
        if not text:
            return

        if _WEATHER_RE.search(text) and not city:
            session["state"]           = STATE_AWAIT_CITY
            session["pending_message"] = text
            await storage.save(_session_key(chat_id), session)
            await send_message(chat_id,
                "Per il meteo ho bisogno di sapere dove sei. "
                "In quale città ti trovi?")
            return

        await send_typing(chat_id)
        reply = await _chat(token, text, city=city)

        if reply == "__TOKEN_EXPIRED__":
            session = {"state": STATE_AWAIT_EMAIL}
            await storage.save(_session_key(chat_id), session)
            await send_message(chat_id, "Sessione scaduta. Reinserisci la tua email:")
            return

        await _send_response(chat_id, reply)

    except Exception as e:
        logger.error("TELEGRAM_HANDLE_ERROR err=%s", e)
