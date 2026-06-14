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
from typing import Dict, Any, List

import httpx
from core.storage import storage
from core.log import log
from core.simple_chat import strip_group_ctx as _strip_group_ctx
from core.telegram_group_memory import (
    update_member_seen, get_member_city, save_member_city,
    build_group_context, append_group_history, append_raw_message, get_raw_messages,
    record_group_observation, consolidate_group_insights_if_needed,
    summarize_group_discussion_if_needed,
    extract_family_relationship,
    sync_family_to_owner,
    detect_and_save_correction,
)

logger = logging.getLogger(__name__)

from core.face_memory_service import (
    handle_photo_identification, handle_text_identification,
    get_awaiting_faces,
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API   = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
TELEGRAM_FILES = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}"
GENESI_URL     = "http://localhost:8000"

# Credenziali pre-configurate per i gruppi (auto-login senza /login manuale)
_GROUP_EMAIL    = os.getenv("TELEGRAM_GROUP_EMAIL", "")
_GROUP_PASSWORD = os.getenv("TELEGRAM_GROUP_PASSWORD", "")
# Segreto per derivare le password degli account virtuali dei membri del gruppo
_GROUP_MEMBER_SECRET = os.getenv("TELEGRAM_GROUP_MEMBER_SECRET", "genesi-family-group-2026")
# Gruppi familiari: "Casa Turrisi" (-318483633, famiglia allargata attiva)
# e "Alfio and Alfio" (-5007188402, chat storica/test). Genesi vi partecipa
# da familiare: saluta, risponde senza menzione, estrae relazioni e memoria.
_FAMILY_GROUP_IDS = {-318483633, -5007188402}
# Retrocompatibilità per eventuali import esterni
_FAMILY_GROUP_ID = -5007188402


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

# Reattività: ultimo timestamp di arrivo messaggio per (chat_id, from_id). Serve a
# scartare le risposte diventate stantie (la stessa persona ha già scritto qualcosa di
# nuovo mentre Genesi elaborava → la risposta vecchia ha perso il contesto).
_GROUP_LAST_USER_MSG: dict[tuple, float] = {}

# Saluti registrati da _group_should_intervene, in attesa di risposta personalizzata
# { chat_id: {"from_id": int, "category": str, "late_wakeup": bool, "pure": bool, "ts": float} }
_PENDING_GREETINGS: dict[int, dict] = {}
 
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
    
    # Aggiorna anche il global group greeting ts se abbiamo appena salutato
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
3. RISPOSTA DI CONTINUAZIONE ESPLICITA: L'utente sta rispondendo direttamente (tramite la funzione 'Rispondi' di Telegram) a una domanda o affermazione fatta da Genesi.
4. CONTINUAZIONE IMPLICITA (REGOLA ASSOLUTA): Se il messaggio dell'utente arriva subito dopo un'azione o risposta di Genesi (es. Genesi ha analizzato una foto e l'utente subito dopo chiede "chi sono?", "e io?"), l'utente sta PARLANDO CON GENESI e testando le sue capacità. In questi casi DEVI SEMPRE RISPONDERE "SI", anche se la frase sembra generica e non contiene il nome di Genesi. Non presumere che l'utente stia parlando con altri membri se Genesi ha appena agito!

RISPONDI "NO" in tutti gli altri casi. In particolare, rispondi "NO" per:
- Chiacchiere, aggiornamenti personali, stati d'animo o aggiornamenti di routine tra i membri del gruppo (es. "sto tornando dalle analisi", "prendo il brufen").
- Saluti generici tra umani.
- Messaggi in cui un utente si rivolge inequivocabilmente a un altro umano citandolo per nome (es. "Zoe a che ora torni?").
- Domande strettamente personali se non è in corso una conversazione attiva con Genesi. MENTRE se Genesi ha appena parlato, le domande vanno considerate rivolte a lei.
- Qualsiasi situazione di dubbio in cui il messaggio sembra rivolto agli umani. Nel dubbio, non intervenire (rispondi "NO").

Rispondi SOLO con JSON: {"intervieni": true, "motivo": "ragione breve"} oppure {"intervieni": false, "motivo": "ragione breve"}
"""


async def _group_should_intervene(
    text: str, caption: str, chat_id: int, from_id: int, first_name: str,
    bot_username: str = None, bot_mentioned: bool = False,
    has_media: bool = False, has_location: bool = False
) -> bool:
    """
    Decide con LLM se Genesi deve intervenire nel gruppo.
    Fast-path per mention/nome diretti. LLM per tutto il resto.
    """
    has_link = bool(re.search(r'https?://[^\s]+|www\.[^\s]+', f"{text} {caption}", re.IGNORECASE))
    if has_media or has_link or has_location:
        # Interviene sempre se viene inviato un elemento multimediale, un link o una posizione
        return True

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
        
    # Fast-path: pulsanti della tastiera → sempre sì
    if combined in ("🌦️ Meteo", "🤖 Aiuto"):
        return True

    combined_lower = combined.lower()

    # Fast-path: saluto di gruppo -> controlla limite temporale per-utente
    category = _get_greeting_category(combined_lower)
    if category:
        if chat_id in _FAMILY_GROUP_IDS or bot_mentioned:
            should_greet, is_late_wakeup = await _check_and_register_greeting(chat_id, str(from_id), category)
            if should_greet:
                # Registra il saluto: handle_update lo gestirà con il servizio
                # universale (group_greeting_service) o, se il messaggio non è
                # un saluto puro, con la pipeline normale (+ flag late_wakeup).
                _PENDING_GREETINGS[chat_id] = {
                    "from_id":     from_id,
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
        else:
            # Nei gruppi esterni interviene sui saluti solo se menzionata
            if _is_pure_greeting(combined_lower) and not has_media:
                return False

    # Fast-path: messaggio troppo corto e senza punto interrogativo → probabile scambio tra membri
    # Se c'è un elemento multimediale, bypassiamo questo controllo per consentire l'analisi del media.
    state = _GROUP_CONV_STATE.get(chat_id, {})
    last_ts = state.get("ts", 0)
    
    if len(combined) < 8 and "?" not in combined and not has_media:
        # Permetti comunque all'LLM di valutare se Genesi ha parlato da poco (follow-up implicito corto)
        if time.time() - last_ts > 300:  # 5 minuti
            return False

    last_user_id = state.get("from_id")
    
    # Continuità GENUINA: se Genesi stava parlando con QUESTA persona (entro 5 min) e
    # lei prosegue, è un follow-up diretto → interveniamo. (I trigger forti — nome, reply
    # in thread, media — sono già stati gestiti sopra e bypassano comunque.)
    if time.time() - last_ts < 300 and last_user_id == from_id:
        logger.info("GROUP_INTERVENE_DECISION chat_id=%s from=%s intervieni=True motivo=follow_up_diretto_stesso_utente", chat_id, first_name)
        return True

    # DOMANDA INEVASA: se nei commenti accumulati c'è una domanda di un'altra persona a
    # cui nessuno ha risposto, Genesi interviene per risponderle direttamente.
    try:
        from core.group_reactivity import find_unanswered_question
        if find_unanswered_question(await get_raw_messages(chat_id, limit=12),
                                    current_sender=first_name, group_id=chat_id):
            logger.info("GROUP_INTERVENE_DECISION chat_id=%s intervieni=True motivo=domanda_inevasa", chat_id)
            return True
    except Exception:
        pass

    # ANTI-FLIPPER: Genesi ha parlato da poco (< 3 min) e ora scrive un'ALTRA persona.
    # Tipico di una discussione tra umani (un lutto condiviso, uno sfogo, un racconto):
    # se è un'affermazione/reazione (non una domanda) NON intromettersi a raffica
    # rispondendo a ognuno. Resta in ascolto silenzioso — il messaggio è comunque salvato
    # nel "diario" del gruppo. I trigger forti (nome, reply in thread, media) sono già
    # gestiti sopra e bypassano. Se c'è una domanda esplicita, lascia decidere all'LLM
    # temperato (che distinguerà utilità reale da sfogo emotivo).
    if time.time() - last_ts < 180 and last_user_id and last_user_id != from_id and "?" not in combined:
        logger.info("GROUP_INTERVENE_DECISION chat_id=%s from=%s intervieni=False motivo=anti_flipper_discussione_tra_umani", chat_id, first_name)
        return False

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
        # Aggiungi l'ultima risposta di Genesi al contesto — così l'LLM può registrarne follow-up
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
        
        user_prefix = f"{from_id}:"
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

def clean_markdown_links(text: str) -> str:
    """Rimuove la sintassi markdown dei link lasciando solo il testo visualizzabile e rimuove URL nudi."""
    # 1. Rimuove markdown: [testo](url) -> testo, supportando 1 livello di parentesi nell'URL
    text = re.sub(r'\[([^\]]+)\]\(((?:[^)(]+|\([^)(]*\))*)\)', r'\1', text)
    # 2. Rimuove URL nudi dal testo
    text = re.sub(r'(?<!\S)(https?://[^\s\"\'\>]+|www\.[^\s\"\'\>]+)', '', text, flags=re.IGNORECASE)
    # 3. Pulisce spazi doppi
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_default_reply_markup(chat_type: str = "private", is_family: bool = False) -> dict | None:
    if chat_type == "private":
        return {
            "keyboard": [
                [{"text": "📍 Meteo (GPS)", "request_location": True}, {"text": "🌦️ Meteo"}],
                [{"text": "🤖 Aiuto"}]
            ],
            "resize_keyboard": True,
            "is_persistent": True
        }
    # Nei gruppi NESSUNA reply keyboard: la tastiera custom persistente
    # collide con quella di sistema (si apre dietro e non è cliccabile).
    # remove_keyboard pulisce anche quella vecchia rimasta nei client.
    # Meteo/Aiuto restano invocabili scrivendo "meteo" / "aiuto".
    return {"remove_keyboard": True}

def get_domain_name(url: str) -> str:
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain.startswith("www."):
            domain = domain[4:]
        if len(domain) > 20:
            domain = domain[:17] + "..."
        return domain
    except Exception:
        return "Sito"

def extract_webapp_urls(text: str) -> list[str]:
    # 1. Trova URL dai link markdown espliciti
    md_urls = re.findall(r'\[[^\]]+\]\(((?:[^)(]+|\([^)(]*\))*)\)', text)
    
    # 2. Trova URL nudi nel testo rimanente
    text_no_md = re.sub(r'\[[^\]]+\]\(((?:[^)(]+|\([^)(]*\))*)\)', '', text)
    raw_urls = re.findall(r'(https?://[^\s\"\'\>]+|www\.[^\s\"\'\>]+)', text_no_md, flags=re.IGNORECASE)
    
    cleaned_raw = []
    for u in raw_urls:
        u = u.rstrip(".,!?;:")
        # Se la parentesi non è bilanciata (es. trascinata dalla punteggiatura), rimuovila
        while u.count(')') > u.count('(') and u.endswith(')'):
            u = u[:-1]
        cleaned_raw.append(u)
        
    all_urls = md_urls + cleaned_raw

    valid_urls = []
    for url in all_urls:
        url_clean = url.rstrip(".,!?;:")
        if not _IMG_URL_RE.match(url_clean):
            # Forziamo a HTTPS per compatibilità con le Web App di Telegram
            if url_clean.lower().startswith("http://"):
                url_clean = "https://" + url_clean[7:]
            elif url_clean.lower().startswith("www."):
                url_clean = "https://" + url_clean
            
            if url_clean not in valid_urls:
                valid_urls.append(url_clean)
    return valid_urls

def build_webapp_inline_keyboard(urls: list[str], is_private: bool = True) -> dict:
    """
    Bottoni per i link delle fonti.
    - Chat private: bottone web_app → la pagina si apre DENTRO Telegram
    - Gruppi: bottone url classico (Telegram non supporta web_app nei gruppi)
    """
    keyboard = []
    for url in urls:
        domain = get_domain_name(url)
        if is_private:
            keyboard.append([
                {"text": f"🌐 Apri {domain}", "web_app": {"url": url}}
            ])
        else:
            keyboard.append([
                {"text": f"🌐 Apri {domain}", "url": url}
            ])
    return {"inline_keyboard": keyboard}

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

async def send_message(chat_id: int, text: str, reply_markup: dict = None, reply_to_message_id: int = None):
    if not text:
        return
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
        
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            res = await client.post(f"{TELEGRAM_API}/sendMessage", json=payload)
            if res.status_code != 200:
                logger.error("TELEGRAM_SEND_ERROR status=%d response=%s payload=%s", res.status_code, res.text, payload)
            else:
                log("TELEGRAM_SEND_OK", chat_id=chat_id, text=text, reply_markup=reply_markup, reply_to=reply_to_message_id)
        except Exception as e:
            logger.error("TELEGRAM_SEND_EXCEPTION chat_id=%s err=%s", chat_id, e)


async def send_photo(chat_id: int, photo_url: str, caption: str = "", reply_markup: dict = None):
    payload = {"chat_id": chat_id, "photo": photo_url}
    if caption:
        payload["caption"] = caption[:1024]
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            res = await client.post(f"{TELEGRAM_API}/sendPhoto", json=payload)
            if res.status_code != 200:
                logger.error("TELEGRAM_SEND_PHOTO_ERROR status=%d response=%s payload=%s", res.status_code, res.text, payload)
            else:
                log("TELEGRAM_SEND_PHOTO_OK", chat_id=chat_id, caption=caption, reply_markup=reply_markup)
            return res.status_code == 200
        except Exception as e:
            logger.error("TELEGRAM_SEND_PHOTO_EXCEPTION chat_id=%s err=%s", chat_id, e)
            return False


async def _handle_group_join(chat_id: int, msg: dict):
    """
    Genesi è appena stata aggiunta a un gruppo: dà un'occhiata ai
    partecipanti (admin visibili via API + profili membri già noti),
    capisce dove si trova (titolo) e si presenta ringraziando chi
    l'ha aggiunta e salutando per nome le persone che conosce.
    """
    try:
        title = msg.get("chat", {}).get("title", "questo gruppo")
        adder = msg.get("from", {}).get("first_name", "")
        is_family = chat_id in _FAMILY_GROUP_IDS
        log("TELEGRAM_GROUP_JOIN", chat_id=chat_id, title=title, adder=adder)

        # Registra il gruppo tra quelli noti (saluti proattivi futuri)
        try:
            from core.telegram_group_memory import register_known_group, get_member
            await register_known_group(chat_id, "telegram", title=title)
        except Exception:
            get_member = None

        # "Rapida occhiata ai partecipanti": l'API bot espone solo gli admin
        known_names: list[str] = []
        other_names: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(f"{TELEGRAM_API}/getChatAdministrators",
                                       params={"chat_id": chat_id})
                for adm in (res.json().get("result") or []):
                    u = adm.get("user", {})
                    if u.get("is_bot"):
                        continue
                    name = u.get("first_name", "")
                    if not name:
                        continue
                    known = False
                    if get_member:
                        try:
                            prof = await get_member(u.get("id"))
                            known = bool(prof and prof.get("first_name"))
                        except Exception:
                            pass
                    (known_names if known else other_names).append(name)
        except Exception as _pe:
            logger.debug("TELEGRAM_JOIN_PARTICIPANTS_ERR %s", _pe)

        await send_typing(chat_id)

        # Presentazione tramite il modulo UNICO/GLOBALE (stessa logica di WhatsApp/Meta).
        # I nomi degli admin diventano "partecipanti visibili" per un saluto su misura.
        from core.group_presentation import maybe_present_in_group
        participants = [{"name": n, "is_me": False} for n in (known_names + other_names)]
        intro = await maybe_present_in_group(
            platform="telegram",
            group_id_int=chat_id,
            group_name=title,
            participants=participants,
            adder_name=adder,
            is_family=is_family,
        )
        if intro:
            await send_message(chat_id, intro)
            log("TELEGRAM_GROUP_JOIN_GREETED", chat_id=chat_id,
                known=len(known_names), others=len(other_names))
    except Exception as e:
        logger.error("TELEGRAM_GROUP_JOIN_ERROR chat_id=%s err=%s", chat_id, e)


async def _welcome_new_member(chat_id: int, names: list[str]):
    """Benvenuto a un nuovo membro umano nel gruppo familiare."""
    try:
        await send_typing(chat_id)
        from core.llm_service import llm_service
        intro = await llm_service._call_model(
            "openai/gpt-4o-mini",
            "Sei Genesi, membro AI della famiglia in questo gruppo Telegram. "
            "Dai un benvenuto caloroso e breve (max 2 frasi, 1 emoji) ai nuovi "
            "arrivati, per nome.",
            f"Nuovi membri appena entrati: {', '.join(names)}",
            user_id=f"tg_welcome_{chat_id}", route="memory")
        if intro and intro.strip():
            await send_message(chat_id, intro.strip())
    except Exception as e:
        logger.debug("TELEGRAM_WELCOME_ERR %s", e)


async def send_typing(chat_id: int):
    """
    Mostra i puntini "sta scrivendo" e li mantiene attivi in background.
    Un singolo sendChatAction dura ~5s, ma il LLM può impiegare 10-20s:
    il keepalive bounded (4 refresh ≈ 20s) copre la costruzione della
    risposta. Telegram cancella i puntini automaticamente all'invio.
    """
    async def _keepalive():
        async with httpx.AsyncClient(timeout=5) as client:
            for i in range(4):
                try:
                    await client.post(f"{TELEGRAM_API}/sendChatAction",
                                      json={"chat_id": chat_id, "action": "typing"})
                except Exception:
                    break
                await asyncio.sleep(4.5)

    asyncio.create_task(_keepalive())


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
    global _BOT_USERNAME, _BOT_ID
    async with httpx.AsyncClient(timeout=10) as client:
        # Scopri username e id del bot
        try:
            me = await client.get(f"{TELEGRAM_API}/getMe")
            me_data = me.json().get("result", {})
            _BOT_USERNAME = me_data.get("username", "")
            _BOT_ID = me_data.get("id", 0)
            logger.info("TELEGRAM_BOT_USERNAME=%s id=%s", _BOT_USERNAME, _BOT_ID)
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
    from core.telegram_group_memory import get_member
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
            return d.get("content") or d.get("analysis") or d.get("summary") or d.get("message") or ""
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

async def _send_response(chat_id: int, reply: str, reply_to_message_id: int = None):
    """Invia la risposta: se contiene URL immagini le manda come foto Telegram."""
    # Cerca prima markdown immagini: ![alt](url)
    md_urls = _IMG_MD_RE.findall(reply)
    # Poi URL immagini pure nel testo
    raw_urls = _IMG_URL_RE.findall(reply)

    img_urls = md_urls + [u for u in raw_urls if u not in md_urls]

    # Estrae URL HTTPS per bottoni WebApp (non immagini)
    webapp_urls = extract_webapp_urls(reply)
    reply_markup = None
    if webapp_urls:
        reply_markup = build_webapp_inline_keyboard(webapp_urls, is_private=(chat_id > 0))
    else:
        reply_markup = get_default_reply_markup(
            chat_type="private" if chat_id > 0 else "group",
            is_family=(chat_id < 0)
        )

    if img_urls:
        # Rimuovi i link immagine dal testo per non mostrare URL grezze
        clean_text = _IMG_MD_RE.sub("", reply).strip()
        clean_text = _IMG_URL_RE.sub("", clean_text).strip()
        clean_text = clean_markdown_links(clean_text)

        for url in img_urls[:3]:  # max 3 immagini
            sent = await send_photo(chat_id, url, caption=clean_text if clean_text else "", reply_markup=reply_markup)
            if not sent:
                # Fallback: manda il testo con l'URL pulito da markdown
                await send_message(chat_id, clean_markdown_links(reply), reply_markup=reply_markup)
            clean_text = ""  # caption solo sulla prima
            reply_markup = None
        return

    # Risposta testuale normale
    clean_reply = clean_markdown_links(reply)
    if len(clean_reply) > 4000:
        for i in range(0, len(clean_reply), 4000):
            markup_to_send = reply_markup if i + 4000 >= len(clean_reply) else None
            await send_message(chat_id, clean_reply[i:i+4000], reply_markup=markup_to_send)
            await asyncio.sleep(0.3)
    else:
        await send_message(chat_id, clean_reply, reply_markup=reply_markup)


_WEBAPP_LINK  = "https://genesi.lucadigitale.eu/"
_WEBAPP_REG   = "https://genesi.lucadigitale.eu/register?from=telegram"
_BOT_USERNAME = ""   # popolato da set_webhook via getMe
_BOT_ID: int = 0     # popolato da set_webhook via getMe


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
    markup = get_default_reply_markup("private")
    if not city:
        session["state"] = STATE_AWAIT_CITY
        await storage.save(_session_key(chat_id), session)
        await send_message(chat_id, _WELCOME_MSG + "\n\n" + _WELCOME_CITY_PREAMBLE, reply_markup=markup)
    else:
        session["welcomed"] = True
        await storage.save(_session_key(chat_id), session)
        await send_message(chat_id, _WELCOME_MSG, reply_markup=markup)


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
        # Normalizzazione dei comandi rapidi (bottoni ReplyKeyboard)
        if text in ("🌦️ Meteo", "📍 Meteo (GPS)"):
            text = "Che tempo fa oggi?"
        # ── GENESI AGGIUNTA A UN GRUPPO: presentazione + ringraziamenti ──────
        _new_members = msg.get("new_chat_members") or []
        if _new_members and is_group:
            try:
                _bot_id = int(TELEGRAM_TOKEN.split(":")[0])
            except Exception:
                _bot_id = 0
            if any(m.get("id") == _bot_id for m in _new_members):
                asyncio.create_task(_handle_group_join(chat_id, msg))
                return
            # Nuovo membro umano nel gruppo familiare → benvenuto caloroso
            if chat_id in _FAMILY_GROUP_IDS:
                _names = [m.get("first_name", "") for m in _new_members
                          if not m.get("is_bot") and m.get("first_name")]
                if _names:
                    asyncio.create_task(_welcome_new_member(chat_id, _names))
                return

        # ── Fallback robusto presentazione: se Genesi si ritrova in un gruppo MAI
        #    salutato (es. evento di join perso mentre era offline), si presenta al
        #    primo messaggio utile. Stessa logica globale di WhatsApp/Meta, deduplicata
        #    sul registry: sui gruppi già noti è un semplice read e prosegue.
        if is_group:
            try:
                from core.group_presentation import maybe_present_in_group
                _intro = await maybe_present_in_group(
                    platform="telegram",
                    group_id_int=chat_id,
                    group_name=msg["chat"].get("title", "questo gruppo"),
                )
                if _intro:
                    await send_message(chat_id, _intro)
                    log("TELEGRAM_GROUP_PRESENTED_FALLBACK", chat_id=chat_id)
                    return
            except Exception as _pe:
                logger.debug("TG_GROUP_PRESENT_FALLBACK_ERR %s", _pe)

        photo      = msg.get("photo")       # lista di dimensioni
        voice      = msg.get("voice")       # messaggio vocale
        audio      = msg.get("audio")       # file audio generico
        document   = msg.get("document")    # documento (pdf, txt, ecc.)
        video      = msg.get("video")       # video
        animation  = msg.get("animation")   # gif/animazione
        video_note = msg.get("video_note")  # video note
        location   = msg.get("location")    # GPS location
        caption    = msg.get("caption", "").strip()

        # Reattività GLOBALE (stesso modulo di WhatsApp): segna l'arrivo del messaggio
        _msg_arrival = time.time()
        if is_group:
            from core.group_reactivity import mark_arrival as _mark_arrival
            _msg_arrival = _mark_arrival("telegram", chat_id, from_id)

        # Reply diretta a un messaggio di Genesi → fast-path SI + inietta contesto
        _reply_to_genesi = False
        _quoted_genesi_text = ""
        if is_group:
            reply_to = msg.get("reply_to_message", {})
            if reply_to:
                replied_from_id = reply_to.get("from", {}).get("id", 0)
                if _BOT_ID and replied_from_id == _BOT_ID:
                    _reply_to_genesi = True
                    _quoted_genesi_text = (reply_to.get("text") or reply_to.get("caption") or "").strip()
                    logger.info("REPLY_TO_GENESI from=%s chat=%s quoted_len=%s",
                                from_id, chat_id, len(_quoted_genesi_text))

        # Aggiorna profilo membro del gruppo ad ogni messaggio
        if is_group and first_name:
            asyncio.create_task(update_member_seen(from_id, first_name))
            # Servizio universale: estrae nome/città dai messaggi (regex gate + LLM)
            try:
                from core.group_greeting_service import group_greeting_service
                asyncio.create_task(group_greeting_service.extract_and_save_member_info(
                    platform_user_id=str(from_id),
                    first_name=first_name,
                    message=(text or caption or ""),
                    platform="telegram",
                    group_id=str(chat_id),
                    is_family_group=(chat_id in _FAMILY_GROUP_IDS),
                ))
            except Exception as _gge:
                logger.warning("GROUP_GREETING_EXTRACT_TASK_FAIL err=%s", _gge)
            # Estrai relazioni familiari e aggiorna albero genealogico di Alfio solo nel gruppo famiglia
            if chat_id in _FAMILY_GROUP_IDS:
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
            markup = get_default_reply_markup("private")
            if session.get("token"):
                name_part = f" {first_name}" if first_name else ""
                webapp = _WEBAPP_LINK
                await send_message(chat_id,
                    f"Bentornato{name_part}! Sono qui 👋\n\n"
                    f"Scrivimi, mandami foto o vocali.\n"
                    f"Webapp completa: {webapp}",
                    reply_markup=markup)
            else:
                session = {"state": STATE_IDLE}
                await storage.save(_session_key(session_uid), session)
                await send_message(chat_id,
                    f"Ciao {first_name}! 👋 Sono *Genesi*, il tuo assistente AI personale.\n\n"
                    f"Per usarmi al massimo hai bisogno di un account.\n\n"
                    f"• Hai già un account? Scrivi /login\n"
                    f"• Nuovo? Registrati qui in Telegram: /registrati\n"
                    f"  oppure sul sito: {_WEBAPP_REG}",
                    reply_markup=markup)
            return
        if text == "🤖 Aiuto":
            text = f"Ho premuto il pulsante Aiuto. Rispondi testualmente con questa esatta frase: 'Ciao {first_name}, dimmi come posso aiutarti.' e nient'altro per ora. Dal mio prossimo messaggio in poi, avvia un'intervista facendomi una domanda alla volta."

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
                # Esegui autologin silenzioso se l'utente è il proprietario (Alfio)
                if from_id == 494065944:
                    token = await _login("alfio.turrisi@gmail.com", "ZOEennio0810")
                    if token:
                        city = await _get_city(token)
                        session.update({
                            "token": token,
                            "email": "alfio.turrisi@gmail.com",
                            "password": "ZOEennio0810",
                            "city": city,
                            "state": STATE_IDLE,
                            "welcomed": True
                        })
                        await storage.save(_session_key(session_uid), session)

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

        # ── Pre-processing Media e Trascrizione Vocale ─────────────────────────
        _original_has_media = bool(photo or voice or audio or document or video or animation or video_note)
        _transcribed_voice_text = ""
        
        if voice or audio:
            await send_typing(chat_id)
            media = voice or audio
            audio_bytes = await download_file(media["file_id"])
            if audio_bytes:
                mime = media.get("mime_type", "audio/ogg")

                # Pipeline sensoriale universale: parlato, MA ANCHE musica e suoni
                transcription = ""
                _audio_desc = ""
                try:
                    from core.message_pipeline import process_incoming_audio
                    _ares = await process_incoming_audio(
                        session_id=str(chat_id) if is_group else str(from_id),
                        user_id=session_uid,
                        audio_bytes=audio_bytes,
                        platform="telegram",
                        content_type=mime,
                        caption=caption,
                    )
                    if _ares.get("kind") == "speech" and _ares.get("transcription"):
                        transcription = _ares["transcription"]
                    elif _ares.get("analysis"):
                        _audio_desc = _ares["analysis"]
                except Exception as _ape:
                    logger.warning("TELEGRAM_AUDIO_PIPELINE_ERR chat_id=%s err=%s", chat_id, _ape)

                # Fallback whisper classico se la pipeline non ha prodotto nulla
                if not transcription and not _audio_desc:
                    transcription = await _transcribe(token, audio_bytes, mime)
                    if transcription == "__TOKEN_EXPIRED__":
                        if is_group:
                            new_token = await _refresh_member_token(from_id)
                        else:
                            new_token = await _auto_refresh(session_uid, session)
                        if new_token:
                            token = new_token
                            transcription = await _transcribe(token, audio_bytes, mime)

                if transcription and transcription != "__TOKEN_EXPIRED__":
                    _transcribed_voice_text = transcription
                    text = transcription  # Aggiorna per i filtri successivi
                    voice = None
                    audio = None
                    if not is_group:
                        await send_message(chat_id, f"🎤 {transcription}")
                elif _audio_desc:
                    # Musica o suoni: il contenuto descritto diventa il messaggio
                    text = ((caption or "Ascolta questo audio.") +
                            f"\n\n[Contenuto audio: {_audio_desc}]")
                    _transcribed_voice_text = text
                    voice = None
                    audio = None
                else:
                    if not is_group:
                        await send_message(chat_id, "Non sono riuscita a capire il vocale. Prova a scrivere.")
                    return
            else:
                if not is_group:
                    await send_message(chat_id, "Non sono riuscita a scaricare il vocale.")
                return

        # ── FILTRO GRUPPI (LLM-based) ──────────────────────────────────────────
        # Salva ogni messaggio nel buffer grezzo PRIMA di decidere se intervenire,
        # così il contesto includerà anche i messaggi a cui Genesi non ha risposto.
        if is_group:
            msg_text = (text or caption or "").strip()
            if msg_text:
                asyncio.create_task(
                    append_raw_message(chat_id, from_id, first_name, msg_text)
                )
            try:
                from core.birthday_service import (
                    register_known_group, link_preseed_to_member, try_extract_birthday
                )
                chat_title = msg["chat"].get("title")
                asyncio.create_task(register_known_group(chat_id, "telegram", title=chat_title))
                asyncio.create_task(link_preseed_to_member(from_id, first_name))
                if msg_text:
                    asyncio.create_task(try_extract_birthday(from_id, first_name, msg_text))
            except Exception:
                pass

        # Genesi decide autonomamente se e quando intervenire nel gruppo.
        if is_group:
            # Fast-path: reply diretta a un messaggio di Genesi → sempre sì
            if _reply_to_genesi:
                should = True
            # Fast-path: in attesa di volti, il prossimo messaggio dell'utente potrebbe essere la risposta!
            elif await get_awaiting_faces(str(chat_id)):
                should = True
            else:
                should = await _group_should_intervene(
                    text, caption, chat_id, from_id, first_name,
                    bot_username=_BOT_USERNAME, bot_mentioned=_bot_mentioned,
                    has_media=_original_has_media, has_location=bool(location)
                )
            if not should:
                logger.info("TELEGRAM_GROUP_SILENT chat_id=%s from=%s msg=%.60s",
                            chat_id, first_name, f"{text} {caption}".strip())
                return
            
            # Rilevamento nomi per volti sconosciuti (usa handler centralizzato)
            _face_text = text if text else caption
            if _face_text:
                face_result = await handle_text_identification(str(chat_id), _face_text)
                if face_result["faces_saved"]:
                    if face_result["all_done"]:
                        text += face_result["sistema_msg"]
                    else:
                        text += face_result["sistema_msg"]

            
            # Se interveniamo su un vocale, invia prima la trascrizione
            if _transcribed_voice_text:
                await send_message(chat_id, f"🎤 {_transcribed_voice_text}")

            # ── SALUTO DI GRUPPO PERSONALIZZATO (servizio universale) ─────────
            _pending_greet = _PENDING_GREETINGS.pop(chat_id, None)
            if (_pending_greet and _pending_greet.get("from_id") == from_id
                    and time.time() - _pending_greet.get("ts", 0) < 60):
                _is_family = (chat_id in _FAMILY_GROUP_IDS)
                try:
                    from core.group_greeting_service import group_greeting_service
                    # Estrai info membro in background (non blocca la risposta)
                    asyncio.create_task(group_greeting_service.extract_and_save_member_info(
                        platform_user_id=str(from_id),
                        first_name=first_name,
                        message=(text or caption or ""),
                        platform="telegram",
                        group_id=str(chat_id),
                        is_family_group=_is_family,
                    ))
                    if _pending_greet.get("pure"):
                        # Saluto puro → risposta personalizzata diretta
                        # (nome + meteo locale + commento), senza pipeline LLM completa.
                        await send_typing(chat_id)
                        greet_reply = await group_greeting_service.build_personalized_greeting(
                            platform_user_id=str(from_id),
                            first_name=first_name,
                            greeting_category=_pending_greet.get("category", "general"),
                            platform="telegram",
                            group_id=str(chat_id),
                            is_family_group=_is_family,
                            is_late_wakeup=_pending_greet.get("late_wakeup", False),
                        )
                        if greet_reply:
                            await _send_response(chat_id, greet_reply,
                                                 reply_to_message_id=msg.get("message_id"))
                            _GROUP_CONV_STATE[chat_id] = {
                                "from_id":    from_id,
                                "ts":         time.time(),
                                "last_reply": greet_reply[:300],
                            }
                            asyncio.create_task(append_group_history(
                                chat_id, from_id, first_name,
                                (text or caption or ""), greet_reply))
                            log("GROUP_GREETING_SENT", platform="telegram",
                                chat_id=chat_id, user=from_id, name=first_name,
                                category=_pending_greet.get("category", ""))
                            return
                    else:
                        # Saluto + altro contenuto → pipeline normale, ma propaga
                        # il flag late_wakeup nella sessione (qui session è in scope).
                        if _pending_greet.get("late_wakeup"):
                            session["late_wakeup"] = True
                            await storage.save(_session_key(session_uid), session)
                except Exception as _ge:
                    logger.warning("GROUP_GREETING_PIPELINE_FALLBACK err=%s", _ge)
                    # fall-through: la pipeline normale gestirà il messaggio

        # In gruppi: appende il nome del mittente DOPO il messaggio per evitare
        # che il LLM mescoli il nome dell'account con quello del mittente.
        # Se il messaggio è solo emoji/reazione, segnala di rispondere brevemente.
        # Costruisce il contesto di gruppo arricchito (asincrono, cached per questo turno)
        _group_ctx_cache: list[str] = []

        async def _load_group_ctx() -> str:
            if not _group_ctx_cache:
                ctx = await build_group_context(
                    chat_id, from_id, first_name, current_message=text,
                    is_family_group=(chat_id in _FAMILY_GROUP_IDS)
                )
                _group_ctx_cache.append(ctx)
            return _group_ctx_cache[0]

        def _group_msg(message: str, group_ctx: str = "") -> str:
            if not is_group or not first_name:
                return message
            
            is_family_group = (chat_id in _FAMILY_GROUP_IDS)
            group_type_label = "GRUPPO FAMILIARE" if is_family_group else "GRUPPO ESTERNO"
            role_label = "naturale da familiare (non da assistente)" if is_family_group else "da assistente AI educata, utile e mai invadente"
            
            if is_family_group:
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

                extra_rules = (
                    f"zero intro elaborati, {domande_rule}zero 'che bello!'. "
                    f"IMPORTANTE: Sei Genesi (un'AI). Non sei la mamma o altri parenti. Non impersonare altri. Se gli utenti festeggiano qualcuno o fanno auguri ad altri nel gruppo, non ringraziare come se fossi tu la festeggiata, ma unisciti cordialmente ai festeggiamenti rivolti a quel familiare. "
                    f"NON menzionare eventi passati (malattie, problemi, notizie di giorni fa) "
                    f"a meno che {first_name} non li citi in questo messaggio. "
                    f"{photo_rules}"
                )
            else:
                extra_rules = (
                    f"Rispondi in modo estremamente conciso, al punto, senza chiacchiere. Non fare la finta amica, sei un'AI esterna. "
                    f"Fornisci il dato richiesto o rispondi alla domanda e fermati. Zero emoji eccessive. "
                    f"NON utilizzare o menzionare informazioni personali di altre chat. "
                )
                if chat_id == -1001267666655:
                    extra_rules += (
                        f"CONTESTO SPECIFICO GRUPPO: Questo gruppo era nato per programmatori Swift. Il creatore, Marcello, è mancato. "
                        f"Oggi gli utenti rimasti interagiscono ogni tanto per parlare delle loro app, che sono in maggioranza per dispositivi Apple. "
                        f"Tieni a mente questo contesto se fanno domande di programmazione, Apple o app. "
                        f"RISOLUZIONE DOMANDE: Quando viene fatta una domanda di cui conosci la risposta o che puoi cercare, usa le tue skill di ricerca web sui siti specializzati per fornire risposte coerenti e verificate, accompagnate possibilmente da link utili (inserendo un bottone al link esterno se supportato). "
                    )

            only_emoji = all(
                ord(c) > 127 or c in (' ', '\n') for c in message.strip()
            )
            if only_emoji:
                return (
                    f"{message}\n\n"
                    f"[{group_type_label}: scrive {first_name}. "
                    f"Reazione emoji — 1 riga max, naturale.]\n"
                    f"{group_ctx}"
                )
            return (
                f"{message}\n\n"
                f"[{group_type_label}: scrive {first_name}. "
                f"REGOLE ASSOLUTE: risposta misurata (3-4 righe max), tono {role_label}, "
                f"{extra_rules}"
                f"Rispondi SOLO a quello che viene detto adesso.]\n"
                f"{group_ctx}"
            )

        async def _do_chat(message: str) -> str:
            """Chat con auto-refresh del token in caso di scadenza."""
            nonlocal token
            try:
                from core.link_explorer import explore_links_in_text
                message = await explore_links_in_text(message)
            except Exception as e:
                logger.warning("TELEGRAM_LINK_EXPLORE_FAIL err=%s", e)

            # Per i gruppi: arricchisce il messaggio con contesto di gruppo
            if is_group:
                group_ctx = await _load_group_ctx()
                # Se è una reply diretta a un vecchio messaggio di Genesi,
                # preponi il testo citato così il proactor sa a cosa si riferisce
                msg_with_quote = message
                if _reply_to_genesi and _quoted_genesi_text:
                    msg_with_quote = (
                        f"[Stai rispondendo a questo tuo messaggio precedente: "
                        f"\"{_quoted_genesi_text[:300]}\"]\n{message}"
                    )
                enriched = _group_msg(msg_with_quote, group_ctx)

                # DOMANDA INEVASA: istruzione PRIORITARIA a rispondere alla persona giusta
                try:
                    from core.group_reactivity import find_unanswered_question, mark_question_handled
                    _uq = find_unanswered_question(await get_raw_messages(chat_id, limit=12),
                                                   current_sender=first_name, group_id=chat_id)
                    if _uq:
                        enriched = (
                            f"[ISTRUZIONE PRIORITARIA: nel gruppo {_uq['name']} aveva chiesto "
                            f"\"{_uq['text']}\" e nessuno le/gli ha ancora risposto. Rispondi PRIMA "
                            f"di tutto a {_uq['name']}, chiamandola/o per nome, con una risposta "
                            f"utile e concreta.]\n\n" + enriched
                        )
                        mark_question_handled(chat_id, _uq['text'])
                except Exception:
                    pass

                # Aggiungi il prompt per il risveglio tardivo se necessario
                if session.pop("late_wakeup", False):
                    await storage.save(_session_key(session_uid), session)
                    enriched += "\n[SISTEMA: Tu hai già dato il buongiorno al gruppo stamattina. Questo utente si è svegliato (o ha scritto) tardi e ti sta salutando adesso. Rispondi con affetto e, se opportuno, con una battuta scherzosa sul fatto che è un po' in ritardo, dandogli un caloroso benvenuto nella giornata! Ignora la regola del 'rispondi in modo estremamente conciso' per questa interazione.]"
                    
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
                asyncio.create_task(append_group_history(chat_id, from_id, first_name, message, reply))
                asyncio.create_task(record_group_observation(chat_id, from_id, first_name, message, reply))
                asyncio.create_task(detect_and_save_correction(chat_id, from_id, first_name, message, reply))
                asyncio.create_task(consolidate_group_insights_if_needed(chat_id))
                asyncio.create_task(summarize_group_discussion_if_needed(chat_id))
                
                is_family_group = (chat_id in _FAMILY_GROUP_IDS)
                if is_family_group:
                    asyncio.create_task(_sync_family_background(chat_id))

                # Rilevamento Risoluzione Episodi della Famiglia in background
                async def _tg_episode_resolution():
                    try:
                        from core.episode_memory import episode_memory as _em
                        _clean_msg = _strip_group_ctx(message)
                        await _em.resolve_episodes(session_uid, _clean_msg)
                    except Exception as _e:
                        logger.warning("EPISODE_RESOLUTION_BG_ERROR_TG: %s", _e)
                if is_family_group:
                    asyncio.create_task(_tg_episode_resolution())

                # Nuovo: rileva cambiamenti dichiarati/eventi personali
                from core.telegram_group_memory import detect_and_save_event_change
                async def _tg_event_change():
                    event = await detect_and_save_event_change(chat_id, from_id, first_name, message)
                    if event:
                        # Se il cambiamento è "importante" o ambiguo, Genesi può chiedere conferma/discretamente
                        event_type = event.get("event_type")
                        matched = event.get("matched_text", "")
                        if event_type in ("lavoro", "trasloco", "salute", "ferie", "rientro", "traguardo"):
                            # Risposta discreta: solo se non già confermato di recente
                            await send_message(chat_id,
                                f"{first_name}, confermi che {matched.lower()}? (Se vuoi, posso ricordartelo per il futuro)")
                asyncio.create_task(_tg_event_change())

                # Livello 4: memoria personale del mittente — episodi e fatti su testo pulito
                _raw_msg = _strip_group_ctx(message)
                if _raw_msg and len(_raw_msg) > 10:
                    _mem_msg  = _raw_msg
                    _mem_resp = reply
                    _mem_session_uid = session_uid  # uid del proprietario (Alfio) — il solo con memoria persistente

                    if is_family_group:
                        from core.message_pipeline import schedule_memory_tasks
                        asyncio.create_task(schedule_memory_tasks(
                            user_id=_mem_session_uid,
                            user_message=f"{first_name}: {_mem_msg}",
                            response=_mem_resp,
                            platform="telegram",
                            is_group=True,
                        ))

            return reply

        async def _handle_reply(reply: str) -> bool:
            """Invia la risposta; ritorna False se auth fallita definitivamente."""
            if reply == "__AUTH_FAILED__" or reply == "__TOKEN_EXPIRED__":
                await send_message(chat_id,
                    "Non riesco ad autenticarti. Usa /login per riconnetterti.")
                return False
            
            # Reattività: se mentre Genesi elaborava la STESSA persona ha già scritto un
            # nuovo messaggio, questa risposta è ormai stantia (ha perso il contesto) →
            # la scartiamo. Il messaggio nuovo riceverà una risposta fresca e pertinente.
            from core.group_reactivity import is_superseded as _is_superseded
            if is_group and not _original_has_media and _is_superseded("telegram", chat_id, from_id, _msg_arrival):
                logger.info("GROUP_STALE_RESPONSE_SKIPPED chat_id=%s from=%s waited=%.1fs",
                            chat_id, first_name, time.time() - _msg_arrival)
                return

            # Legge il message_id originale per poter rispondere in thread se in gruppo
            reply_to = msg.get("message_id") if is_group else None
            await _send_response(chat_id, reply, reply_to_message_id=reply_to)
            
            # Traccia con chi Genesi stava conversando (per il fast-path del filtro)
            if is_group:
                _GROUP_CONV_STATE[chat_id] = {
                    "from_id":    from_id,
                    "ts":         time.time(),
                    "last_reply": reply[:300],
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
                if is_group:
                    new_token = await _refresh_member_token(from_id)
                else:
                    new_token = await _auto_refresh(session_uid, session)
                if new_token:
                    token = new_token
                    analysis = await _upload_file(token, img_bytes, "photo.jpg", "image/jpeg")
                else:
                    analysis = ""
            user_msg  = caption or "Analizza questa immagine che ti ho inviato."
            if analysis and analysis != "__TOKEN_EXPIRED__":
                # Handler centralizzato per identificazione volti/animali
                _photo_session = str(chat_id) if is_group else str(from_id)
                photo_result = await handle_photo_identification(
                    _photo_session, img_bytes, analysis, caption=caption
                )
                user_msg = f"{user_msg}\n\n[Contenuto immagine: {analysis}]"
                if photo_result["sistema_msg"]:
                    user_msg += photo_result["sistema_msg"]

            media_group_id = msg.get("media_group_id")
            if media_group_id:
                # Accumula messaggi per gli album
                key = f"media_group_desc:{media_group_id}"
                desc_list = await storage.load(key) or []
                desc_list.append(user_msg)
                await storage.save(key, desc_list)
                
                # Debounce: aspetta per vedere se arrivano altre foto dell'album
                msg_id = msg.get("message_id")
                await storage.save(f"media_group_latest:{media_group_id}", msg_id)
                await asyncio.sleep(4.0)
                latest = await storage.load(f"media_group_latest:{media_group_id}")
                if latest != msg_id:
                    # Non è l'ultima foto arrivata, interrompi qui l'esecuzione silente
                    return
                
                # È l'ultima foto dell'album: concatena le descrizioni
                all_descs = await storage.load(key) or []
                if len(all_descs) > 1:
                    user_msg = f"L'utente ha inviato un album di {len(all_descs)} foto.\n"
                    for idx, d in enumerate(all_descs):
                        user_msg += f"\n--- FOTO {idx+1} ---\n{d}\n"
                
                # Pulizia cache
                await storage.save(key, [])
                await storage.save(f"media_group_latest:{media_group_id}", 0)

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

            # Audio/video inviati come FILE (es. inoltri da WhatsApp):
            # vanno alla pipeline sensoriale, non al percorso documenti
            if mime.startswith("audio/") or mime.startswith("video/"):
                try:
                    from core.message_pipeline import process_incoming_audio, process_incoming_video
                    _sess = str(chat_id) if is_group else str(from_id)
                    if mime.startswith("audio/"):
                        _mres = await process_incoming_audio(
                            session_id=_sess, user_id=session_uid,
                            audio_bytes=doc_bytes, platform="telegram",
                            content_type=mime, caption=caption)
                        _manalysis = _mres.get("analysis", "")
                        if _mres.get("kind") == "speech" and _mres.get("transcription"):
                            await send_message(chat_id, f"🎤 {_mres['transcription']}")
                            reply = await _do_chat(_mres["transcription"])
                        elif _manalysis:
                            reply = await _do_chat(
                                (caption or f"Ascolta questo audio ({filename}).") +
                                f"\n\n[Contenuto audio: {_manalysis}]")
                        else:
                            reply = await _do_chat(
                                (caption or f"Ti ho inviato un audio ({filename}).") +
                                "\n\n[SISTEMA: analisi audio non riuscita — rispondi con "
                                "curiosità, senza fingere di averlo sentito.]")
                    else:
                        _mres = await process_incoming_video(
                            session_id=_sess, user_id=session_uid,
                            video_bytes=doc_bytes, platform="telegram", caption=caption)
                        _manalysis = _mres.get("analysis", "")
                        if _manalysis:
                            reply = await _do_chat(
                                (caption or f"Guarda questo video ({filename}).") +
                                f"\n\n[Contenuto video: {_manalysis}]" +
                                (_mres.get("sistema_msg") or ""))
                        else:
                            reply = await _do_chat(
                                (caption or f"Ti ho inviato un video ({filename}).") +
                                "\n\n[SISTEMA: analisi video non riuscita — rispondi con "
                                "curiosità, senza fingere di averlo visto.]")
                    if not await _handle_reply(reply):
                        return
                    logger.info("TELEGRAM_MEDIA_DOC_OK chat_id=%s mime=%s", chat_id, mime)
                    return
                except Exception as _mde:
                    logger.warning("TELEGRAM_MEDIA_DOC_ERR chat_id=%s err=%s", chat_id, _mde)
                    # fall-through al percorso documenti classico

            analysis = await _upload_file(token, doc_bytes, filename, mime)
            if analysis == "__TOKEN_EXPIRED__":
                if is_group:
                    new_token = await _refresh_member_token(from_id)
                else:
                    new_token = await _auto_refresh(session_uid, session)
                if new_token:
                    token = new_token
                    analysis = await _upload_file(token, doc_bytes, filename, mime)
                else:
                    analysis = ""
            user_msg  = caption or f"Ho inviato il documento: {filename}."
            if analysis and analysis != "__TOKEN_EXPIRED__":
                _doc_session = str(chat_id) if is_group else str(from_id)
                doc_result = await handle_photo_identification(
                    _doc_session, doc_bytes, analysis, caption=caption
                )
                user_msg = f"{user_msg}\n\n[Contenuto: {analysis}]"
                if doc_result["sistema_msg"]:
                    user_msg += doc_result["sistema_msg"]

            reply = await _do_chat(user_msg)
            if not await _handle_reply(reply):
                return
            logger.info("TELEGRAM_DOCUMENT_OK chat_id=%s filename=%s", chat_id, filename)
            return

        # ── POSIZIONE (Location) ─────────────────────────────────────────────
        if location:
            await send_typing(chat_id)
            lat = location["latitude"]
            lon = location["longitude"]
            from core.location_resolver import reverse_geocode
            city_name = await reverse_geocode(lat, lon)
            if city_name:
                if is_group:
                    await save_member_city(from_id, city_name)
                else:
                    if session.get("token"):
                        await _save_city(session["token"], city_name)
                    session["city"] = city_name
                    await storage.save(_session_key(session_uid), session)
                reply = await _do_chat(f"[L'utente ha inviato la sua posizione GPS: {city_name}] Dimmi le previsioni meteo per {city_name}.")
                if not await _handle_reply(reply):
                    return
                logger.info("TELEGRAM_LOCATION_OK chat_id=%s city=%s", chat_id, city_name)
            else:
                await send_message(chat_id, "Ho ricevuto la tua posizione, ma non sono riuscita a determinare il nome della città esatta per il meteo.")
            return

        # ── VIDEO / ANIMATION / VIDEO_NOTE ─────────────────────────────────────
        if video or animation or video_note:
            await send_typing(chat_id)
            media = video or animation or video_note
            user_msg = caption or "Guarda questo video/animazione."

            # Analisi reale del video (frame + vision + biometria) — pipeline universale
            _video_analysis = ""
            _video_sistema = ""
            try:
                _size = media.get("file_size", 0)
                if _size and _size <= 50 * 1024 * 1024:
                    _vbytes = await download_file(media["file_id"])
                    if _vbytes:
                        from core.message_pipeline import process_incoming_video
                        _vres = await process_incoming_video(
                            session_id=str(chat_id) if is_group else str(from_id),
                            user_id=session_uid,
                            video_bytes=_vbytes,
                            platform="telegram",
                            caption=caption,
                        )
                        _video_analysis = _vres.get("analysis", "")
                        _video_sistema = _vres.get("sistema_msg", "")
            except Exception as _ve:
                logger.warning("TELEGRAM_VIDEO_ANALYSIS_ERR chat_id=%s err=%s", chat_id, _ve)

            if _video_analysis:
                reply = await _do_chat(f"{user_msg}\n\n[Contenuto video: {_video_analysis}]{_video_sistema}")
            else:
                reply = await _do_chat(
                    f"{user_msg}\n\n[SISTEMA: l'utente ha inviato un video ma l'analisi "
                    "non è riuscita. Rispondi con curiosità, senza fingere di averlo visto.]")
            if not await _handle_reply(reply):
                return
            logger.info("TELEGRAM_VIDEO_OK chat_id=%s analyzed=%s", chat_id, bool(_video_analysis))
            return

        # ── VOCALE / AUDIO ─────────────────────────────────────────────────────
        if voice or audio:
            await send_typing(chat_id)
            media      = voice or audio
            audio_bytes = await download_file(media["file_id"])
            if not audio_bytes:
                await send_message(chat_id, "Non riuscito a scaricare il vocale.")
                return

            mime = (voice or audio).get("mime_type", "audio/ogg")

            # Analisi audio universale: parlato, ma anche musica e suoni
            try:
                from core.message_pipeline import process_incoming_audio
                _ares = await process_incoming_audio(
                    session_id=str(chat_id) if is_group else str(from_id),
                    user_id=session_uid,
                    audio_bytes=audio_bytes,
                    platform="telegram",
                    content_type=mime,
                    caption=caption,
                )
                _akind = _ares.get("kind")
                _atrans = _ares.get("transcription")
                _aanalysis = _ares.get("analysis", "")
                if _akind == "speech" and _atrans:
                    # Parlato: comportamento classico (eco trascrizione + chat)
                    await send_message(chat_id, f"🎤 {_atrans}")
                    _audio_msg = _atrans
                    if _aanalysis and _aanalysis != _atrans:
                        _audio_msg += f"\n\n[Contesto audio: {_aanalysis}]"
                    reply = await _do_chat(_audio_msg)
                    if not await _handle_reply(reply):
                        return
                    logger.info("TELEGRAM_AUDIO_OK chat_id=%s kind=speech", chat_id)
                    return
                elif _aanalysis:
                    # Musica o suoni: rispondi alla descrizione
                    reply = await _do_chat(
                        (caption or "Ascolta questo audio.") +
                        f"\n\n[Contenuto audio: {_aanalysis}]")
                    if not await _handle_reply(reply):
                        return
                    logger.info("TELEGRAM_AUDIO_OK chat_id=%s kind=%s", chat_id, _akind)
                    return
            except Exception as _ae:
                logger.warning("TELEGRAM_AUDIO_PIPELINE_ERR chat_id=%s err=%s", chat_id, _ae)

            # Fallback: flusso STT classico (zero regressioni)
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

        # Rilevamento nomi per volti sconosciuti (usa handler centralizzato)
        face_result = await handle_text_identification(str(chat_id) if is_group else str(from_id), text)
        if face_result["was_awaiting"] and face_result["faces_saved"]:
            text += face_result["sistema_msg"]


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
