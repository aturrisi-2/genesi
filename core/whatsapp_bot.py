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
import time
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

# Filtro gruppi: risponde solo se menzionato o saluto/augurio
_GREETING_RE = re.compile(
    r'\b(ciao|salve|buongiorno|buonasera|buonanotte|hey|hei|ehilà|'
    r'hello|hi|buon\s*giorno|buona\s*sera|'
    r'buon\s*pranzo|buona\s*cena|buon\s*pomeriggio|buona\s*notte|'
    r'buon\s*natale|buona\s*pasqua|buon\s*anno|felice\s*anno|'
    r'buona\s*domenica|buon\s*sabato|buon\s*venerd[iì]|'
    r'buon\s*week\s*end|buon\s*weekend|buone\s*feste|'
    r'auguri|tanti\s*auguri|felicitazioni|congratulazioni)\b',
    re.IGNORECASE
)
_GENESI_RE = re.compile(r'\bgenesi\b', re.IGNORECASE)

_CELEBRATION_EMOJIS = ("🎉", "🎊", "🥳", "🎈", "🥂", "🍾", "🎂", "🏆", "🎁")
_GOOD_NEWS_KW = (
    "habemus", "ce l'ho fatta", "ce la fatta", "ho preso", "ho comprato",
    "è arrivat", "arrivata la", "arrivato il", "finalmente", "ho trovato",
    "ho vinto", "abbiamo vinto", "promozione", "promosso", "promossa",
    "laurea", "diploma", "compleanno", "auguri", "tanti auguri",
    "felicitazioni", "congratulazioni", "buone feste",
)


# Stato conversazione per gruppo: traccia con chi Genesi stava parlando di recente
# { chat_id: {"wa_id": str, "ts": float, "last_reply": str} }
_GROUP_CONV_STATE: dict[int, dict] = {}


def _get_greeting_category(text_lower: str) -> str:
    holiday_kws = ("natal", "pasqu", "anno nuovo", "feste", "augur", "compleann", "onomastic")
    if any(k in text_lower for k in holiday_kws):
        return "holiday"
    evening_kws = ("buonasera", "buona sera", "buonanotte", "buona notte", "buona cena", "buona serata", "buonaserata")
    if any(k in text_lower for k in evening_kws):
        return "evening"
    morning_kws = ("buongiorno", "buon giorno", "buon pomeriggio", "buona domenica", "buon weekend", "buon week end", "buona giornata", "buon pranzo")
    if any(k in text_lower for k in morning_kws):
        return "morning"
    general_kws = ("ciao", "salve", "hey", "hei", "ehilà", "hello", "hi")
    if any(k in text_lower for k in general_kws):
        return "general"
    return ""


async def _check_and_register_greeting(chat_id: int, user_id: str, category: str) -> bool:
    if not category or not user_id:
        return False
    from datetime import datetime
    from zoneinfo import ZoneInfo
    try:
        tz = ZoneInfo("Europe/Rome")
    except Exception:
        tz = None
    now = datetime.now(tz)
    today_str = now.date().isoformat()
    now_ts = time.time()
    
    key = f"relational_state:group_greetings_{chat_id}"
    history = await storage.load(key, default={}) or {}
    
    user_prefix = f"{user_id}:"
    for k, v in history.items():
        if k.startswith(user_prefix):
            stored_date = ""
            stored_ts = 0.0
            if isinstance(v, dict):
                stored_date = v.get("date", "")
                stored_ts = v.get("ts", 0.0)
            elif isinstance(v, str):
                stored_date = v
            
            # Allow greetings if more than 4 hours elapsed. 
            # If legacy string format (no ts), block if it was today for this category.
            if stored_ts > 0:
                if now_ts - stored_ts < 14400:
                    return False
            else:
                if k == f"{user_id}:{category}" and stored_date == today_str:
                    return False

    history[f"{user_id}:{category}"] = {
        "date": today_str,
        "ts": now_ts
    }
    await storage.save(key, history)
    return True



_GROUP_INTERVENE_PROMPT = """\
Sei il filtro di intervento di Genesi in un gruppo familiare su Telegram o WhatsApp.
Genesi è il GUARDIANO EMOTIVO della famiglia: veglia con affetto, pazienza e attenzione sui membri della famiglia, ed è pronta a partecipare attivamente alla discussione per sostenere, intrattenere, o incalzare la conversazione, ma sempre con discrezione e MAI in modo invadente o spammone.

Leggi i messaggi recenti del gruppo e il messaggio attuale. Decidi se Genesi deve rispondere.

RISPONDI "SI" se il messaggio attuale rientra in UNO di questi casi:
1. INVOCATA: qualcuno cita Genesi per nome (es: "Genesi..."), la taglia o le pone una domanda diretta.
2. CONTINUAZIONE DIRETTA: follow-up a una risposta appena data da Genesi (< 5 min, stesso filo).
3. VERO DIALOGO E INTRATTENIMENTO: intuisci un vero dialogo attivo in cui la partecipazione proattiva di Genesi può arricchire la discussione, incalzando con curiosità o intrattenendo i familiari in modo caloroso e naturale.
4. DOMANDA GENERICA DA AIUTO: qualcuno pone una domanda oggettiva, informativa, o di curiosità generale rivolta al gruppo o a nessuno in particolare (es: "qualcuno sa a che ora chiude il supermercato?", "come si prepara la carbonara?", "che tempo fa domani a Roma?") a cui Genesi può rispondere con certezza assoluta, coerenza e grande utilità per il gruppo.
5. COMPLEANNI E FESTIVITÀ: qualcuno fa gli auguri di compleanno o festeggia una festività nel gruppo, oppure il messaggio descrive una festività del giorno attuale, e Genesi vuole unirsi in modo caloroso e naturale agli auguri.
6. NOTIZIA EMOTIVA O SIGNIFICATIVA: un successo eccezionale, un traguardo importante, un lutto, una malattia seria, o un problema/stato emotivo di un familiare — Genesi, come guardiano emotivo, interviene sempre con sincera vicinanza e calore umano.
7. SALUTO DI APERTURA / ACCOGLIENZA: il primo saluto del giorno nel gruppo o il saluto di un utente che si sveglia/arriva più tardi (es. dopo ore di silenzio per quell'utente). Genesi deve accogliere calorosamente chiunque saluti a distanza di tempo. Nota: se nel contesto è indicato che Genesi ha già salutato di recente o oggi lo stesso utente per quella categoria, rispondi "NO".
8. DOMANDA DI FOLLOW-UP O CHIARIMENTO: qualcuno pone una domanda di approfondimento, continuazione o chiarimento legata a un tema o a una risposta data da Genesi di recente.

RISPONDI "NO" in tutti gli altri casi, incluso:
- Aggiornamenti quotidiani di routine irrilevanti (es. coordinamento logistico stretto o passaggi tecnici puri tra familiari dove l'AI non darebbe alcun valore emotivo o informativo).
- Chiacchiere esclusive e private tra due persone della famiglia dove l'intrusione dell'AI risulterebbe forzata o innaturale.
- Domande rivolte specificamente ed esclusivamente a un altro membro umano della famiglia (es: "Papà, mi porti le chiavi?"). Se invece la domanda riguarda informazioni che l'AI possiede (meteo, news, informazioni sui familiari) e non è rivolta in modo esclusivo a un umano specifico, rispondi "SI".
- Saluti ripetuti o ravvicinati dello stesso utente a cui si è già risposto di recente.

REGOLA CRITICA: Sii partecipe e veglia sulla famiglia come guardiano emotivo paziente, ma tieni sempre presente il limite dell'invadenza. Il dubbio va verso "NO" solo se la conversazione è palesemente privata o puramente tecnica/logistica tra umani. Se c'è spazio per un calore reale o per stimolare il dialogo attivo, intervieni con un "SI".

Rispondi SOLO con JSON: {"intervieni": true, "motivo": "ragione breve"} oppure {"intervieni": false, "motivo": "ragione breve"}
"""


async def _group_should_intervene(
    text: str, caption: str, chat_id: int, wa_id: str, first_name: str,
    bot_mentioned: bool = False, has_media: bool = False
) -> bool:
    """
    Decide con LLM se Genesi deve intervenire nel gruppo WhatsApp.
    Fast-path per mention/nome diretti. LLM per tutto il resto.
    """
    combined = f"{text} {caption}".strip()
    if not combined:
        if not has_media:
            return False
        combined = "[Inviato elemento multimediale senza didascalia]"

    # Fast-path: menzione diretta → sempre sì
    if bot_mentioned:
        return True

    # Fast-path: saluto di gruppo -> controlla limite temporale per-utente
    combined_lower = combined.lower()
    category = _get_greeting_category(combined_lower)
    if category:
        should_greet = await _check_and_register_greeting(chat_id, wa_id, category)
        if should_greet:
            return True
        # Se should_greet è False, NON usciamo con False direttamente!
        # Facciamo fall-through per consentire ad altre regole (es. domande o follow-up) di intervenire.

    # Fast-path: messaggio troppo corto e senza punto interrogativo → probabile scambio tra membri
    if len(combined) < 8 and "?" not in combined:
        return False

    # Fast-path: continuazione di conversazione attiva nel gruppo (< 5 min)
    state = _GROUP_CONV_STATE.get(chat_id, {})
    last_reply_age = time.time() - state.get("ts", 0)
    if last_reply_age < 300:
        # Se lo stesso utente continua a scrivere
        if state.get("wa_id") == wa_id:
            return True
        # Se un altro utente fa una domanda o cita Genesi
        if "?" in combined:
            return True
        # Se è una domanda implicita di follow-up (es. inizia con "e ", "ma ", "invece ")
        combined_clean = combined.lower().strip()
        if combined_clean.startswith(("e ", "ma ", "invece ")):
            return True

    # LLM decision
    try:
        from core.llm_service import llm_service
        from core.telegram_group_memory import get_raw_messages
        raw_msgs = await get_raw_messages(chat_id, limit=12)
        history_text = ""
        if raw_msgs:
            history_text = "Messaggi recenti nel gruppo (tutti, non solo quelli con Genesi):\n" + "\n".join(
                f"  {m.get('first_name','?')}: {m.get('text','')[:100]}"
                for m in raw_msgs[:-1]  # escludi l'ultimo che è il messaggio attuale
            ) + "\n\n"
        # Aggiungi l'ultima risposta di Genesi al contesto
        state = _GROUP_CONV_STATE.get(chat_id, {})
        last_reply = state.get("last_reply")
        last_reply_ts = state.get("ts", 0)
        if last_reply and time.time() - last_reply_ts < 300:  # 5 minuti
            history_text += f"Ultima risposta di Genesi in questo gruppo: Genesi: {last_reply[:200]}\n\n"

        # Informa l'LLM se Genesi ha già risposto a saluti oggi per questo specifico utente
        key = f"relational_state:group_greetings_{chat_id}"
        history = await storage.load(key, default={}) or {}
        from datetime import datetime
        from zoneinfo import ZoneInfo
        try:
            tz = ZoneInfo("Europe/Rome")
        except Exception:
            tz = None
        today_str = datetime.now(tz).date().isoformat()
        
        user_prefix = f"{wa_id}:"
        user_sent_today = []
        for k, v in history.items():
            if k.startswith(user_prefix):
                stored_date = ""
                if isinstance(v, dict):
                    stored_date = v.get("date", "")
                elif isinstance(v, str):
                    stored_date = v
                if stored_date == today_str:
                    user_sent_today.append(k.split(":")[1])
        
        greet_note = ""
        if user_sent_today:
            greet_note = f"[Nota: Genesi ha già salutato oggi l'utente {first_name} per queste categorie: {', '.join(user_sent_today)}. Non rispondere a saluti ripetuti di queste categorie da parte sua!]\n\n"

        user_msg = (
            f"{greet_note}"
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
        logger.info("GROUP_INTERVENE_DECISION_WA chat_id=%s from=%s intervieni=%s motivo=%s",
                    chat_id, first_name, intervieni, motivo)
        return bool(intervieni)
    except Exception as exc:
        logger.debug("GROUP_INTERVENE_ERROR_WA err=%s", exc)
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
    if not text:
        return
    
    # Costruisci il JID di WhatsApp (Baileys)
    jid = wa_id if "@" in wa_id else f"{wa_id}@s.whatsapp.net"

    # Tentiamo di inviare tramite il bridge Baileys locale
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            payload = {
                "groupId": jid,
                "text": text
            }
            res = await client.post("http://localhost:3001/send", json=payload)
            if res.status_code == 200:
                logger.info("WA_SEND_BAILEYS_OK to=%s", jid)
                return
            else:
                logger.warning("WA_SEND_BAILEYS_FAIL status=%d to=%s, falling back to Meta API", res.status_code, jid)
    except Exception as e:
        logger.warning("WA_SEND_BAILEYS_EXCEPTION err=%s to=%s, falling back to Meta API", e, jid)

    # Fallback su Meta Business Cloud API originale
    if not WA_ACCESS_TOKEN or not WA_PHONE_NUMBER_ID:
        return
    meta_to = wa_id.split("@")[0]
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    async with httpx.AsyncClient(timeout=15) as client:
        for chunk in chunks:
            payload = {
                "messaging_product": "whatsapp",
                "to": meta_to,
                "type": "text",
                "text": {"body": chunk, "preview_url": False},
            }
            try:
                await client.post(
                    f"{WA_API_BASE}/{WA_PHONE_NUMBER_ID}/messages",
                    json=payload,
                    headers={"Authorization": f"Bearer {WA_ACCESS_TOKEN}"},
                )
                logger.info("WA_SEND_META_OK to=%s", meta_to)
            except Exception as e:
                logger.error("WA_SEND_META_ERROR to=%s err=%s", meta_to, e)
            if len(chunks) > 1:
                await asyncio.sleep(0.3)


async def send_typing(wa_id: str, msg_id: str = ""):
    """Segna il messaggio come letto su WhatsApp e attiva l'indicatore di scrittura via Baileys."""
    jid = wa_id if "@" in wa_id else f"{wa_id}@s.whatsapp.net"

    # Tentiamo di inviare lo stato di scrittura tramite il bridge Baileys
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            payload = {
                "groupId": jid,
                "presence": "composing"
            }
            res = await client.post("http://localhost:3001/send", json=payload)
            if res.status_code == 200:
                logger.info("WA_SEND_TYPING_BAILEYS_OK to=%s", jid)
            else:
                logger.warning("WA_SEND_TYPING_BAILEYS_FAIL status=%d to=%s", res.status_code, jid)
    except Exception as e:
        logger.debug("WA_SEND_TYPING_BAILEYS_EXCEPTION err=%s to=%s", e, jid)

    # Segna il messaggio come letto tramite Meta API (come backup/originale)
    if not WA_ACCESS_TOKEN or not WA_PHONE_NUMBER_ID or not msg_id:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
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
    except Exception as e:
        logger.warning("WA_MARK_READ_ERROR wa_id=%s err=%s", wa_id, e)


async def send_image(wa_id: str, image_url: str, caption: str = "") -> bool:
    """Invia un'immagine da URL pubblico."""
    jid = wa_id if "@" in wa_id else f"{wa_id}@s.whatsapp.net"

    # Tentiamo di inviare tramite il bridge Baileys
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            payload = {
                "groupId": jid,
                "imageUrl": image_url,
                "caption": caption
            }
            res = await client.post("http://localhost:3001/send", json=payload)
            if res.status_code == 200:
                logger.info("WA_SEND_IMAGE_BAILEYS_OK to=%s url=%s", jid, image_url)
                return True
            else:
                logger.warning("WA_SEND_IMAGE_BAILEYS_FAIL status=%d to=%s, falling back to Meta API", res.status_code, jid)
    except Exception as e:
        logger.warning("WA_SEND_IMAGE_BAILEYS_EXCEPTION err=%s to=%s, falling back to Meta API", e, jid)

    # Fallback su Meta Business Cloud API originale
    if not WA_ACCESS_TOKEN or not WA_PHONE_NUMBER_ID:
        return False
    meta_to = wa_id.split("@")[0]
    payload = {
        "messaging_product": "whatsapp",
        "to": meta_to,
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
            logger.info("WA_SEND_IMAGE_META_OK to=%s status=%d", meta_to, res.status_code)
            return res.status_code == 200
        except Exception as e:
            logger.error("WA_SEND_IMAGE_META_ERROR to=%s err=%s", meta_to, e)
            return False


async def download_media(media_id: str) -> tuple[bytes | None, str]:
    """Scarica un media da WhatsApp. Ritorna (bytes, mime_type).
    Tenta prima di leggere la cache locale salvata da Baileys, poi fa il fallback su Meta.
    """
    media_path = os.path.join("/opt/genesi-baileys/media-cache", media_id)
    mime_path = media_path + ".mime"
    
    # Controlla percorso alternativo relativo per testing locale su Windows
    if not os.path.exists(media_path):
        alt_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "baileys-service", "media-cache", media_id))
        if os.path.exists(alt_path):
            media_path = alt_path
            mime_path = alt_path + ".mime"

    if os.path.exists(media_path):
        try:
            with open(media_path, "rb") as f:
                content = f.read()
            mime = "application/octet-stream"
            if os.path.exists(mime_path):
                with open(mime_path, "r", encoding="utf-8") as f:
                    mime = f.read().strip()
                try:
                    os.remove(mime_path)
                except Exception:
                    pass
            try:
                os.remove(media_path)
            except Exception:
                pass
            logger.info("WA_DOWNLOAD_LOCAL_OK media_id=%s mime=%s", media_id, mime)
            return content, mime
        except Exception as e:
            logger.error("WA_DOWNLOAD_LOCAL_ERROR media_id=%s err=%s", media_id, e)

    # Fallback su Meta Business Cloud API originale
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
            logger.info("WA_DOWNLOAD_META_OK media_id=%s mime=%s", media_id, mime)
            return res2.content, mime
        except Exception as e:
            logger.error("WA_DOWNLOAD_META_ERROR media_id=%s err=%s", media_id, e)
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
            token = session.get("token")
            if not token:
                # Esegui autologin silenzioso con l'account principale di Alfio
                token = await _login("alfio.turrisi@gmail.com", "ZOEennio0810")
                if token:
                    session.update({
                        "token": token,
                        "email": "alfio.turrisi@gmail.com",
                        "password": "ZOEennio0810",
                        "state": STATE_IDLE,
                        "welcomed": True
                    })
                    await storage.save(_session_key(wa_id), session)

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
            # Esegui autologin silenzioso con l'account principale di Alfio
            token = await _login("alfio.turrisi@gmail.com", "ZOEennio0810")
            if token:
                session.update({
                    "token": token,
                    "email": "alfio.turrisi@gmail.com",
                    "password": "ZOEennio0810",
                    "state": STATE_IDLE,
                    "welcomed": True
                })
                await storage.save(_session_key(wa_id), session)
            else:
                await send_message(wa_id,
                    "Per chattare con me hai bisogno di un account.\n\n"
                    f"• Già registrato? Scrivi: *accedi*\n"
                    f"  oppure: {_WEBAPP_LINK}login?from=whatsapp&wa_id={wa_id}\n\n"
                    f"• Nuovo? Scrivi: *registrati*\n"
                    f"  oppure: {_WEBAPP_LINK}register?from=whatsapp&wa_id={wa_id}")
                return


        city = session.get("city", "")

        # ── Pre-processing Media e Trascrizione Vocale ─────────────────────────
        _original_has_media = bool(photo_id or voice_id or doc_id)
        _transcribed_voice_text = ""
        
        if voice_id:
            await send_typing(wa_id, msg_id)
            audio_bytes, mime = await download_media(voice_id)
            if audio_bytes:
                transcription = await _transcribe(token, audio_bytes, mime or "audio/ogg")
                if transcription == "__TOKEN_EXPIRED__":
                    new_token = await _auto_refresh(wa_id, session)
                    if new_token:
                        token = new_token
                        transcription = await _transcribe(token, audio_bytes, mime or "audio/ogg")
                
                if transcription and transcription != "__TOKEN_EXPIRED__":
                    _transcribed_voice_text = transcription
                    text = transcription  # Aggiorna per i filtri successivi
                    voice_id = ""         # Evita ri-processamento nel blocco media
                    if not is_group:
                        await send_message(wa_id, f"🎤 _{transcription}_")
                else:
                    if not is_group:
                        await send_message(wa_id, "Non sono riuscita a capire il vocale. Prova a scrivere.")
                    return
            else:
                if not is_group:
                    await send_message(wa_id, "Non sono riuscita a scaricare il vocale.")
                return

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

        # ── FILTRO GRUPPI (LLM-based) ──────────────────────────────────────────
        _reply_to_genesi = False
        if is_group:
            combined = f"{text} {caption}".strip()
            bot_mentioned = False
            if WA_PHONE_NUMBER and WA_PHONE_NUMBER in combined:
                bot_mentioned = True
            if _GENESI_RE.search(combined):
                bot_mentioned = True

            # Reply a Genesi
            reply_to = msg.get("context", {})
            replied_from = reply_to.get("from", "")
            if replied_from == WA_PHONE_NUMBER:
                _reply_to_genesi = True

            # Fast-path: reply diretta a Genesi -> sempre sì
            if _reply_to_genesi:
                should = True
            else:
                should = await _group_should_intervene(
                    text, caption, chat_id, wa_id, first_name,
                    bot_mentioned=bot_mentioned,
                    has_media=_original_has_media
                )
            if not should:
                logger.info("WA_GROUP_SILENT chat_id=%s from=%s msg=%.60s",
                            chat_id, first_name, f"{text} {caption}".strip())
                return
            
            # Se interveniamo su un vocale, invia prima la trascrizione
            if _transcribed_voice_text:
                await send_message(wa_id, f"🎤 _{_transcribed_voice_text}_")

        async def _do_chat(message: str) -> str:
            nonlocal token, session
            try:
                from core.link_explorer import explore_links_in_text
                message = await explore_links_in_text(message)
            except Exception as e:
                logger.warning("WA_LINK_EXPLORE_FAIL err=%s", e)

            # Gruppi WhatsApp: inietta contesto famiglia e usa platform whatsapp_group
            if is_group and chat_id and first_name:
                try:
                    from core.telegram_group_memory import build_group_context
                    group_ctx = await build_group_context(chat_id, abs(hash(wa_id)) % (10**9), first_name)
                    msg_with_quote = message
                    if _reply_to_genesi:
                        msg_with_quote = f"[Stai rispondendo a un tuo messaggio precedente di Genesi]\n{message}"
                    message = (
                        f"{msg_with_quote}\n\n"
                        f"[GRUPPO FAMILIARE: scrive {first_name}. "
                        f"REGOLE ASSOLUTE: risposta MAX 2 righe, tono naturale da familiare (non da assistente), "
                        f"zero intro elaborati, zero domande di ritorno, zero 'che bello!'. "
                        f"IMPORTANTE: Sei Genesi (un'AI). Non sei la mamma o altri parenti. Non impersonare altri e non dire 'grazie per gli auguri' se festeggiano altri (es. 'Auguri mamma!'). Invece unisciti con calore agli auguri per lei (es. 'Tanti auguri alla tua mamma!'). "
                        f"NON menzionare eventi passati (malattie, problemi, notizie di giorni fa) "
                        f"a meno che {first_name} non li citi in questo messaggio. "
                        f"Rispondi SOLO a quello che viene detto adesso.]\n"
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
                    summarize_group_discussion_if_needed,
                    detect_and_save_correction,
                )
                orig_text = (text or caption or "").strip()
                _wa_from_id = abs(hash(wa_id)) % (10**9)
                asyncio.create_task(append_group_history(chat_id, _wa_from_id, first_name, orig_text, reply))
                asyncio.create_task(record_group_observation(chat_id, _wa_from_id, first_name, orig_text, reply))
                asyncio.create_task(consolidate_group_insights_if_needed(chat_id))
                asyncio.create_task(summarize_group_discussion_if_needed(chat_id))
                asyncio.create_task(detect_and_save_correction(chat_id, _wa_from_id, first_name, orig_text, reply))

            # Livello 4: memoria personale del mittente — episodi e fatti su testo pulito
            if reply not in ("__TOKEN_EXPIRED__", "__AUTH_FAILED__"):
                from core.simple_chat import strip_group_ctx as _strip_group_ctx
                _raw_msg = _strip_group_ctx(message)
                if _raw_msg and len(_raw_msg) > 10:
                    _mem_msg  = _raw_msg
                    _mem_resp = reply
                    _mem_session_uid = chat_id if is_group else wa_id

                    async def _wa_extract_episode(_mm=_mem_msg, _su=_mem_session_uid):
                        try:
                            from core.episode_extractor import extract_episodes
                            from core.episode_memory import episode_memory as _em
                            ctx = f"{first_name}: {_mm}"
                            for ep in await extract_episodes(ctx, _su):
                                await _em.add(_su, ep)
                                logger.info("EPISODE_SAVED_WA sender=%s text=%.60s", first_name, ep['text'])
                        except Exception as e:
                            logger.debug("WA_EPISODE_EXTRACT_ERROR err=%s", e)
                    asyncio.create_task(_wa_extract_episode())

                    async def _wa_extract_facts(_mm=_mem_msg, _mr=_mem_resp, _su=_mem_session_uid):
                        try:
                            from core.personal_facts_service import personal_facts_service as _pfs
                            ctx = f"{first_name}: {_mm}"
                            await _pfs.extract_and_save(ctx, _mr, _su)
                        except Exception as e:
                            logger.debug("WA_FACTS_EXTRACT_ERROR err=%s", e)
                    asyncio.create_task(_wa_extract_facts())

                    async def _wa_global_memory(_su=_mem_session_uid):
                        try:
                            from core.global_memory_service import global_memory_service as _gms
                            await _gms.consolidate_if_needed(_su)
                        except Exception as e:
                            logger.debug("WA_GLOBAL_MEM_ERROR err=%s", e)
                    asyncio.create_task(_wa_global_memory())

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
            # Traccia con chi Genesi stava conversando
            if is_group and chat_id:
                _GROUP_CONV_STATE[chat_id] = {
                    "wa_id":      wa_id,
                    "ts":         time.time(),
                    "last_reply": reply[:300],
                }
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
