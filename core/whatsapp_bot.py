"""
GENESI — WhatsApp Bot (Meta Business Cloud API)
Parità completa con Telegram:
- Chat testuale con tutti gli intent (meteo, news, ricerca web, ecc.)
- Immagini → analisi automatica tramite /api/upload
- Messaggi vocali → trascrizione STT → risposta Genesi
- Documenti PDF/TXT → analisi
- Session persistence con auto-refresh token
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

# ── Credenziali Meta WhatsApp Business Cloud API ────────────────────────────
WA_ACCESS_TOKEN    = os.getenv("WA_ACCESS_TOKEN", "")
WA_PHONE_NUMBER_ID = os.getenv("WA_PHONE_NUMBER_ID", "")
WA_VERIFY_TOKEN    = os.getenv("WA_VERIFY_TOKEN", "genesi_wa_verify")
WA_PHONE_NUMBER    = os.getenv("WA_PHONE_NUMBER", "393313650671")   # senza +
WA_API_VERSION     = "v19.0"
WA_API_BASE        = f"https://graph.facebook.com/{WA_API_VERSION}"

GENESI_URL         = "http://localhost:8000"

_WEBAPP_LINK = "https://genesi.lucadigitale.eu/"

# Regex meteo
_WEATHER_RE = re.compile(
    r'\b(meteo|tempo|temperatura|piogge?|sole|vento|previsioni?|forecast|'
    r'caldo|freddo|nebbia|neve|nuvoloso|sereno|umidità)\b',
    re.IGNORECASE
)

# Filtro gruppi: risponde solo se menzionato o saluto
_GREETING_RE = re.compile(
    r'\b(ciao|salve|buongiorno|buonasera|buonanotte|hey|hei|ehilà|'
    r'hello|hi|buon\s*giorno|buona\s*sera)\b',
    re.IGNORECASE
)
_GENESI_RE = re.compile(r'\bgenesi\b', re.IGNORECASE)

_CELEBRATION_EMOJIS = ("🎉", "🎊", "🥳", "🎈", "🥂", "🍾", "🎂", "🏆", "🎁")
_GOOD_NEWS_KW = (
    "habemus", "ce l'ho fatta", "ce la fatta", "ho preso", "ho comprato",
    "è arrivat", "arrivata la", "arrivato il", "finalmente", "ho trovato",
    "ho vinto", "abbiamo vinto", "promozione", "promosso", "promossa",
    "laurea", "diploma", "compleanno", "auguri",
)


def _group_should_respond(text: str, caption: str = "") -> bool:
    """In un gruppo risponde solo se: nome 'Genesi', saluto, o buona notizia/celebrazione."""
    combined = f"{text} {caption}".strip()
    if not combined:
        return False
    if _GENESI_RE.search(combined):
        return True
    if _GREETING_RE.search(combined):
        return True
    if any(e in combined for e in _CELEBRATION_EMOJIS):
        return True
    combined_lower = combined.lower()
    if any(kw in combined_lower for kw in _GOOD_NEWS_KW):
        return True
    return False

# Regex per trovare URL immagini nelle risposte
_IMG_URL_RE = re.compile(
    r'https?://[^\s\)\"\']+\.(?:jpg|jpeg|png|webp|gif)(?:\?[^\s\)\"\']*)?',
    re.IGNORECASE
)
_IMG_MD_RE = re.compile(r'!\[.*?\]\((https?://[^\)]+)\)', re.IGNORECASE)

# Stati conversazionali (identici a Telegram)
STATE_IDLE               = "idle"
STATE_AWAIT_EMAIL        = "await_email"
STATE_AWAIT_PASSWORD     = "await_password"
STATE_AWAIT_REG_EMAIL    = "await_reg_email"
STATE_AWAIT_REG_PASSWORD = "await_reg_password"
STATE_AWAIT_CITY         = "await_city"

_WELCOME_MSG = (
    "✅ *Collegato!*\n\n"
    "Sono *Genesi*, la tua assistente AI personale.\n\n"
    "Puoi:\n"
    "• 💬 Scrivermi in chat libera\n"
    "• 🖼 Mandarmi foto da analizzare\n"
    "• 🎤 Inviarmi messaggi vocali\n"
    "• 📄 Condividere PDF e documenti\n"
    "• ☀️ Chiedere meteo, notizie, ricerche web\n\n"
    "Ogni nostra conversazione mi aiuta a conoscerti meglio e a migliorare.\n\n"
    f"Trovi anche la versione completa su: {_WEBAPP_LINK}"
)

_WELCOME_CITY_PREAMBLE = (
    "Per darti il meteo della tua zona, dimmi in quale città sei:"
)


def _session_key(wa_id: str) -> str:
    return f"whatsapp:session:{wa_id}"


def _decode_user_id(token: str) -> str | None:
    try:
        payload = token.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        data = json.loads(base64.b64decode(payload))
        return data.get("sub") or data.get("user_id")
    except Exception:
        return None


# ── Profilo ─────────────────────────────────────────────────────────────────

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


# ── WhatsApp API helpers ─────────────────────────────────────────────────────

async def send_message(wa_id: str, text: str):
    """Invia un messaggio testuale WhatsApp."""
    if not text or not WA_ACCESS_TOKEN or not WA_PHONE_NUMBER_ID:
        return
    # WhatsApp ha limite 4096 caratteri per messaggio
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    async with httpx.AsyncClient(timeout=15) as client:
        for chunk in chunks:
            payload = {
                "messaging_product": "whatsapp",
                "to": wa_id,
                "type": "text",
                "text": {"body": chunk, "preview_url": False},
            }
            try:
                await client.post(
                    f"{WA_API_BASE}/{WA_PHONE_NUMBER_ID}/messages",
                    json=payload,
                    headers={"Authorization": f"Bearer {WA_ACCESS_TOKEN}"},
                )
            except Exception as e:
                logger.error("WA_SEND_ERROR wa_id=%s err=%s", wa_id, e)
            if len(chunks) > 1:
                await asyncio.sleep(0.3)


async def send_typing(wa_id: str, msg_id: str = ""):
    """Mostra l'indicatore di digitazione all'utente WhatsApp.

    WhatsApp Cloud API: prima segna il messaggio come letto (blue ticks),
    poi invia il typing indicator con il formato corretto per Cloud API.
    """
    if not WA_ACCESS_TOKEN or not WA_PHONE_NUMBER_ID:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            # 1. Mark as read — ufficialmente supportato, mostra le spunte blu
            if msg_id:
                r = await client.post(
                    f"{WA_API_BASE}/{WA_PHONE_NUMBER_ID}/messages",
                    json={
                        "messaging_product": "whatsapp",
                        "status": "read",
                        "message_id": msg_id,
                    },
                    headers={"Authorization": f"Bearer {WA_ACCESS_TOKEN}"},
                )
                logger.info("WA_MARK_READ msg_id=%s status=%d", msg_id, r.status_code)

            # 2. Typing indicator — formato corretto Cloud API
            r2 = await client.post(
                f"{WA_API_BASE}/{WA_PHONE_NUMBER_ID}/messages",
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": wa_id,
                    "type": "action",
                    "action": {
                        "type": "typing",
                        "typing": {"is_typing": True},
                    },
                },
                headers={"Authorization": f"Bearer {WA_ACCESS_TOKEN}"},
            )
            logger.info("WA_TYPING_SENT wa_id=%s status=%d body=%s",
                        wa_id, r2.status_code, r2.text[:200])
    except Exception as e:
        logger.warning("WA_TYPING_ERROR wa_id=%s err=%s", wa_id, e)


async def send_image(wa_id: str, image_url: str, caption: str = "") -> bool:
    """Invia un'immagine da URL pubblico."""
    if not WA_ACCESS_TOKEN or not WA_PHONE_NUMBER_ID:
        return False
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "image",
        "image": {"link": image_url},
    }
    if caption:
        payload["image"]["caption"] = caption[:1024]  # type: ignore[index]
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            res = await client.post(
                f"{WA_API_BASE}/{WA_PHONE_NUMBER_ID}/messages",
                json=payload,
                headers={"Authorization": f"Bearer {WA_ACCESS_TOKEN}"},
            )
            return res.status_code == 200
        except Exception as e:
            logger.error("WA_SEND_IMAGE_ERROR wa_id=%s err=%s", wa_id, e)
            return False


async def download_media(media_id: str) -> tuple[bytes | None, str]:
    """Scarica un media da WhatsApp tramite media_id. Ritorna (bytes, mime_type)."""
    if not WA_ACCESS_TOKEN:
        return None, ""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            # Step 1: ottieni URL del media
            res = await client.get(
                f"{WA_API_BASE}/{media_id}",
                headers={"Authorization": f"Bearer {WA_ACCESS_TOKEN}"},
            )
            info = res.json()
            url  = info.get("url", "")
            mime = info.get("mime_type", "application/octet-stream")
            if not url:
                return None, ""
            # Step 2: scarica il contenuto
            res2 = await client.get(
                url,
                headers={"Authorization": f"Bearer {WA_ACCESS_TOKEN}"},
            )
            return res2.content, mime
        except Exception as e:
            logger.error("WA_DOWNLOAD_ERROR media_id=%s err=%s", media_id, e)
            return None, ""


# ── Auth helpers ─────────────────────────────────────────────────────────────

async def _login(email: str, password: str) -> str | None:
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(f"{GENESI_URL}/auth/login",
                                json={"email": email, "password": password})
        if res.status_code == 200:
            return res.json().get("access_token")
    return None


async def _auto_refresh(wa_id: str, session: dict) -> str | None:
    """Rinnova silenziosamente il token usando le credenziali salvate in sessione."""
    email    = session.get("email", "")
    password = session.get("password", "")
    if not email or not password:
        return None
    new_token = await _login(email, password)
    if new_token:
        session["token"] = new_token
        await storage.save(_session_key(wa_id), session)
        logger.info("WA_TOKEN_REFRESHED wa_id=%s", wa_id)
    return new_token


async def _register(email: str, password: str) -> bool:
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(f"{GENESI_URL}/api/auth/register",
                                json={"email": email, "password": password})
        return res.status_code in (200, 201)


# ── Genesi API calls ─────────────────────────────────────────────────────────

async def _chat(token: str, message: str, city: str = "", platform: str = "whatsapp") -> str:
    if city and _WEATHER_RE.search(message) and city.lower() not in message.lower():
        message = f"{message} (sono a {city})"
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            f"{GENESI_URL}/api/chat",
            json={"message": message, "platform": platform},
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
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            f"{GENESI_URL}/api/upload/",
            files={"file": (filename, data, content_type)},
            headers={"Authorization": f"Bearer {token}"},
        )
        if res.status_code == 200:
            d = res.json()
            return d.get("analysis") or d.get("summary") or d.get("message") or ""
        if res.status_code == 401:
            return "__TOKEN_EXPIRED__"
        return ""


async def _transcribe(token: str, audio_data: bytes,
                      content_type: str = "audio/ogg") -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            f"{GENESI_URL}/api/stt/",
            files={"audio": ("voice.ogg", audio_data, content_type)},
            headers={"Authorization": f"Bearer {token}"},
        )
        if res.status_code == 200:
            return res.json().get("text", "")
        if res.status_code == 401:
            return "__TOKEN_EXPIRED__"
    return ""


# ── Risposta con immagini ────────────────────────────────────────────────────

async def _send_response(wa_id: str, reply: str):
    """Invia la risposta: se contiene URL immagini le manda come immagini WhatsApp."""
    md_urls  = _IMG_MD_RE.findall(reply)
    raw_urls = _IMG_URL_RE.findall(reply)
    img_urls = md_urls + [u for u in raw_urls if u not in md_urls]

    if img_urls:
        clean_text = _IMG_MD_RE.sub("", reply).strip()
        clean_text = _IMG_URL_RE.sub("", clean_text).strip()

        for url in img_urls[:3]:
            sent = await send_image(wa_id, url, caption=clean_text if clean_text else "")
            if not sent:
                await send_message(wa_id, reply)
            clean_text = ""
        return

    await send_message(wa_id, reply)


# ── Post-login ───────────────────────────────────────────────────────────────

async def _complete_login(wa_id: str, token: str, email: str, password: str = ""):
    city = await _get_city(token)
    session = {"token": token, "email": email, "password": password, "city": city,
               "state": STATE_IDLE, "welcomed": False}
    if not city:
        session["state"] = STATE_AWAIT_CITY
        await storage.save(_session_key(wa_id), session)
        await send_message(wa_id, _WELCOME_MSG + "\n\n" + _WELCOME_CITY_PREAMBLE)
    else:
        session["welcomed"] = True
        await storage.save(_session_key(wa_id), session)
        await send_message(wa_id, _WELCOME_MSG)


# ── Verifica webhook (richiesta Meta al setup) ───────────────────────────────

def get_wa_link() -> str:
    return f"https://wa.me/{WA_PHONE_NUMBER}"


async def link_webapp_session(wa_id: str, token: str, email: str = "", password: str = ""):
    """Salva il token (ottenuto dalla webapp) nella sessione WhatsApp dell'utente."""
    city = await _get_city(token)
    session = await storage.load(_session_key(wa_id)) or {}
    session.update({
        "token": token,
        "email": email,
        "password": password,
        "city": city,
        "state": STATE_IDLE,
        "welcomed": True,
    })
    await storage.save(_session_key(wa_id), session)
    logger.info("WA_SESSION_LINKED wa_id=%s email=%s", wa_id, email)
    await send_message(wa_id,
        "✅ Accesso effettuato! Sono pronta.\n\nScrivimi pure 💬")


def verify_webhook(mode: str, token: str, challenge: str) -> str | None:
    """Verifica la challenge Meta. Ritorna la challenge se valida, None altrimenti."""
    if mode == "subscribe" and token == WA_VERIFY_TOKEN:
        logger.info("WA_WEBHOOK_VERIFIED")
        return challenge
    logger.warning("WA_WEBHOOK_VERIFY_FAILED mode=%s token=%s", mode, token)
    return None


# ── Main message handler ─────────────────────────────────────────────────────

async def handle_update(payload: dict):
    """Processa un update WhatsApp (chiamato dal webhook in background)."""
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value    = change.get("value", {})
                messages = value.get("messages", [])
                contacts = value.get("contacts", [])

                name_map = {c["wa_id"]: c.get("profile", {}).get("name", "")
                            for c in contacts}

                # Rileva se siamo in un gruppo (group_id presente nei metadati WA)
                raw_group_id = value.get("metadata", {}).get("group_id", "")
                is_group = bool(raw_group_id)

                for msg in messages:
                    msg_is_group = is_group or bool(
                        msg.get("context", {}).get("id", "").endswith("@g.us")
                        or msg.get("group", {})
                    )
                    # Usa group_id come chat_id (hash stabile in int per storage)
                    gid = raw_group_id or msg.get("context", {}).get("id", "")
                    chat_id = abs(hash(gid)) % (10**9) if gid else 0
                    await _process_message(msg, name_map, is_group=msg_is_group, chat_id=chat_id)

    except Exception as e:
        logger.error("WA_HANDLE_UPDATE_ERROR err=%s", e)


async def _process_message(msg: dict, name_map: dict, is_group: bool = False, chat_id: int = 0):
    try:
        wa_id      = msg.get("from", "")
        msg_id     = msg.get("id", "")   # ID messaggio per typing + mark-as-read
        msg_type   = msg.get("type", "")
        first_name = name_map.get(wa_id, "").split()[0] if name_map.get(wa_id) else ""

        # Estrai contenuti in base al tipo
        text     = ""
        caption  = ""
        photo_id = ""
        voice_id = ""
        mime_type_media = ""
        doc_id   = ""
        doc_name = ""

        if msg_type == "text":
            text = msg.get("text", {}).get("body", "").strip()
        elif msg_type == "image":
            img    = msg.get("image", {})
            photo_id = img.get("id", "")
            caption  = img.get("caption", "").strip()
            mime_type_media = img.get("mime_type", "image/jpeg")
        elif msg_type in ("audio", "voice"):
            media = msg.get(msg_type, {})
            voice_id = media.get("id", "")
            mime_type_media = media.get("mime_type", "audio/ogg")
        elif msg_type == "document":
            doc    = msg.get("document", {})
            doc_id   = doc.get("id", "")
            doc_name = doc.get("filename", "document")
            caption  = doc.get("caption", "").strip()
            mime_type_media = doc.get("mime_type", "application/octet-stream")
        else:
            # Tipo non gestito (sticker, location, ecc.)
            logger.info("WA_UNSUPPORTED_TYPE wa_id=%s type=%s", wa_id, msg_type)
            await send_message(wa_id,
                "Questo tipo di messaggio non è ancora supportato. "
                "Scrivimi in testo, o inviami foto, vocali o documenti.")
            return

        session = await storage.load(_session_key(wa_id)) or {}
        state   = session.get("state", STATE_IDLE)

        # ── Comandi (testo che inizia con /) ──────────────────────────────────
        if text in ("/start", "ciao", "start"):
            if session.get("token"):
                name_part = f" {first_name}" if first_name else ""
                await send_message(wa_id,
                    f"Bentornato{name_part}! Sono qui 👋\n\n"
                    f"Scrivimi, mandami foto o vocali.\n"
                    f"Webapp completa: {_WEBAPP_LINK}")
            else:
                session = {"state": STATE_IDLE}
                await storage.save(_session_key(wa_id), session)
                await send_message(wa_id,
                    f"Ciao {first_name}! 👋 Sono *Genesi*, il tuo assistente AI personale.\n\n"
                    f"Per usarmi hai bisogno di un account:\n\n"
                    f"• Hai già un account? Scrivi: *accedi*\n"
                    f"  oppure: {_WEBAPP_LINK}login?from=whatsapp&wa_id={wa_id}\n\n"
                    f"• Nuovo? Scrivi: *registrati*\n"
                    f"  oppure: {_WEBAPP_LINK}register?from=whatsapp&wa_id={wa_id}")
            return

        if text.lower() in ("/login", "/accedi", "accedi", "login"):
            session = {"state": STATE_AWAIT_EMAIL}
            await storage.save(_session_key(wa_id), session)
            await send_message(wa_id, "Inserisci la tua email:")
            return

        if text.lower() in ("/registrati", "/nuovo", "registrati", "nuovo"):
            session = {"state": STATE_AWAIT_REG_EMAIL}
            await storage.save(_session_key(wa_id), session)
            await send_message(wa_id, "Scegli un'email per il tuo account:")
            return

        if text.lower() in ("/logout", "logout", "esci"):
            await storage.save(_session_key(wa_id), {"state": STATE_IDLE})
            await send_message(wa_id, "Disconnesso. Scrivi *accedi* per rientrare.")
            return

        # ── Flusso LOGIN ──────────────────────────────────────────────────────
        if state == STATE_AWAIT_EMAIL:
            session["pending_email"] = text
            session["state"] = STATE_AWAIT_PASSWORD
            await storage.save(_session_key(wa_id), session)
            await send_message(wa_id, "Inserisci la tua password:")
            return

        if state == STATE_AWAIT_PASSWORD:
            email, password = session.get("pending_email", ""), text
            await send_typing(wa_id, msg_id)
            token = await _login(email, password)
            if not token:
                session.update({"state": STATE_AWAIT_EMAIL, "pending_email": None})
                await storage.save(_session_key(wa_id), session)
                await send_message(wa_id,
                    "Credenziali non valide. Reinserisci la tua email:")
                return
            logger.info("WA_LOGIN_OK wa_id=%s email=%s", wa_id, email)
            await _complete_login(wa_id, token, email, password)
            return

        # ── Flusso REGISTRAZIONE ──────────────────────────────────────────────
        if state == STATE_AWAIT_REG_EMAIL:
            session["pending_email"] = text
            session["state"] = STATE_AWAIT_REG_PASSWORD
            await storage.save(_session_key(wa_id), session)
            await send_message(wa_id, "Scegli una password (min 8 caratteri):")
            return

        if state == STATE_AWAIT_REG_PASSWORD:
            email, password = session.get("pending_email", ""), text
            await send_typing(wa_id, msg_id)
            ok = await _register(email, password)
            if not ok:
                session["state"] = STATE_AWAIT_REG_EMAIL
                await storage.save(_session_key(wa_id), session)
                await send_message(wa_id,
                    "Registrazione non riuscita. Forse l'email è già in uso.\n"
                    "Inserisci un'altra email:")
                return
            token = await _login(email, password)
            logger.info("WA_REGISTER_OK wa_id=%s email=%s", wa_id, email)
            await _complete_login(wa_id, token, email, password)
            return

        # ── Città mancante ────────────────────────────────────────────────────
        if state == STATE_AWAIT_CITY and text:
            city = text.strip().title()
            await _save_city(session["token"], city)
            session.update({"city": city, "state": STATE_IDLE, "welcomed": True})
            await storage.save(_session_key(wa_id), session)
            pending = session.pop("pending_message", None)
            if pending:
                await send_message(wa_id, "Perfetto! Rispondo subito...")
                reply = await _chat(session["token"], pending, city=city)
                await _send_response(wa_id, reply)
            else:
                await send_message(wa_id,
                    f"Perfetto, ti ricordo a {city}! Scrivimi pure.")
            return

        # ── Verifica login ────────────────────────────────────────────────────
        token = session.get("token")
        if not token:
            await send_message(wa_id,
                "Per chattare con me hai bisogno di un account.\n\n"
                f"• Già registrato? Scrivi: *accedi*\n"
                f"  oppure: {_WEBAPP_LINK}login?from=whatsapp&wa_id={wa_id}\n\n"
                f"• Nuovo? Scrivi: *registrati*\n"
                f"  oppure: {_WEBAPP_LINK}register?from=whatsapp&wa_id={wa_id}")
            return

        city = session.get("city", "")

        # ── LOGICA GRUPPO ─────────────────────────────────────────────────────
        if is_group and first_name:
            from core.telegram_group_memory import (
                update_member_seen, append_raw_message, build_group_context,
                append_group_history, record_group_observation,
                consolidate_group_insights_if_needed, extract_family_relationship,
                sync_family_to_owner,
            )
            # Aggiorna profilo membro ad ogni messaggio
            asyncio.create_task(update_member_seen(abs(hash(wa_id)) % (10**9), first_name))
            # Estrai relazioni familiari
            asyncio.create_task(extract_family_relationship(wa_id, first_name, (text or caption), "whatsapp"))
            # Salva nel buffer grezzo (tutti i messaggi, anche quelli ignorati)
            msg_text = (text or caption or "").strip()
            if msg_text and chat_id:
                asyncio.create_task(append_raw_message(chat_id, abs(hash(wa_id)) % (10**9), first_name, msg_text))

        # ── FILTRO GRUPPI ─────────────────────────────────────────────────────
        if is_group and not _group_should_respond(text, caption=caption):
            logger.info("WA_GROUP_SKIP wa_id=%s msg=%.60s",
                        wa_id, f"{text} {caption}".strip())
            return

        async def _do_chat(message: str) -> str:
            nonlocal token, session
            # Gruppi WhatsApp: inietta contesto famiglia e usa platform whatsapp_group
            if is_group and chat_id and first_name:
                try:
                    from core.telegram_group_memory import build_group_context
                    group_ctx = await build_group_context(chat_id, abs(hash(wa_id)) % (10**9), first_name)
                    message = (
                        f"{message}\n\n"
                        f"[GRUPPO FAMILIARE: scrive {first_name}. "
                        f"Sei un membro della famiglia. Usa il nome {first_name}.]\n"
                        f"{group_ctx}"
                    )
                except Exception:
                    pass
            platform = "whatsapp_group" if is_group else "whatsapp"
            reply = await _chat(token, message, city=city, platform=platform)
            if reply == "__TOKEN_EXPIRED__":
                new_token = await _auto_refresh(wa_id, session)
                if new_token:
                    token = new_token
                    reply = await _chat(token, message, city=city, platform=platform)
                else:
                    reply = "__AUTH_FAILED__"
            # Apprendimento di gruppo in background
            if is_group and reply not in ("__TOKEN_EXPIRED__", "__AUTH_FAILED__") and chat_id:
                from core.telegram_group_memory import (
                    append_group_history, record_group_observation,
                    consolidate_group_insights_if_needed,
                )
                orig_text = (text or caption or "").strip()
                asyncio.create_task(append_group_history(chat_id, abs(hash(wa_id)) % (10**9), first_name, orig_text, reply))
                asyncio.create_task(record_group_observation(chat_id, abs(hash(wa_id)) % (10**9), first_name, orig_text, reply))
                asyncio.create_task(consolidate_group_insights_if_needed(chat_id))
            return reply

        async def _handle_reply(reply: str) -> bool:
            if reply in ("__AUTH_FAILED__", "__TOKEN_EXPIRED__"):
                saved_email = session.get("email", "")
                if saved_email:
                    # Abbiamo l'email: chiediamo solo la password
                    session["pending_email"] = saved_email
                    session["state"] = STATE_AWAIT_PASSWORD
                    await storage.save(_session_key(wa_id), session)
                    await send_message(wa_id,
                        f"Sessione scaduta. Inserisci la tua password per rientrare:")
                else:
                    session["state"] = STATE_AWAIT_EMAIL
                    await storage.save(_session_key(wa_id), session)
                    await send_message(wa_id,
                        "Sessione scaduta. Inserisci la tua email:")
                return False
            await _send_response(wa_id, reply)
            return True

        # ── FOTO ──────────────────────────────────────────────────────────────
        if photo_id:
            await send_typing(wa_id, msg_id)
            img_bytes, mime = await download_media(photo_id)
            if not img_bytes:
                await send_message(wa_id, "Non riuscito a scaricare la foto.")
                return
            ext = "jpg" if "jpeg" in mime else mime.split("/")[-1]
            analysis = await _upload_file(token, img_bytes, f"photo.{ext}", mime)
            if analysis == "__TOKEN_EXPIRED__":
                new_token = await _auto_refresh(wa_id, session)
                if new_token:
                    token = new_token
                    analysis = await _upload_file(token, img_bytes, f"photo.{ext}", mime)
                else:
                    await _handle_reply("__AUTH_FAILED__")
                    return
            user_msg  = caption or "Analizza questa immagine che ti ho inviato."
            if analysis:
                user_msg = f"{user_msg}\n\n[Contenuto immagine: {analysis}]"
            reply = await _do_chat(user_msg)
            if not await _handle_reply(reply):
                return
            logger.info("WA_PHOTO_OK wa_id=%s", wa_id)
            return

        # ── DOCUMENTO ─────────────────────────────────────────────────────────
        if doc_id:
            await send_typing(wa_id, msg_id)
            doc_bytes, mime = await download_media(doc_id)
            if not doc_bytes:
                await send_message(wa_id, "Non riuscito a scaricare il documento.")
                return
            analysis = await _upload_file(token, doc_bytes, doc_name, mime)
            if analysis == "__TOKEN_EXPIRED__":
                new_token = await _auto_refresh(wa_id, session)
                if new_token:
                    token = new_token
                    analysis = await _upload_file(token, doc_bytes, doc_name, mime)
                else:
                    await _handle_reply("__AUTH_FAILED__")
                    return
            user_msg  = caption or f"Ho inviato il documento: {doc_name}."
            if analysis:
                user_msg = f"{user_msg}\n\n[Contenuto: {analysis[:500]}]"
            reply = await _do_chat(user_msg)
            if not await _handle_reply(reply):
                return
            logger.info("WA_DOCUMENT_OK wa_id=%s filename=%s", wa_id, doc_name)
            return

        # ── VOCALE ────────────────────────────────────────────────────────────
        if voice_id:
            await send_typing(wa_id, msg_id)
            audio_bytes, mime = await download_media(voice_id)
            if not audio_bytes:
                await send_message(wa_id,
                    "Non riuscito a scaricare il vocale.")
                return
            transcription = await _transcribe(token, audio_bytes, mime or "audio/ogg")
            if transcription == "__TOKEN_EXPIRED__":
                new_token = await _auto_refresh(wa_id, session)
                if new_token:
                    token = new_token
                    transcription = await _transcribe(token, audio_bytes, mime or "audio/ogg")
                else:
                    await _handle_reply("__AUTH_FAILED__")
                    return
            if not transcription:
                await send_message(wa_id,
                    "Non sono riuscita a capire il vocale. Prova a scrivere.")
                return
            await send_message(wa_id, f"🎤 _{transcription}_")
            reply = await _do_chat(transcription)
            if not await _handle_reply(reply):
                return
            logger.info("WA_VOICE_OK wa_id=%s transcription=%s",
                        wa_id, transcription[:50])
            return

        # ── TESTO ─────────────────────────────────────────────────────────────
        if not text:
            return

        if _WEATHER_RE.search(text) and not city:
            session["state"]           = STATE_AWAIT_CITY
            session["pending_message"] = text
            await storage.save(_session_key(wa_id), session)
            await send_message(wa_id,
                "Per il meteo ho bisogno di sapere dove sei. "
                "In quale città ti trovi?")
            return

        await send_typing(wa_id, msg_id)
        reply = await _do_chat(text)
        await _handle_reply(reply)

    except Exception as e:
        logger.error("WA_PROCESS_MESSAGE_ERROR err=%s", e)
