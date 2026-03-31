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
import hashlib
import hmac
import json
import logging
import os
import re
import time
import httpx
from core.storage import storage
from core.simple_chat import strip_group_ctx as _strip_group_ctx
from core.telegram_group_memory import (
    update_member_seen, get_member_city, save_member_city,
    build_group_context, append_group_history, append_raw_message, get_raw_messages,
    record_group_observation, consolidate_group_insights_if_needed,
    summarize_group_discussion_if_needed,
    extract_family_relationship,
    sync_family_to_owner,
)

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API   = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
TELEGRAM_FILES = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}"
GENESI_URL     = "http://localhost:8000"

# Credenziali pre-configurate per i gruppi (auto-login senza /login manuale)
_GROUP_EMAIL    = os.getenv("TELEGRAM_GROUP_EMAIL", "")
_GROUP_PASSWORD = os.getenv("TELEGRAM_GROUP_PASSWORD", "")
# Segreto per derivare le password degli account virtuali dei membri del gruppo
_GROUP_MEMBER_SECRET = os.getenv("TELEGRAM_GROUP_MEMBER_SECRET", "genesi-family-group-2026")

# Cache token per-membro (in memoria, si rinnova automaticamente)
_MEMBER_TOKENS: dict[int, str] = {}
# user_id del proprietario del gruppo (decodificato dal GROUP_EMAIL token, cached)
_OWNER_USER_ID: str = ""

# Regex meteo
_WEATHER_RE = re.compile(
    r'\b(meteo|tempo|temperatura|piogge?|sole|vento|previsioni?|forecast|'
    r'caldo|freddo|nebbia|neve|nuvoloso|sereno|umidità)\b',
    re.IGNORECASE
)

_GENESI_RE = re.compile(r'\bgenesi\b', re.IGNORECASE)

# Stato conversazione per gruppo: traccia con chi Genesi stava parlando di recente
# { chat_id: {"from_id": int, "ts": float, "count": int} }
_GROUP_CONV_STATE: dict[int, dict] = {}

_GROUP_INTERVENE_PROMPT = """\
Sei il filtro di intervento di Genesi in un gruppo familiare su Telegram.
Genesi è discreta: ascolta tutto in silenzio e interviene RARAMENTE, solo nelle situazioni indicate.

Leggi i messaggi recenti del gruppo e il messaggio attuale. Decidi se Genesi deve rispondere.

RISPONDI "SI" SOLO se il messaggio attuale rientra in UNO di questi casi:
1. INVOCATA: qualcuno cita Genesi per nome, la taglia o le pone una domanda diretta
2. BUONA NOTIZIA: qualcuno condivide una notizia bella, un successo, un traguardo, qualcosa di speciale da celebrare (UNA VOLTA per evento)
3. CONTINUAZIONE: è un follow-up diretto a una risposta appena data da Genesi (stessa conversazione, < 5 min)

RISPONDI "NO" in tutti gli altri casi, incluso:
- Conversazioni, aggiornamenti, discussioni, battute tra i membri
- Domande rivolte ad altri membri
- Momenti difficili o sfogo (Genesi resta in silenzio — non si intromette nel dolore altrui senza essere chiamata)
- Qualsiasi cosa che sia chiaramente uno scambio privato tra persone della famiglia

Il dubbio va verso NO. Genesi non deve partecipare a ogni cosa.

Rispondi SOLO con JSON: {"intervieni": true, "motivo": "ragione breve"} oppure {"intervieni": false, "motivo": "ragione breve"}
"""


async def _group_should_intervene(
    text: str, caption: str, chat_id: int, from_id: int, first_name: str,
    bot_username: str = "", bot_mentioned: bool = False
) -> bool:
    """
    Decide con LLM se Genesi deve intervenire nel gruppo.
    Fast-path per mention/nome diretti. LLM per tutto il resto.
    """
    combined = f"{text} {caption}".strip()
    if not combined:
        return False

    # Fast-path: menzione diretta (@bot o nome) → sempre sì
    if bot_mentioned:
        return True
    if bot_username and f"@{bot_username.lower()}" in combined.lower():
        return True
    if _GENESI_RE.search(combined):
        return True

    # Fast-path: saluto al gruppo → sempre sì
    _GREETINGS = ("buongiorno", "buonasera", "buonanotte", "ciao a tutti", "salve", "hey")
    combined_lower = combined.lower()
    if any(g in combined_lower for g in _GREETINGS):
        return True

    # Fast-path: celebrazione/buona notizia → sempre sì (emoji festive o keyword di traguardo)
    _CELEBRATION_EMOJIS = ("🎉", "🎊", "🥳", "🎈", "🥂", "🍾", "🎂", "🏆", "🎁")
    _GOOD_NEWS_KW = (
        "habemus", "ce l'ho fatta", "ce la fatta", "ho preso", "ho comprato",
        "è arrivat", "arrivata la", "arrivato il", "finalmente", "ho trovato",
        "ho vinto", "abbiamo vinto", "promozione", "promosso", "promossa",
        "laurea", "diploma", "compleanno", "auguri",
    )
    if any(e in combined for e in _CELEBRATION_EMOJIS):
        return True
    if any(kw in combined_lower for kw in _GOOD_NEWS_KW):
        return True

    # Fast-path: messaggio troppo corto e senza punto interrogativo → probabile scambio tra membri
    if len(combined) < 8 and "?" not in combined:
        return False

    # Fast-path: continuazione di conversazione attiva con questo utente (< 3 min)
    state = _GROUP_CONV_STATE.get(chat_id, {})
    if state.get("from_id") == from_id and time.time() - state.get("ts", 0) < 180:
        return True

    # LLM decision
    try:
        from core.llm_service import llm_service
        raw_msgs = await get_raw_messages(chat_id, limit=12)
        history_text = ""
        if raw_msgs:
            history_text = "Messaggi recenti nel gruppo (tutti, non solo quelli con Genesi):\n" + "\n".join(
                f"  {m.get('first_name','?')}: {m.get('text','')[:100]}"
                for m in raw_msgs[:-1]  # escludi l'ultimo che è il messaggio attuale
            ) + "\n\n"

        user_msg = (
            f"{history_text}"
            f"Messaggio attuale di {first_name}: {combined}"
        )
        raw = await llm_service._call_model(
            "openai/gpt-4o-mini",
            _GROUP_INTERVENE_PROMPT,
            user_msg,
            user_id="group-filter",
            route="memory",
        )
        if not raw:
            return False
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        parsed = json.loads(clean.strip())
        intervieni = parsed.get("intervieni", False)
        motivo     = parsed.get("motivo", "")
        logger.info("GROUP_INTERVENE_DECISION chat_id=%s from=%s intervieni=%s motivo=%s",
                    chat_id, first_name, intervieni, motivo)
        return bool(intervieni)
    except Exception as exc:
        logger.debug("GROUP_INTERVENE_ERROR err=%s", exc)
        return False

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


def _group_user_city_key(from_id: int) -> str:
    return f"telegram:group_user:{from_id}:city"


async def _get_group_user_city(from_id: int) -> str:
    return await storage.load(_group_user_city_key(from_id), default="") or ""


async def _save_group_user_city(from_id: int, city: str):
    await storage.save(_group_user_city_key(from_id), city)


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
    global _BOT_USERNAME
    async with httpx.AsyncClient(timeout=10) as client:
        # Scopri username del bot
        try:
            me = await client.get(f"{TELEGRAM_API}/getMe")
            _BOT_USERNAME = me.json().get("result", {}).get("username", "")
            logger.info("TELEGRAM_BOT_USERNAME=%s", _BOT_USERNAME)
        except Exception:
            pass
        # Registra webhook
        res = await client.post(f"{TELEGRAM_API}/setWebhook",
                                json={"url": webhook_url,
                                      "allowed_updates": ["message", "my_chat_member"]})
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


async def _auto_refresh(chat_id: int, session: dict) -> str | None:
    """Rinnova silenziosamente il token usando le credenziali salvate in sessione.
    Ritorna il nuovo token se ok, None se le credenziali non sono più valide."""
    email    = session.get("email", "")
    password = session.get("password", "")
    if not email or not password:
        return None
    new_token = await _login(email, password)
    if new_token:
        session["token"] = new_token
        await storage.save(_session_key(chat_id), session)
        logger.info("TELEGRAM_TOKEN_REFRESHED chat_id=%s", chat_id)
    return new_token


async def _register(email: str, password: str) -> bool:
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(f"{GENESI_URL}/auth/register",
                                json={"email": email, "password": password})
        return res.status_code in (200, 201)


def _member_email(from_id: int) -> str:
    """Email virtuale deterministica per un membro del gruppo Telegram."""
    return f"telegram_{from_id}@genesi.group"


def _member_password(from_id: int) -> str:
    """Password deterministica derivata da from_id + segreto condiviso."""
    sig = hmac.new(
        _GROUP_MEMBER_SECRET.encode(),
        str(from_id).encode(),
        hashlib.sha256
    ).hexdigest()[:24]
    return f"Gm{sig}"


async def _get_or_create_member_token(from_id: int, first_name: str) -> str | None:
    """
    Restituisce un token JWT valido per il membro del gruppo.
    Se l'account non esiste lo crea automaticamente (silent registration).
    Usa la cache in-memory _MEMBER_TOKENS per evitare login ripetuti.
    """
    # Cache hit
    if from_id in _MEMBER_TOKENS:
        return _MEMBER_TOKENS[from_id]

    email    = _member_email(from_id)
    password = _member_password(from_id)

    # Prova login
    token = await _login(email, password)
    if not token:
        # Account non esiste: crealo
        await _register(email, password)
        # Imposta il nome nel profilo
        token = await _login(email, password)
        if token:
            # Salva il nome nel profilo Genesi del membro direttamente sullo storage
            try:
                user_id = _decode_user_id(token)
                if user_id:
                    profile = await storage.load(f"profile:{user_id}", default={})
                    if not profile.get("name"):
                        profile["name"] = first_name
                        await storage.save(f"profile:{user_id}", profile)
            except Exception:
                pass
            logger.info("GROUP_MEMBER_ACCOUNT_CREATED from_id=%s name=%s email=%s",
                        from_id, first_name, email)

    if token:
        _MEMBER_TOKENS[from_id] = token
    return token


async def _refresh_member_token(from_id: int) -> str | None:
    """Rinnova il token del membro rimuovendolo dalla cache e ri-autenticando."""
    _MEMBER_TOKENS.pop(from_id, None)
    member = await get_member(from_id)
    first_name = member.get("first_name", "")
    return await _get_or_create_member_token(from_id, first_name)


async def _get_owner_user_id() -> str:
    """Restituisce il user_id del proprietario del gruppo (da GROUP_EMAIL), con cache."""
    global _OWNER_USER_ID
    if _OWNER_USER_ID:
        return _OWNER_USER_ID
    if not _GROUP_EMAIL or not _GROUP_PASSWORD:
        return ""
    token = await _login(_GROUP_EMAIL, _GROUP_PASSWORD)
    if token:
        uid = _decode_user_id(token)
        if uid:
            _OWNER_USER_ID = uid
    return _OWNER_USER_ID


async def _sync_family_background(chat_id: int):
    """Task background: sincronizza profili famiglia nel contesto privato del proprietario."""
    owner_uid = await _get_owner_user_id()
    if owner_uid:
        await sync_family_to_owner(chat_id, owner_uid)


# ── Genesi API calls ───────────────────────────────────────────────────────────

async def _chat(token: str, message: str, city: str = "", is_group: bool = False) -> str:
    if city and _WEATHER_RE.search(message) and city.lower() not in message.lower():
        message = f"{message} (sono a {city})"
    platform = "telegram_group" if is_group else "telegram"
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
    """Carica un file su Genesi e ritorna il testo di analisi.
    Ritorna '__TOKEN_EXPIRED__' se il token è scaduto (401)."""
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            f"{GENESI_URL}/api/upload/",
            files={"file": (filename, data, content_type)},
            headers={"Authorization": f"Bearer {token}"},
        )
        if res.status_code == 200:
            d = res.json()
            return d.get("analysis") or d.get("summary") or d.get("message") or ""
        elif res.status_code == 401:
            return "__TOKEN_EXPIRED__"
        return ""


async def _transcribe(token: str, audio_data: bytes,
                      content_type: str = "audio/ogg") -> str:
    """Invia audio all'endpoint STT e ritorna il testo trascritto.
    Ritorna '__TOKEN_EXPIRED__' se il token è scaduto (401)."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post(
                f"{GENESI_URL}/api/stt/",
                files={"audio": ("voice.ogg", audio_data, content_type)},
                headers={"Authorization": f"Bearer {token}"},
            )
            if res.status_code == 200:
                data = res.json()
                text = data.get("text", "")
                logger.info("TELEGRAM_STT_OK status=200 text_len=%d stt_status=%s",
                            len(text), data.get("stt_status", "ok"))
                return text
            elif res.status_code == 401:
                return "__TOKEN_EXPIRED__"
            else:
                logger.warning("TELEGRAM_STT_HTTP_ERROR status=%d body=%s",
                               res.status_code, res.text[:200])
    except Exception as e:
        logger.error("TELEGRAM_STT_EXCEPTION err=%s", e)
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


_WEBAPP_LINK  = "https://genesi.lucadigitale.eu/"
_WEBAPP_REG   = "https://genesi.lucadigitale.eu/register?from=telegram"
_BOT_USERNAME = ""   # popolato da set_webhook via getMe


def get_bot_link() -> str:
    return f"https://t.me/{_BOT_USERNAME}" if _BOT_USERNAME else "https://t.me/"


_WELCOME_MSG = (
    "✅ Collegato!\n\n"
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


# ── Post-login ─────────────────────────────────────────────────────────────────

async def _complete_login(chat_id: int, token: str, email: str, password: str = ""):
    city = await _get_city(token)
    session = {"token": token, "email": email, "password": password, "city": city,
               "state": STATE_IDLE, "welcomed": False}
    if not city:
        session["state"] = STATE_AWAIT_CITY
        await storage.save(_session_key(chat_id), session)
        await send_message(chat_id, _WELCOME_MSG + "\n\n" + _WELCOME_CITY_PREAMBLE)
    else:
        session["welcomed"] = True
        await storage.save(_session_key(chat_id), session)
        await send_message(chat_id, _WELCOME_MSG)


# ── Main update handler ────────────────────────────────────────────────────────

async def handle_update(update: dict):
    try:
        # Gestisci aggiunta del bot al gruppo
        if update.get("my_chat_member"):
            mcm = update["my_chat_member"]
            if mcm.get("new_chat_member", {}).get("status") == "member":
                gid = mcm["chat"]["id"]
                # Auto-login con credenziali pre-configurate
                if _GROUP_EMAIL and _GROUP_PASSWORD:
                    token = await _login(_GROUP_EMAIL, _GROUP_PASSWORD)
                    if token:
                        city = await _get_city(token)
                        session = {"token": token, "email": _GROUP_EMAIL,
                                   "password": _GROUP_PASSWORD, "city": city,
                                   "state": STATE_IDLE, "welcomed": True}
                        await storage.save(_session_key(gid), session)
                await send_message(gid,
                    "🎉 Eccomi qui! Sono *Genesi*, la vostra assistente AI!\n\n"
                    "Chiedete pure qualsiasi cosa — sono qui per tutti voi, "
                    "pronti a rispondere a ogni messaggio! 🚀\n\n"
                    "Chi sono? Sono un'AI che conosce ognuno di voi e si ricorda "
                    "di tutto quello che condividete con me. Parlatemi liberamente! 😊")
            return

        msg = update.get("message")
        if not msg:
            return

        chat_id    = msg["chat"]["id"]
        chat_type  = msg["chat"].get("type", "private")
        is_group   = chat_type in ("group", "supergroup")
        from_id    = msg.get("from", {}).get("id", chat_id)
        first_name = msg.get("from", {}).get("first_name", "")
        text       = msg.get("text", "").strip()
        photo      = msg.get("photo")       # lista di dimensioni
        voice      = msg.get("voice")       # messaggio vocale
        audio      = msg.get("audio")       # file audio generico
        document   = msg.get("document")    # documento (pdf, txt, ecc.)
        caption    = msg.get("caption", "").strip()

        # Aggiorna profilo membro del gruppo ad ogni messaggio
        if is_group and first_name:
            asyncio.create_task(update_member_seen(from_id, first_name))
            # Estrai relazioni familiari e aggiorna albero genealogico di Alfio
            asyncio.create_task(extract_family_relationship(str(from_id), first_name, text or caption, "telegram"))

        # ── Logica gruppi ──────────────────────────────────────────────────────
        _bot_mentioned = False  # True se il messaggio menzionava direttamente il bot
        if is_group:
            # Rileva menzione PRIMA di rimuoverla dal testo
            bot_mention = f"@{_BOT_USERNAME}" if _BOT_USERNAME else None
            if bot_mention and (bot_mention.lower() in (text or "").lower() or bot_mention.lower() in (caption or "").lower()):
                _bot_mentioned = True
            if bot_mention:
                text = text.replace(bot_mention, "").replace(bot_mention.lower(), "").strip()

        # Sessione condivisa per chat (chat_id sia in privato che in gruppo)
        session_uid = chat_id

        session = await storage.load(_session_key(session_uid)) or {}

        # Nei gruppi con credenziali pre-configurate: ignora stati login pendenti
        # (evita che vecchie sessioni STATE_AWAIT_PASSWORD trattino i messaggi come password)
        if is_group and _GROUP_EMAIL and not session.get("token"):
            session = {"state": STATE_IDLE}

        state   = session.get("state", STATE_IDLE)

        # ── Comandi globali ────────────────────────────────────────────────────
        if text == "/start":
            if session.get("token"):
                name_part = f" {first_name}" if first_name else ""
                webapp = _WEBAPP_LINK
                await send_message(chat_id,
                    f"Bentornato{name_part}! Sono qui 👋\n\n"
                    f"Scrivimi, mandami foto o vocali.\n"
                    f"Webapp completa: {webapp}")
            else:
                session = {"state": STATE_IDLE}
                await storage.save(_session_key(session_uid), session)
                await send_message(chat_id,
                    f"Ciao {first_name}! 👋 Sono *Genesi*, il tuo assistente AI personale.\n\n"
                    f"Per usarmi al massimo hai bisogno di un account.\n\n"
                    f"• Hai già un account? Scrivi /login\n"
                    f"• Nuovo? Registrati qui in Telegram: /registrati\n"
                    f"  oppure sul sito: {_WEBAPP_REG}")
            return

        if text in ("/login", "/accedi"):
            session = {"state": STATE_AWAIT_EMAIL}
            await storage.save(_session_key(session_uid), session)
            await send_message(chat_id, "Inserisci la tua email:")
            return

        if text in ("/registrati", "/nuovo"):
            session = {"state": STATE_AWAIT_REG_EMAIL}
            await storage.save(_session_key(session_uid), session)
            await send_message(chat_id, "Scegli un'email per il tuo account:")
            return

        if text == "/logout":
            await storage.save(_session_key(session_uid), {"state": STATE_IDLE})
            await send_message(chat_id, "Disconnesso. Usa /login per ricollegarti.")
            return

        # ── Flusso LOGIN ───────────────────────────────────────────────────────
        if state == STATE_AWAIT_EMAIL:
            session["pending_email"] = text
            session["state"] = STATE_AWAIT_PASSWORD
            await storage.save(_session_key(session_uid), session)
            await send_message(chat_id, "Inserisci la tua password:")
            return

        if state == STATE_AWAIT_PASSWORD:
            email, password = session.get("pending_email", ""), text
            await send_typing(chat_id)
            token = await _login(email, password)
            if not token:
                session.update({"state": STATE_AWAIT_EMAIL, "pending_email": None})
                await storage.save(_session_key(session_uid), session)
                await send_message(chat_id,
                    "Credenziali non valide. Reinserisci la tua email:")
                return
            logger.info("TELEGRAM_LOGIN_OK telegram_id=%s email=%s", chat_id, email)
            await _complete_login(session_uid, token, email, password)
            return

        # ── Flusso REGISTRAZIONE ───────────────────────────────────────────────
        if state == STATE_AWAIT_REG_EMAIL:
            session["pending_email"] = text
            session["state"] = STATE_AWAIT_REG_PASSWORD
            await storage.save(_session_key(session_uid), session)
            await send_message(chat_id, "Scegli una password (min 8 caratteri):")
            return

        if state == STATE_AWAIT_REG_PASSWORD:
            email, password = session.get("pending_email", ""), text
            await send_typing(chat_id)
            ok = await _register(email, password)
            if not ok:
                session["state"] = STATE_AWAIT_REG_EMAIL
                await storage.save(_session_key(session_uid), session)
                await send_message(chat_id,
                    "Registrazione non riuscita. Forse l'email è già in uso.\n"
                    "Inserisci un'altra email:")
                return
            token = await _login(email, password)
            logger.info("TELEGRAM_REGISTER_OK telegram_id=%s email=%s", chat_id, email)
            await _complete_login(session_uid, token, email, password)
            return

        # ── Città mancante ─────────────────────────────────────────────────────
        if state == STATE_AWAIT_CITY and text:
            # In gruppo: accetta la risposta solo dall'utente che ha triggerato la domanda
            pending_from = session.get("pending_city_from_id")
            if is_group and pending_from and pending_from != from_id:
                pass  # ignora risposta da altro utente, aspetta quello giusto
            else:
                city = text.strip().title()
                if is_group:
                    await save_member_city(from_id, city)
                else:
                    await _save_city(session["token"], city)
                    session["city"] = city
                session.update({"state": STATE_IDLE, "welcomed": True})
                session.pop("pending_city_from_id", None)
                await storage.save(_session_key(session_uid), session)
                pending = session.pop("pending_message", None)
                if pending:
                    await send_message(chat_id, f"Perfetto! Rispondo subito...")
                    reply = await _chat(session["token"], pending, city=city)
                    await _send_response(chat_id, reply)
                else:
                    name_part = f" {first_name}" if first_name else ""
                    await send_message(chat_id, f"Perfetto{name_part}, ti ricordo a {city}! Scrivimi pure.")
                return

        # ── Verifica login ─────────────────────────────────────────────────────
        if is_group:
            # In gruppo ogni membro ha il proprio account virtuale Genesi
            # con memoria, fatti personali ed episodi propri — come un utente reale.
            token = await _get_or_create_member_token(from_id, first_name)
            if not token:
                logger.error("GROUP_MEMBER_TOKEN_FAIL from_id=%s", from_id)
                return
        else:
            token = session.get("token")
            if not token:
                await send_message(chat_id,
                    "Per chattare con me hai bisogno di un account.\n\n"
                    "• Già registrato? /login\n"
                    "• Nuovo? /registrati (qui in Telegram)\n"
                    f"  oppure: {_WEBAPP_REG}")
                return

        # In gruppi la city è per-utente (from_id), non condivisa sull'intera chat
        if is_group:
            city = await get_member_city(from_id)
        else:
            city = session.get("city", "")

        # ── FILTRO GRUPPI (LLM-based) ──────────────────────────────────────────
        # Salva ogni messaggio nel buffer grezzo PRIMA di decidere se intervenire,
        # così il contesto includerà anche i messaggi a cui Genesi non ha risposto.
        if is_group:
            msg_text = (text or caption or "").strip()
            if msg_text:
                asyncio.create_task(
                    append_raw_message(chat_id, from_id, first_name, msg_text)
                )
            # Birthday: registra gruppo e collega pre-seed al from_id
            try:
                from core.birthday_service import (
                    register_known_group, link_preseed_to_member, try_extract_birthday
                )
                asyncio.create_task(register_known_group(chat_id, "telegram"))
                asyncio.create_task(link_preseed_to_member(from_id, first_name))
                if msg_text:
                    asyncio.create_task(try_extract_birthday(from_id, first_name, msg_text))
            except Exception:
                pass

        # Genesi decide autonomamente se e quando intervenire nel gruppo.
        if is_group:
            should = await _group_should_intervene(
                text, caption, chat_id, from_id, first_name,
                bot_username=_BOT_USERNAME, bot_mentioned=_bot_mentioned
            )
            if not should:
                logger.info("TELEGRAM_GROUP_SILENT chat_id=%s from=%s msg=%.60s",
                            chat_id, first_name, f"{text} {caption}".strip())
                return

        # In gruppi: appende il nome del mittente DOPO il messaggio per evitare
        # che il LLM mescoli il nome dell'account con quello del mittente.
        # Se il messaggio è solo emoji/reazione, segnala di rispondere brevemente.
        # Costruisce il contesto di gruppo arricchito (asincrono, cached per questo turno)
        _group_ctx_cache: list[str] = []

        async def _load_group_ctx() -> str:
            if not _group_ctx_cache:
                ctx = await build_group_context(chat_id, from_id, first_name)
                _group_ctx_cache.append(ctx)
            return _group_ctx_cache[0]

        def _group_msg(message: str, group_ctx: str = "") -> str:
            if not is_group or not first_name:
                return message
            only_emoji = all(
                ord(c) > 127 or c in (' ', '\n') for c in message.strip()
            )
            if only_emoji:
                return (
                    f"{message}\n\n"
                    f"[GRUPPO FAMILIARE: scrive {first_name}. "
                    f"Reazione/emoji — risposta brevissima, calore familiare, zero domande.]\n"
                    f"{group_ctx}"
                )
            return (
                f"{message}\n\n"
                f"[GRUPPO FAMILIARE: scrive {first_name}. "
                f"Sei un membro della famiglia — rispondi con calore e concretezza, "
                f"senza domande superflue. Usa il nome {first_name}.]\n"
                f"{group_ctx}"
            )

        async def _do_chat(message: str) -> str:
            """Chat con auto-refresh del token in caso di scadenza."""
            nonlocal token
            # Per i gruppi: arricchisce il messaggio con contesto di gruppo
            if is_group:
                group_ctx = await _load_group_ctx()
                enriched = _group_msg(message, group_ctx)
            else:
                enriched = _group_msg(message)
            reply = await _chat(token, enriched, city=city, is_group=is_group)
            if reply == "__TOKEN_EXPIRED__":
                if is_group:
                    new_token = await _refresh_member_token(from_id)
                else:
                    new_token = await _auto_refresh(session_uid, session)
                if new_token:
                    token = new_token
                    reply = await _chat(token, enriched, city=city, is_group=is_group)
                else:
                    reply = "__AUTH_FAILED__"
            # Automiglioramento + storia di gruppo in background
            if is_group and reply not in ("__TOKEN_EXPIRED__", "__AUTH_FAILED__"):
                asyncio.create_task(
                    append_group_history(chat_id, from_id, first_name, message, reply)
                )
                # Livello 1: osservazione lab_feedback_cycle ogni N messaggi
                asyncio.create_task(
                    record_group_observation(chat_id, from_id, first_name, message, reply)
                )
                # Livello 2a: consolidazione insights gruppo ogni 24h
                asyncio.create_task(
                    consolidate_group_insights_if_needed(chat_id)
                )
                # Livello 2b: riepilogo discussioni ogni 6h (memoria cross-sessione)
                asyncio.create_task(
                    summarize_group_discussion_if_needed(chat_id)
                )
                # Livello 3: cross-awareness — sincronizza profili famiglia verso il proprietario
                asyncio.create_task(_sync_family_background(chat_id))

                # Livello 4: memoria personale del mittente — episodi e fatti su testo pulito
                # Il testo originale (senza group_ctx arricchito) è già in `message`
                _raw_msg = _strip_group_ctx(message)
                if _raw_msg and len(_raw_msg) > 10:
                    _mem_msg  = _raw_msg
                    _mem_resp = reply
                    _mem_session_uid = session_uid  # uid del proprietario (Alfio) — il solo con memoria persistente

                    async def _tg_extract_episode(_mm=_mem_msg, _su=_mem_session_uid):
                        try:
                            import asyncio as _a
                            from core.episode_extractor import extract_episodes
                            from core.episode_memory import episode_memory as _em
                            ctx = f"{first_name}: {_mm}"
                            for ep in await extract_episodes(ctx, _su):
                                await _em.add(_su, ep)
                                logger.info("EPISODE_SAVED_TG_GROUP sender=%s text=%.60s", first_name, ep['text'])
                        except Exception:
                            pass
                    asyncio.create_task(_tg_extract_episode())

                    async def _tg_extract_facts(_mm=_mem_msg, _mr=_mem_resp, _su=_mem_session_uid):
                        try:
                            from core.personal_facts_service import personal_facts_service as _pfs
                            ctx = f"{first_name}: {_mm}"
                            await _pfs.extract_and_save(ctx, _mr, _su)
                        except Exception:
                            pass
                    asyncio.create_task(_tg_extract_facts())

                    async def _tg_global_memory(_su=_mem_session_uid):
                        try:
                            from core.global_memory_service import global_memory_service as _gms
                            await _gms.consolidate_if_needed(_su)
                        except Exception:
                            pass
                    asyncio.create_task(_tg_global_memory())

            return reply

        async def _handle_reply(reply: str) -> bool:
            """Invia la risposta; ritorna False se auth fallita definitivamente."""
            if reply == "__AUTH_FAILED__" or reply == "__TOKEN_EXPIRED__":
                await send_message(chat_id,
                    "Non riesco ad autenticarti. Usa /login per riconnetterti.")
                return False
            await _send_response(chat_id, reply)
            # Traccia con chi Genesi stava conversando (per il fast-path del filtro)
            if is_group:
                _GROUP_CONV_STATE[chat_id] = {
                    "from_id": from_id,
                    "ts":      time.time(),
                }
            return True

        # ── FOTO ───────────────────────────────────────────────────────────────
        if photo:
            await send_typing(chat_id)
            file_id   = photo[-1]["file_id"]  # qualità massima
            img_bytes = await download_file(file_id)
            if not img_bytes:
                await send_message(chat_id, "Non riuscito a scaricare la foto.")
                return

            analysis = await _upload_file(token, img_bytes, "photo.jpg", "image/jpeg")
            if analysis == "__TOKEN_EXPIRED__":
                new_token = await _auto_refresh(session_uid, session)
                if new_token:
                    token = new_token
                    analysis = await _upload_file(token, img_bytes, "photo.jpg", "image/jpeg")
                else:
                    analysis = ""
            user_msg  = caption or "Analizza questa immagine che ti ho inviato."
            if analysis and analysis != "__TOKEN_EXPIRED__":
                user_msg = f"{user_msg}\n\n[Contenuto immagine: {analysis}]"

            reply = await _do_chat(user_msg)
            if not await _handle_reply(reply):
                return
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
            if analysis == "__TOKEN_EXPIRED__":
                new_token = await _auto_refresh(session_uid, session)
                if new_token:
                    token = new_token
                    analysis = await _upload_file(token, doc_bytes, filename, mime)
                else:
                    analysis = ""
            user_msg  = caption or f"Ho inviato il documento: {filename}."
            if analysis and analysis != "__TOKEN_EXPIRED__":
                user_msg = f"{user_msg}\n\n[Contenuto: {analysis[:500]}]"

            reply = await _do_chat(user_msg)
            if not await _handle_reply(reply):
                return
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

            mime = (voice or audio).get("mime_type", "audio/ogg")
            transcription = await _transcribe(token, audio_bytes, mime)
            if transcription == "__TOKEN_EXPIRED__":
                new_token = await _auto_refresh(session_uid, session)
                if new_token:
                    token = new_token
                    transcription = await _transcribe(token, audio_bytes, mime)
                else:
                    transcription = ""
            if not transcription:
                await send_message(chat_id,
                    "Non sono riuscita a capire il vocale. Prova a scrivere.")
                logger.warning("TELEGRAM_VOICE_STT_EMPTY chat_id=%s mime=%s size=%d",
                               chat_id, mime, len(audio_bytes))
                return

            # Mostra la trascrizione e rispondi
            await send_message(chat_id, f"🎤 {transcription}")
            reply = await _do_chat(transcription)
            if not await _handle_reply(reply):
                return
            logger.info("TELEGRAM_VOICE_OK chat_id=%s transcription=%s",
                        chat_id, transcription[:50])
            return

        # ── TESTO ──────────────────────────────────────────────────────────────
        if not text:
            return

        if _WEATHER_RE.search(text) and not city:
            session["state"]               = STATE_AWAIT_CITY
            session["pending_message"]     = text
            session["pending_city_from_id"] = from_id
            await storage.save(_session_key(session_uid), session)
            name_part = f" {first_name}" if first_name else ""
            await send_message(chat_id,
                f"Per il meteo ho bisogno di sapere dove sei{name_part}. "
                "In quale città ti trovi?")
            return

        await send_typing(chat_id)
        reply = await _do_chat(text)
        await _handle_reply(reply)

    except Exception as e:
        logger.error("TELEGRAM_HANDLE_ERROR err=%s", e)
