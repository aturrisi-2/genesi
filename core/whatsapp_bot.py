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
from core.log import log
from core.face_memory_service import (
    handle_photo_identification, handle_text_identification,
    get_awaiting_faces,
)

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

# Saluti registrati da _group_should_intervene, in attesa di risposta personalizzata
# { chat_id: {"wa_id": str, "category": str, "late_wakeup": bool, "pure": bool, "ts": float} }
_PENDING_GREETINGS: dict[int, dict] = {}

# I gruppi WhatsApp gestiti da Genesi sono attualmente tutti familiari
# (la pipeline usa già il prompt "GRUPPO FAMILIARE" per ogni gruppo WA).
_WA_GROUPS_ARE_FAMILY = True


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


def _is_pure_greeting(text_lower: str) -> bool:
    category = _get_greeting_category(text_lower)
    if not category:
        return False
    if "?" in text_lower:
        return False
    cleaned = re.sub(r'[^a-záéíóúàèìòù\s]', ' ', text_lower)
    words = [w for w in cleaned.split() if w]
    
    greeting_vocab = {
        "buongiorno", "buon", "giorno", "pomeriggio", "domenica", "weekend", "week", "end", "giornata", "pranzo",
        "buonasera", "buona", "sera", "buonanotte", "notte", "cena", "serata", "buonaserata",
        "ciao", "salve", "hey", "hei", "ehilà", "hello", "hi", "tutti", "a", "da", "di", "per", "con", "e", "o",
        "famiglia", "gruppo", "belli", "bella", "cara", "caro", "nonna", "mamma", "papà", "zio", "zia", "ragazzi",
        "gente", "mondo", "ciurma", "soci", "società", "tutte", "tutti", "tutto", "auguri", "augur", "feste",
        "felice", "compleanno", "onomastico", "pasqua", "natale", "anno", "nuovo",
        "del", "al", "ai", "degli", "delle", "della", "dello", "nei", "nella", "nello", "negli", "nelle",
        "sul", "sulla", "sullo", "sugli", "sulle", "col", "coi", "dal", "dalla", "dallo", "dagli", "dalle",
        "un", "una", "uno", "il", "la", "i", "gli", "le", "te", "ti", "tu"
    }
    
    non_greeting_words = [w for w in words if w not in greeting_vocab]
    significant_words = [w for w in non_greeting_words if len(w) > 2]
    return len(significant_words) == 0



async def _check_and_register_greeting(chat_id: int, user_id: str, category: str) -> tuple[bool, bool]:
    if not category or not user_id:
        return False, False
    from datetime import datetime
    from zoneinfo import ZoneInfo
    try:
        tz = ZoneInfo("Europe/Rome")
    except Exception:
        tz = None
    now = datetime.now(tz)
    today_str = now.date().isoformat()
    now_ts = time.time()
    
    # 1. Controlla il gap globale di 1 ora (3600 secondi) a livello di gruppo
    global_key = f"relational_state:last_group_greeting_ts_{chat_id}"
    last_ts = await storage.load(global_key, default=0.0)
    if now_ts - last_ts < 3600:
        return False, False
        
    is_late_wakeup = (last_ts > 0) and (category == "morning")
        
    # 2. Controlla il gap per-singolo-utente
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
                    return False, False
            else:
                if k == f"{user_id}:{category}" and stored_date == today_str:
                    return False, False

    history[f"{user_id}:{category}"] = {
        "date": today_str,
        "ts": now_ts
    }
    await storage.save(key, history)
    await storage.save(global_key, now_ts)
    return True, is_late_wakeup



_GROUP_INTERVENE_PROMPT = """\
Sei il filtro di intervento di Genesi in un gruppo familiare su Telegram o WhatsApp.
Genesi è un'assistente AI silenziosa e discreta all'interno del gruppo. NON è un membro umano della famiglia, ma un'AI esterna di supporto.
Deve rimanere SILENZIOSA la maggior parte del tempo per evitare di essere invadente o fastidiosa.

Leggi i messaggi recenti del gruppo e il messaggio attuale. Decidi se Genesi deve rispondere.

RISPONDI "SI" SOLO nei seguenti casi:
1. INVOCATA DIRETTAMENTE: Qualcuno si rivolge esplicitamente a Genesi, la nomina (es. "Genesi..."), la tagga o le fa una domanda diretta.
2. DOMANDA GENERICA DI UTILITÀ: Qualcuno fa una domanda oggettiva o informativa rivolta al gruppo (es. "a che ora chiude il supermercato?", "che tempo fa domani?"), a cui un'AI può rispondere con dati certi e utili per tutti.
3. RISPOSTA DI CONTINUAZIONE: L'utente sta rispondendo direttamente a una domanda o affermazione fatta da Genesi nel turno immediatamente precedente.

RISPONDI "NO" in tutti gli altri casi. In particolare, rispondi "NO" per:
- Chiacchiere, aggiornamenti personali, stati d'animo o aggiornamenti di routine tra i membri del gruppo (es. "sto tornando dalle analisi", "prendo il brufen").
- Saluti generici di inizio giornata o auguri (es. "Buongiorno a tutti", "Buon pranzo", "Buonanotte", "Auguri mamma!"). Questi sono scambi affettuosi tra umani; Genesi deve rimanere in silenzio e non intromettersi.
- Messaggi in cui un utente risponde o parla con un altro membro umano del gruppo (es. Katia che risponde a Zoe, o Iolanda che saluta Mariella).
- Qualsiasi situazione di dubbio. Nel dubbio, non intervenire (rispondi "NO").

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
    import re
    has_link = bool(re.search(r'https?://[^\s]+|www\.[^\s]+', f"{text} {caption}", re.IGNORECASE))
    if has_media or has_link:
        # Interviene sempre se viene inviato un elemento multimediale (foto, video, doc, ecc.) o un link
        return True

    combined = f"{text} {caption}".strip()
    if not combined:
        return False

    # Fast-path: menzione diretta → sempre sì
    if bot_mentioned:
        return True

    combined_lower = combined.lower()

    # Fast-path: saluto di gruppo -> controlla limite temporale per-utente
    category = _get_greeting_category(combined_lower)
    if category:
        should_greet, is_late_wakeup = await _check_and_register_greeting(chat_id, wa_id, category)
        if should_greet:
            # Registra il saluto: _process_message lo gestirà con il servizio
            # universale (group_greeting_service) o, se il messaggio non è un
            # saluto puro, con la pipeline normale (+ flag late_wakeup).
            _PENDING_GREETINGS[chat_id] = {
                "wa_id":       wa_id,
                "category":    category,
                "late_wakeup": is_late_wakeup,
                "pure":        _is_pure_greeting(combined_lower) and not has_media,
                "ts":          time.time(),
            }
            return True
        # Se should_greet è False e il saluto è "puro" (senza domande o altro testo utile),
        # ignoralo subito senza fare fall-through, per evitare di ripetere i saluti!
        if _is_pure_greeting(combined_lower) and not has_media:
            return False

    # Fast-path: messaggio troppo corto e senza punto interrogativo → probabile scambio tra membri
    # Se c'è un elemento multimediale, bypassiamo questo controllo per consentire l'analisi del media.
    if len(combined) < 8 and "?" not in combined and not has_media:
        return False

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
        if last_reply and time.time() - last_reply_ts < 600:  # 10 minuti
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
    "Ogni nostra conversazione mi aiuta a conoscerti meglio e a migliorare."
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

_WA_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)")


def _wa_clean_links(text: str) -> tuple[str, list[tuple[str, str]]]:
    """
    WhatsApp non rende il markdown: [titolo](url) apparirebbe grezzo.
    Converte in '🌐 titolo: url' (cliccabile) e ritorna i link estratti
    per l'eventuale bottone cta_url sul fallback Cloud API.
    """
    links = _WA_MD_LINK_RE.findall(text or "")
    clean = _WA_MD_LINK_RE.sub(lambda m: f"🌐 {m.group(1)}: {m.group(2)}", text or "")
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for title, url in links:
        if url not in seen:
            seen.add(url)
            out.append((title.strip(), url))
    return clean, out[:1]


async def send_message(wa_id: str, text: str):
    """Invia un messaggio testuale WhatsApp."""
    if not text:
        return

    # Fonti live search: markdown → link cliccabile pulito
    text, _source_links = _wa_clean_links(text)

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

        # Fonte come bottone nativo (cta_url) — solo path Cloud API
        if _source_links:
            _title, _url = _source_links[0]
            try:
                await client.post(
                    f"{WA_API_BASE}/{WA_PHONE_NUMBER_ID}/messages",
                    json={
                        "messaging_product": "whatsapp",
                        "to": meta_to,
                        "type": "interactive",
                        "interactive": {
                            "type": "cta_url",
                            "body": {"text": f"Fonte: {_title[:900]}"},
                            "action": {"name": "cta_url", "parameters": {
                                "display_text": "🌐 Apri fonte",
                                "url": _url,
                            }},
                        },
                    },
                    headers={"Authorization": f"Bearer {WA_ACCESS_TOKEN}"},
                )
                logger.info("WA_SOURCE_BUTTON_SENT to=%s", meta_to)
            except Exception as e:
                logger.debug("WA_SOURCE_BUTTON_ERR to=%s err=%s", meta_to, e)


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

    # Mark-read + indicatore "sta scrivendo" nativo Cloud API
    # (typing_indicator mostra i puntini fino a ~25s o fino alla risposta)
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
                    "typing_indicator": {"type": "text"},
                },
                headers={"Authorization": f"Bearer {WA_ACCESS_TOKEN}"},
            )
            logger.info("WA_MARK_READ_TYPING msg_id=%s status=%d", msg_id, r.status_code)
            if r.status_code != 200:
                # Fallback: alcuni account non supportano typing_indicator —
                # ritenta il solo mark-read classico
                r2 = await client.post(
                    f"{WA_API_BASE}/{WA_PHONE_NUMBER_ID}/messages",
                    json={
                        "messaging_product": "whatsapp",
                        "status": "read",
                        "message_id": msg_id,
                    },
                    headers={"Authorization": f"Bearer {WA_ACCESS_TOKEN}"},
                )
                logger.info("WA_MARK_READ_FALLBACK msg_id=%s status=%d", msg_id, r2.status_code)
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
            return d.get("content") or d.get("analysis") or d.get("summary") or d.get("message") or ""
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
                    from core.telegram_group_memory import stable_hash
                    chat_id = stable_hash(gid) if gid else 0
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
        video_id = ""

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
        elif msg_type == "video":
            vid = msg.get("video", {})
            video_id = vid.get("id", "")
            caption  = vid.get("caption", "").strip()
            mime_type_media = vid.get("mime_type", "video/mp4")
        else:
            # Tipo non gestito (sticker, location, ecc.)
            logger.info("WA_UNSUPPORTED_TYPE wa_id=%s type=%s", wa_id, msg_type)
            await send_message(wa_id,
                "Questo tipo di messaggio non è ancora supportato. "
                "Scrivimi in testo, o inviami foto, vocali o documenti.")
            return

        session = await storage.load(_session_key(wa_id)) or {}
        state   = session.get("state", STATE_IDLE)

        # ── Rilevamento nomi per volti sconosciuti (handler centralizzato) ──────
        _wa_session = str(chat_id) if is_group else str(wa_id)
        # Cattura stato PRIMA di handle_text_identification (che potrebbe cancellarlo)
        was_awaiting_faces = bool(await get_awaiting_faces(_wa_session))
        if text:
            face_result = await handle_text_identification(_wa_session, text)
            if face_result["was_awaiting"] and face_result["faces_saved"]:
                text += face_result["sistema_msg"]

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
                    f"Scrivimi, mandami foto o vocali.")
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
        _original_has_media = bool(photo_id or voice_id or doc_id or video_id)
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
                sync_family_to_owner, stable_hash,
            )
            # Aggiorna profilo membro ad ogni messaggio
            asyncio.create_task(update_member_seen(stable_hash(wa_id), first_name))
            # Servizio universale: estrae nome/città dai messaggi (regex gate + LLM)
            try:
                from core.group_greeting_service import group_greeting_service
                asyncio.create_task(group_greeting_service.extract_and_save_member_info(
                    platform_user_id=wa_id,
                    first_name=first_name,
                    message=(text or caption or ""),
                    platform="whatsapp",
                    group_id=str(chat_id),
                    is_family_group=_WA_GROUPS_ARE_FAMILY,
                ))
            except Exception as _gge:
                logger.warning("GROUP_GREETING_EXTRACT_TASK_FAIL_WA err=%s", _gge)
            # Estrai relazioni familiari
            asyncio.create_task(extract_family_relationship(wa_id, first_name, (text or caption), "whatsapp"))
            # Salva nel buffer grezzo (tutti i messaggi, anche quelli ignorati)
            msg_text = (text or caption or "").strip()
            if msg_text and chat_id:
                asyncio.create_task(append_raw_message(chat_id, stable_hash(wa_id), first_name, msg_text))

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
            if WA_PHONE_NUMBER and WA_PHONE_NUMBER in replied_from:
                _reply_to_genesi = True

            # Fast-path: reply diretta a Genesi -> sempre sì
            if _reply_to_genesi:
                should = True
            elif was_awaiting_faces:
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

            # ── SALUTO DI GRUPPO PERSONALIZZATO (servizio universale) ─────────
            _pending_greet = _PENDING_GREETINGS.pop(chat_id, None)
            if (_pending_greet and _pending_greet.get("wa_id") == wa_id
                    and time.time() - _pending_greet.get("ts", 0) < 60):
                try:
                    from core.group_greeting_service import group_greeting_service
                    from core.telegram_group_memory import append_group_history, stable_hash
                    # Estrai info membro in background (non blocca la risposta)
                    asyncio.create_task(group_greeting_service.extract_and_save_member_info(
                        platform_user_id=wa_id,
                        first_name=first_name,
                        message=(text or caption or ""),
                        platform="whatsapp",
                        group_id=str(chat_id),
                        is_family_group=_WA_GROUPS_ARE_FAMILY,
                    ))
                    if _pending_greet.get("pure"):
                        # Saluto puro → risposta personalizzata diretta
                        # (nome + meteo locale + commento), senza pipeline LLM completa.
                        await send_typing(wa_id, msg_id)
                        greet_reply = await group_greeting_service.build_personalized_greeting(
                            platform_user_id=wa_id,
                            first_name=first_name,
                            greeting_category=_pending_greet.get("category", "general"),
                            platform="whatsapp",
                            group_id=str(chat_id),
                            is_family_group=_WA_GROUPS_ARE_FAMILY,
                            is_late_wakeup=_pending_greet.get("late_wakeup", False),
                        )
                        if greet_reply:
                            await _send_response(wa_id, greet_reply)
                            if chat_id:
                                _GROUP_CONV_STATE[chat_id] = {
                                    "wa_id":      wa_id,
                                    "ts":         time.time(),
                                    "last_reply": greet_reply[:300],
                                }
                                asyncio.create_task(append_group_history(
                                    chat_id, stable_hash(wa_id), first_name,
                                    (text or caption or ""), greet_reply))
                            log("GROUP_GREETING_SENT", platform="whatsapp",
                                chat_id=chat_id, user=wa_id, name=first_name,
                                category=_pending_greet.get("category", ""))
                            return
                    else:
                        # Saluto + altro contenuto → pipeline normale, ma propaga
                        # il flag late_wakeup nella sessione in scope (usata da _do_chat).
                        if _pending_greet.get("late_wakeup"):
                            session["late_wakeup"] = True
                            await storage.save(_session_key(wa_id), session)
                except Exception as _ge:
                    logger.warning("GROUP_GREETING_PIPELINE_FALLBACK_WA err=%s", _ge)
                    # fall-through: la pipeline normale gestirà il messaggio

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
                    from core.telegram_group_memory import build_group_context, stable_hash
                    group_ctx = await build_group_context(chat_id, stable_hash(wa_id), first_name, current_message=message)
                    msg_with_quote = message
                    if _reply_to_genesi:
                        msg_with_quote = f"[Stai rispondendo a un tuo messaggio precedente di Genesi]\n{message}"
                    
                    late_prompt = ""
                    if session.pop("late_wakeup", False):
                        await storage.save(_session_key(wa_id), session)
                        late_prompt = "\n[SISTEMA: Tu hai già dato il buongiorno al gruppo stamattina. Questo utente si è svegliato (o ha scritto) tardi e ti sta salutando adesso. Rispondi con affetto e, se opportuno, con una battuta scherzosa sul fatto che è un po' in ritardo, dandogli un caloroso benvenuto nella giornata! Ignora la regola del 'rispondi in modo estremamente conciso' per questa interazione.]"
                        
                    photo_rules = ""
                    if "[Contenuto immagine:" in message:
                        photo_rules += "Evita spiegoni descrittivi dell'immagine: fai un commento discorsivo e conciso. "
                    
                    domande_rule = "zero domande di ritorno, "
                    if "[UNKNOWN_FACES_DETECTED]" in message or "[UNKNOWN_PETS_DETECTED]" in message:
                        if "[UNKNOWN_PETS_DETECTED]" in message:
                            photo_rules += 'Ci sono animali domestici sconosciuti al sistema visivo. Fai un commento affettuoso. Anche se intuisci chi sia dal profilo, DEVI CHIEDERE all\'utente di scriverti esplicitamente come si chiama per poter memorizzare il suo aspetto visivo. REGOLA FERREA: Fai la domanda e chiedi di scriverti il nome! '
                        else:
                            photo_rules += 'Ci sono persone sconosciute in foto. Fai un commento colloquiale, curioso e intelligente. Includi con molta naturalezza una domanda per chiedere chi sono (se non lo sai dal contesto), ma non essere ripetitivo se l\'hai già chiesto di recente. '
                        domande_rule = ""

                    message = (
                        f"{msg_with_quote}\n\n"
                        f"[GRUPPO FAMILIARE: scrive {first_name}. "
                        f"REGOLE ASSOLUTE: risposta misurata ma loquace e di compagnia (3-4 righe max), tono naturale da familiare (non da assistente), "
                        f"zero intro elaborati, {domande_rule}zero 'che bello!'. "
                        f"IMPORTANTE: Sei Genesi (un'AI). Non sei la mamma o altri parenti. Non impersonare altri. Se gli utenti festeggiano qualcuno o fanno auguri ad altri nel gruppo, non ringraziare come se fossi tu la festeggiata, ma unisciti cordialmente ai festeggiamenti rivolti a quel familiare. "
                        f"NON menzionare eventi passati (malattie, problemi, notizie di giorni fa) "
                        f"a meno che {first_name} non li citi in questo messaggio. "
                        f"{photo_rules}"
                        f"Rispondi SOLO a quello che viene detto adesso.]{late_prompt}\n"
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
                    detect_and_save_correction, stable_hash,
                )
                orig_text = (text or caption or "").strip()
                _wa_from_id = stable_hash(wa_id)
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

                    from core.message_pipeline import schedule_memory_tasks
                    asyncio.create_task(schedule_memory_tasks(
                        user_id=_mem_session_uid,
                        user_message=f"{first_name}: {_mem_msg}",
                        response=_mem_resp,
                        platform="whatsapp",
                        is_group=is_group,
                    ))

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
                # Handler centralizzato per identificazione volti/animali
                _photo_session = str(chat_id) if is_group else str(wa_id)
                photo_result = await handle_photo_identification(
                    _photo_session, img_bytes, analysis, caption=caption
                )
                user_msg = f"{user_msg}\n\n[Contenuto immagine: {analysis}]"
                if photo_result["sistema_msg"]:
                    user_msg += photo_result["sistema_msg"]
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
                # Handler centralizzato per identificazione volti/animali
                _doc_session = str(chat_id) if is_group else str(wa_id)
                photo_result = await handle_photo_identification(
                    _doc_session, doc_bytes, analysis, caption=caption
                )
                user_msg = f"{user_msg}\n\n[Contenuto: {analysis}]"
                if photo_result["sistema_msg"]:
                    user_msg += photo_result["sistema_msg"]
            reply = await _do_chat(user_msg)
            if not await _handle_reply(reply):
                return
            logger.info("WA_DOCUMENT_OK wa_id=%s filename=%s", wa_id, doc_name)
            return

        # ── VIDEO ─────────────────────────────────────────────────────────────
        if video_id:
            await send_typing(wa_id, msg_id)
            user_msg = caption or "Guarda questo video."
            reply = await _do_chat(f"{user_msg}\n\n[Inviato un file video/animazione]")
            if not await _handle_reply(reply):
                return
            logger.info("WA_VIDEO_OK wa_id=%s", wa_id)
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
