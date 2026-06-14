"""
BIRTHDAY SERVICE — Genesi
Gestisce compleanni per tutti gli utenti e gruppi:
  - Web app: profilo individuale (data nascita → alert al primo messaggio del giorno)
  - Telegram gruppo: invio proattivo alle 6:00, dati da storage o pre-seed
  - WhatsApp 1:1: invio proattivo alle 6:00 (solo utenti privati, non gruppi)
  - Auto-estrazione: rileva data di nascita dai messaggi del gruppo
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo

from core.storage import storage
from core.log import log

# Baileys HTTP send endpoint (Node.js locale)
_BAILEYS_SEND_URL    = os.getenv("BAILEYS_SEND_URL", "http://127.0.0.1:3001/send")
_BAILEYS_SEND_SECRET = os.getenv("BAILEYS_SEND_SECRET", "")

# Gruppo WhatsApp ID (jid Baileys) — es. "39...-...@g.us"
_WA_GROUP_JID = os.getenv("WA_GROUP_JID", "")

# Gruppo WhatsApp che riceve OGNI MATTINA, a corredo del saluto, un'immagine
# generata coerente con il testo del saluto e col meteo del posto (solo questo gruppo).
_WA_MORNING_IMAGE_JID = os.getenv("WA_MORNING_IMAGE_JID", "393298879304-1482062977@g.us")

logger = logging.getLogger(__name__)
_TZ = ZoneInfo("Europe/Rome")

# ── Algoritmi Festività Italiane e Locali dei Membri ──────────────────────────

def get_easter_date(year: int) -> date:
    """Calcola la data della Pasqua per un dato anno (algoritmo di Meeus/Jones/Butcher)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d_val = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d_val - g + 15) % 30
    i = c // 4
    k = c % 4
    L = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * L) // 451
    month = (h + L - 7 * m + 114) // 31
    day = ((h + L - 7 * m + 114) % 31) + 1
    return date(year, month, day)

def get_italian_holiday(d: date) -> str | None:
    """Ritorna il nome della festività nazionale italiana se oggi è un giorno festivo."""
    fixed = {
        (1, 1): "Capodanno",
        (1, 6): "Epifania",
        (4, 25): "Festa della Liberazione",
        (5, 1): "Festa del Lavoro",
        (6, 2): "Festa della Repubblica",
        (8, 15): "Ferragosto (Assunzione di Maria)",
        (11, 1): "Tutti i Santi",
        (12, 8): "Immacolata Concezione",
        (12, 25): "Natale",
        (12, 26): "Santo Stefano",
    }
    
    if (d.month, d.day) in fixed:
        return fixed[(d.month, d.day)]
        
    from datetime import timedelta
    easter = get_easter_date(d.year)
    if d == easter:
        return "Pasqua"
    if d == easter + timedelta(days=1):
        return "Lunedì dell'Angelo (Pasquetta)"
        
    return None

_PATRONAL_FEASTS = {
    "roma": (6, 29, "Santi Pietro e Paolo"),
    "milano": (12, 7, "Sant'Ambrogio"),
    "torino": (6, 24, "San Giovanni Battista"),
    "napoli": (9, 19, "San Gennaro"),
    "firenze": (6, 24, "San Giovanni Battista"),
    "genova": (6, 24, "San Giovanni Battista"),
    "venezia": (4, 25, "San Marco"),
    "catania": (2, 5, "Sant'Agata"),
    "palermo": (7, 15, "Santa Rosalia"),
    "bari": (12, 6, "San Nicola"),
    "imola": (8, 13, "San Cassiano"),
    "bracciano": (1, 20, "San Sebastiano"),
}

def get_local_holiday(d: date, city: str) -> str | None:
    """Ritorna la festività patronale della città se coincide con oggi."""
    if not city:
        return None
    city_lower = city.lower().strip()
    if city_lower in _PATRONAL_FEASTS:
        m, day, name = _PATRONAL_FEASTS[city_lower]
        if d.month == m and d.day == day:
            return f"Festa patronale di {name} a {city.capitalize()}"
    return None

async def get_group_members_locations(chat_id: int) -> dict[str, str]:
    """Mappa {nome: città} dei membri attivi del gruppo.

    FONTE PRIMARIA: le città REALI dichiarate dai membri ("vivo a X"), salvate da
    group_greeting_service in `group_member_profile`. La città è una proprietà della
    PERSONA: per ogni nome si tiene la voce più recente (preferendo lo stesso gruppo).
    Il fallback statico interviene SOLO per i membri attivi senza città reale.
    """
    locations: dict[str, str] = {}

    # 1. Membri attivi di questo gruppo (chi ha scritto)
    active_names = None
    if chat_id != 0:
        try:
            from core.telegram_group_memory import get_active_group_members
            active_names = await get_active_group_members(chat_id)
        except Exception:
            pass

    # 2. FONTE PRIMARIA — città reali da group_member_profile
    try:
        import os
        base_dir = "memory/group_member_profile"
        gid = str(chat_id)
        best: dict[str, tuple] = {}  # name_lower -> (name, rank, city)
        if os.path.isdir(base_dir):
            for fn in os.listdir(base_dir):
                if not fn.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(base_dir, fn), encoding="utf-8") as f:
                        d = json.load(f)
                except Exception:
                    continue
                if not isinstance(d, dict):
                    continue
                name = (d.get("name") or "").strip()
                city = (d.get("city") or "").strip()
                if not name or not city:
                    continue
                same_group = (chat_id == 0) or (str(d.get("group_id") or "") == gid)
                ts = int(d.get("city_updated_at") or d.get("last_seen") or 0)
                rank = (1 if same_group else 0, ts)  # stesso gruppo > più recente
                nl = name.lower()
                if nl not in best or rank > best[nl][1]:
                    best[nl] = (name, rank, city)
        for nl, (name, _rank, city) in best.items():
            if active_names is None or name in active_names:
                locations[name] = city
    except Exception as e:
        logger.warning("Error getting group members locations: %s", e)

    # 3. FALLBACK statico — SOLO per colmare i buchi (membro attivo senza città reale).
    #    NB: la famiglia Turrisi è a Imola (Alfio NON è a Roma: era un default errato).
    known_fallbacks = {
        "Alfio": "Imola",
        "Rita": "Imola",
        "Zoe": "Imola",
        "Ennio": "Imola",
        "Iolanda": "Catania",
        "Sandra": "Milano",
        "Mariella": "Torino",
        "Katia": "Catania",
    }
    is_family_context = (chat_id == 0) or (chat_id in (-5007188402, -318483633))
    for k, v in known_fallbacks.items():
        if k in locations:
            continue  # città reale già nota → il fallback non la tocca
        if active_names is None or k in active_names or is_family_context:
            locations[k] = v

    return locations

async def get_today_events_context(chat_id: int) -> str:
    """Costruisce una descrizione testuale delle festività e dei compleanni odierni per l'LLM."""
    tz = ZoneInfo("Europe/Rome")
    today = datetime.now(tz).date()
    
    lines = []
    
    # 1. Giorno della settimana e data
    giorni_settimana = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
    giorno_nome = giorni_settimana[today.weekday()]
    lines.append(f"Oggi è {giorno_nome}, {today.strftime('%d/%m/%Y')}.")
    
    # 2. Festività Nazionale
    hol = get_italian_holiday(today)
    if hol:
        lines.append(f"FESTIVITÀ NAZIONALE IN ITALIA: Oggi è {hol}!")
    else:
        is_weekend = today.weekday() in (5, 6)
        if is_weekend:
            lines.append("Oggi è un giorno del weekend (sabato/domenica).")
        else:
            lines.append("Oggi è un normale giorno feriale lavorativo.")
            
    # 3. Feste Patronali dei Membri
    locations = await get_group_members_locations(chat_id)
    local_hols = []
    for name, city in locations.items():
        loc_hol = get_local_holiday(today, city)
        if loc_hol:
            local_hols.append(f"• {name} a {city.capitalize()}: {loc_hol}")
    if local_hols:
        lines.append("FESTIVITÀ LOCALI DEI MEMBRI DEL GRUPPO OGGI:")
        lines.extend(local_hols)
        
    # 4. Compleanni di Oggi
    birthdays_today = []
    member_ids_to_check = set()
    for name_lower in _PRESEED_TELEGRAM:
        member_ids_to_check.add(f"tg:name:{name_lower}")
    try:
        for _mid in _all_birthday_member_ids():
            member_ids_to_check.add(_mid)
    except Exception:
        pass
        
    for member_id in member_ids_to_check:
        try:
            if member_id.startswith("tg:name:"):
                name_lower = member_id[len("tg:name:"):]
                if name_lower not in _PRESEED_TELEGRAM:
                    continue
                birthdate, display_name = _PRESEED_TELEGRAM[name_lower]
            else:
                data = await get_birthday(member_id)
                if not data:
                    continue
                birthdate = data.get("birthdate", "")
                display_name = data.get("name", member_id)
            
            if birthdate and _is_birthday_today(birthdate, today):
                age = _calc_age(birthdate, today)
                birthdays_today.append((display_name, age))
        except Exception:
            pass
            
    if birthdays_today:
        lines.append("COMPLEANNI DA FESTEGGIARE OGGI NELLA FAMIGLIA:")
        for name, age in birthdays_today:
            age_info = f"compie {age} anni!" if age else "compie gli anni oggi!"
            lines.append(f"• {name}: {age_info}")
            
    return "\n".join(lines)


# ── Chiavi storage ─────────────────────────────────────────────────────────────

def _bday_key(member_id: str) -> str:
    """Chiave universale: può essere user_id webapp, 'tg:{from_id}', 'wa:{wa_id}'."""
    return f"birthday:{member_id}"


def _all_birthday_member_ids() -> list[str]:
    """
    Enumera TUTTI i compleanni salvati leggendo da DISCO (memory/birthday/*.json),
    non dalla cache in-memory storage._storage (che dopo un riavvio è vuota e farebbe
    perdere gli auguri). Ritorna i member_id (es. 'wa:39...', 'tg:123', user_id webapp).
    """
    out: list[str] = []
    try:
        base = getattr(storage, "base_path", "memory")
        bdir = os.path.join(base, "birthday")
        for fn in os.listdir(bdir):
            if not fn.endswith(".json"):
                continue
            mid = fn[:-5]
            if mid in ("known_groups",) or mid.startswith("sent:"):
                continue
            out.append(mid)
    except Exception:
        pass
    return out

def _known_groups_key() -> str:
    return "birthday:known_groups"

def _sent_today_key(year: int) -> str:
    return f"birthday:sent:{year}"

# ── Pre-seed dati gruppo Telegram ──────────────────────────────────────────────

# Formato: {first_name_lower: (birthdate_iso, display_name)}
# from_id verrà collegato automaticamente quando il membro scrive
_PRESEED_TELEGRAM = {
    "alfio":    ("1980-02-11", "Alfio"),
    "rita":     ("1969-07-25", "Rita"),
    "zoe":      ("2008-04-28", "Zoe"),
    "ennio":    ("2010-10-19", "Ennio"),
    "iolanda":  ("1954-05-22", "Iolanda"),
    "sandra":   ("1975-10-11", "Sandra"),
    "mariella": ("1971-08-21", "Mariella"),
    "katia":    ("1986-08-04", "Katia"),
    "elena":    ("2013-09-14", "Elena"),
    "gianluca": ("1985-08-17", "Gianluca"),
    "leo":      ("2010-07-21", "Leo"),
    "gianvito": ("1979-04-18", "Gianvito"),
}


# ── Storage helpers ────────────────────────────────────────────────────────────

async def save_birthday(member_id: str, birthdate_iso: str, name: str = "",
                         platform: str = "webapp"):
    """Salva data di nascita per qualsiasi membro/utente."""
    data = await storage.load(_bday_key(member_id), default={}) or {}
    data["birthdate"] = birthdate_iso  # "YYYY-MM-DD"
    data["name"]      = name
    data["platform"]  = platform
    await storage.save(_bday_key(member_id), data)


async def get_birthday(member_id: str) -> dict:
    """Ritorna {"birthdate": "YYYY-MM-DD", "name": ..., "platform": ...} o {}."""
    return await storage.load(_bday_key(member_id), default={}) or {}


async def register_known_group(chat_id: int, platform: str = "telegram", title: str = None):
    """Registra un gruppo attivo (chiamato al primo messaggio ricevuto)."""
    known = await storage.load(_known_groups_key(), default=[]) or []
    entry = {"chat_id": chat_id, "platform": platform}
    if entry not in known:
        known.append(entry)
        await storage.save(_known_groups_key(), known)
    if title:
        await storage.save(f"group_title:{chat_id}", title)


async def get_known_groups() -> list:
    return await storage.load(_known_groups_key(), default=[]) or []


# ── Auto-linking: collega first_name a from_id per il pre-seed ────────────────

async def link_preseed_to_member(from_id: int, first_name: str):
    """
    Quando un membro del gruppo Telegram scrive, verifica se il suo nome
    è nel pre-seed e, se non ha già una birthday salvata, la crea.
    """
    member_id = f"tg:{from_id}"
    existing = await get_birthday(member_id)
    if existing.get("birthdate"):
        return  # già noto

    name_key = first_name.strip().lower()
    if name_key in _PRESEED_TELEGRAM:
        birthdate, display = _PRESEED_TELEGRAM[name_key]
        await save_birthday(member_id, birthdate, display, "telegram_group")
        log("BIRTHDAY_PRESEED_LINKED", from_id=from_id, name=display, birthdate=birthdate)


# ── Auto-estrazione data di nascita dai messaggi ──────────────────────────────

import re as _re

_BDAY_PATTERNS = [
    # "sono nato il 15 marzo 1990", "nata il 3/5/1985"
    _re.compile(
        r"nat[oae]\s+il?\s+(\d{1,2})[\/\-\s](\d{1,2}|\w+)[\/\-\s](\d{4})",
        _re.IGNORECASE
    ),
    # "il mio compleanno è il 15 marzo", "compie gli anni il 4 agosto"
    _re.compile(
        r"(?:compleanno|compie\s+gli\s+anni|festeggio|festeggiamo)\s+.*?il\s+(\d{1,2})[\/\-\s](\d{1,2}|\w+)(?:[\/\-\s](\d{4}))?",
        _re.IGNORECASE
    ),
    # "ho 45 anni" (meno preciso — usato solo se ha anche una data)
]

_MONTH_MAP = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_date_from_match(day_s: str, month_s: str, year_s: str) -> str | None:
    """Prova a costruire una data ISO da componenti estratti dal testo."""
    try:
        day = int(day_s)
        month = int(month_s) if month_s.isdigit() else _MONTH_MAP.get(month_s.lower())
        if not month:
            return None
        year = int(year_s) if year_s else None
        if year and (year < 1920 or year > date.today().year):
            return None
        if not (1 <= day <= 31 and 1 <= month <= 12):
            return None
        if year:
            return date(year, month, day).isoformat()
        else:
            return f"????-{month:02d}-{day:02d}"  # anno sconosciuto
    except Exception:
        return None


async def try_extract_birthday(from_id: int | str, first_name: str, text: str):
    """
    Analizza un messaggio; se contiene una data di nascita la salva.
    from_id: int → telegram from_id; str → user_id webapp (saltato il prefisso tg:)
    Fail-silent. Chiamato in background.
    """
    if not text or len(text) < 8:
        return
    if isinstance(from_id, str):
        member_id = from_id  # webapp user_id diretto
    else:
        member_id = f"tg:{from_id}"
    existing = await get_birthday(member_id)
    if existing.get("birthdate") and "????" not in existing.get("birthdate", ""):
        return  # già completo

    for pattern in _BDAY_PATTERNS:
        m = pattern.search(text)
        if m:
            groups = m.groups()
            day_s   = groups[0] if len(groups) > 0 else ""
            month_s = groups[1] if len(groups) > 1 else ""
            year_s  = groups[2] if len(groups) > 2 and groups[2] else ""
            bdate = _parse_date_from_match(day_s, month_s, year_s)
            if bdate:
                await save_birthday(member_id, bdate, first_name, "telegram_group")
                log("BIRTHDAY_AUTO_EXTRACTED", from_id=from_id, name=first_name,
                    birthdate=bdate)
                return


_MONTH_NAMES_IT = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
                   "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


async def parse_birthdate_freeform(text: str) -> str:
    """
    Estrae una data di nascita da testo libero in QUALSIASI formato.
    Ritorna ISO 'YYYY-MM-DD', oppure '????-MM-DD' se l'anno manca, oppure '' se assente.
    Prima i pattern regex; poi fallback LLM per formati liberi ("il dodici marzo del '78").
    """
    if not text or not text.strip():
        return ""
    # 1. Pattern regex esistenti
    for pattern in _BDAY_PATTERNS:
        m = pattern.search(text)
        if m:
            g = m.groups()
            iso = _parse_date_from_match(
                g[0] if len(g) > 0 else "",
                g[1] if len(g) > 1 else "",
                g[2] if len(g) > 2 and g[2] else "",
            )
            if iso:
                return iso
    # 2. Fallback LLM per formati liberi
    try:
        from core.llm_service import llm_service
        import json as _json
        import re as _re
        raw = await llm_service._call_model(
            "openai/gpt-4o-mini",
            ("Estrai la DATA DI NASCITA dal messaggio dell'utente. "
             "Rispondi SOLO con JSON valido: {\"day\":N|null,\"month\":N|null,\"year\":N|null}. "
             "month è il numero del mese (1-12). Se l'anno non è indicato metti year=null. "
             "Se non c'è alcuna data, metti tutti i campi a null."),
            text.strip()[:300],
            user_id="bday-parse",
            route="memory",
        )
        if raw:
            mt = _re.search(r"\{.*\}", raw, _re.S)
            if mt:
                d = _json.loads(mt.group(0))
                day, month, year = d.get("day"), d.get("month"), d.get("year")
                if day and month and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                    yy = f"{int(year):04d}" if year and 1900 <= int(year) <= date.today().year else "????"
                    return f"{yy}-{int(month):02d}-{int(day):02d}"
    except Exception as e:
        logger.warning("BDAY_FREEFORM_PARSE_ERROR err=%s", e)
    return ""


async def collect_birthday_dm(wa_id: str, name: str, text: str) -> dict:
    """
    Gestisce la risposta di un membro al DM di raccolta compleanni.
    Salva la data (sotto member_id 'wa:{wa_id}') e ritorna {found, date, reply}.
    """
    wa_clean = (wa_id or "").split("@")[0].replace("+", "")
    member_id = f"wa:{wa_clean}"
    iso = await parse_birthdate_freeform(text)
    if iso:
        existing = await get_birthday(member_id)
        try:
            from core.telegram_group_memory import _sanitize_member_name
            clean_name = _sanitize_member_name(name) or existing.get("name", "")
        except Exception:
            clean_name = name or existing.get("name", "")
        await save_birthday(member_id, iso, clean_name, "whatsapp_dm")
        log("BIRTHDAY_DM_SAVED", wa_id=wa_clean, name=name, birthdate=iso)
        try:
            parts = iso.split("-")
            quando = f"{int(parts[2])} {_MONTH_NAMES_IT[int(parts[1])]}"
            if parts[0] != "????":
                quando += f" {parts[0]}"
        except Exception:
            quando = iso
        nm = f", {name}" if name else ""
        return {"found": True, "date": iso,
                "reply": (f"Perfetto{nm}! 🎂 Ho segnato il tuo compleanno: {quando}. "
                          "Ti farò gli auguri quel giorno. Grazie!")}
    return {"found": False, "date": "",
            "reply": ("Scusa, non sono riuscita a capire la data 😅 "
                      "Scrivimela pure come preferisci, anche semplice: "
                      "\"12 marzo 1985\" oppure solo \"12 marzo\".")}


# ── Calcolo età e messaggio ───────────────────────────────────────────────────

def _calc_age(birthdate_iso: str, today: date = None) -> int | None:
    """Calcola anni compiuti oggi. None se anno sconosciuto."""
    today = today or date.today()
    if "????" in birthdate_iso:
        return None
    try:
        bd = date.fromisoformat(birthdate_iso)
        age = today.year - bd.year
        if (today.month, today.day) < (bd.month, bd.day):
            age -= 1
        return age
    except Exception:
        return None


def _is_birthday_today(birthdate_iso: str, today: date = None) -> bool:
    today = today or date.today()
    try:
        # Supporta sia YYYY-MM-DD che ????-MM-DD
        parts = birthdate_iso.replace("????", "2000").split("-")
        return int(parts[1]) == today.month and int(parts[2]) == today.day
    except Exception:
        return False


async def _generate_birthday_message(name: str, age: int | None) -> str:
    """Genera un messaggio di auguri personalizzato con LLM leggero."""
    try:
        from core.llm_service import llm_service
        age_str = f"Compie {age} anni." if age else "Non so quanti anni compie."
        prompt = (
            "Sei Genesi, l'AI di famiglia, affettuosa e calorosa. "
            "Scrivi un messaggio di buon compleanno breve (max 3 righe) per un membro della famiglia. "
            "Usa il nome, menziona gli anni se li sai, usa un tono caldo e familiare. "
            "NIENTE emoji eccessive — al massimo 1-2. Scrivi in italiano."
        )
        msg = await llm_service._call_model(
            "openai/gpt-4o-mini",
            prompt,
            f"Nome: {name}. {age_str}",
            user_id="birthday-bot",
            route="memory",
        )
        if msg and msg.strip():
            return msg.strip()
    except Exception as exc:
        logger.debug("BIRTHDAY_MSG_GEN_ERROR err=%s", exc)

    # Fallback deterministico
    age_part = f" — {age} anni!" if age else "!"
    return f"Buon compleanno, {name}{age_part} Che sia una giornata speciale per te! 🎂"


# ── Invio auguri Telegram gruppo ───────────────────────────────────────────────

async def _send_telegram_group_birthday(chat_id: int, name: str, age: int | None):
    try:
        from core.telegram_bot import send_message as tg_send
        msg = await _generate_birthday_message(name, age)
        await tg_send(chat_id, msg)
        log("BIRTHDAY_SENT_TG", chat_id=chat_id, name=name, age=age)
    except Exception as exc:
        logger.warning("BIRTHDAY_SEND_TG_ERROR chat_id=%s err=%s", chat_id, exc)


async def _send_telegram_private_birthday(chat_id: int, name: str, age: int | None):
    """Per utenti che usano Genesi in chat privata Telegram."""
    try:
        from core.telegram_bot import send_message as tg_send
        msg = await _generate_birthday_message(name, age)
        await tg_send(chat_id, msg)
        log("BIRTHDAY_SENT_TG_PRIVATE", chat_id=chat_id, name=name, age=age)
    except Exception as exc:
        logger.warning("BIRTHDAY_SEND_TG_PRIVATE_ERROR err=%s", exc)


async def _send_wa_group_birthday(name: str, age: int | None):
    """Invia auguri al gruppo WhatsApp via Baileys HTTP."""
    if not _WA_GROUP_JID:
        logger.info("BIRTHDAY_WA_GROUP_SKIP no WA_GROUP_JID configured")
        return
    try:
        import httpx
        msg = await _generate_birthday_message(name, age)
        payload = {"groupId": _WA_GROUP_JID, "text": msg}
        if _BAILEYS_SEND_SECRET:
            payload["secret"] = _BAILEYS_SEND_SECRET
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(_BAILEYS_SEND_URL, json=payload)
        if r.status_code == 200:
            log("BIRTHDAY_SENT_WA_GROUP", name=name, age=age)
        else:
            logger.warning("BIRTHDAY_SEND_WA_GROUP_HTTP err=%s body=%s", r.status_code, r.text[:100])
    except Exception as exc:
        logger.warning("BIRTHDAY_SEND_WA_GROUP_ERROR err=%s", exc)


async def _send_wa_private_birthday(wa_id: str, name: str, age: int | None):
    """Per utenti che usano Genesi in WhatsApp 1:1 (Cloud API)."""
    try:
        from core.whatsapp_bot import send_message as wa_send
        msg = await _generate_birthday_message(name, age)
        await wa_send(wa_id, msg)
        log("BIRTHDAY_SENT_WA_PRIVATE", wa_id=wa_id, name=name, age=age)
    except Exception as exc:
        logger.warning("BIRTHDAY_SEND_WA_PRIVATE_ERROR err=%s", exc)


# ── Check giornaliero: scopre chi compie gli anni oggi ────────────────────────

async def check_and_send_birthdays():
    """
    Logica principale del birthday checker.
    1. Scansiona tutti i birthday: in storage
    2. Per ogni membro il cui compleanno è oggi e non ha già ricevuto gli auguri:
       - Genera messaggio LLM
       - Invia al gruppo Telegram appropriato (se membro del gruppo)
       - Invia in privato Telegram/WA (se utente con chat_id privato)
    3. Segna come "auguri inviati" per quest'anno
    """
    tz = ZoneInfo("Europe/Rome")
    today = datetime.now(tz).date()
    year  = today.year


    # Carica set auguri già inviati quest'anno
    sent_key  = _sent_today_key(year)
    sent_data = await storage.load(sent_key, default={}) or {}

    # Carica gruppi noti
    known_groups = await get_known_groups()
    tg_group_ids = [g["chat_id"] for g in known_groups if g["platform"] == "telegram"]

    # Scansiona tutti i birthday:* in storage
    # Usiamo la lista dei pre-seed + chiunque abbia inviato messaggi
    member_ids_to_check: set[str] = set()

    # 1. Pre-seed Telegram (by name — prima del link a from_id)
    for name_lower in _PRESEED_TELEGRAM:
        _, display = _PRESEED_TELEGRAM[name_lower]
        # Cerca se esiste un from_id collegato (sarà stato salvato da link_preseed_to_member)
        # Altrimenti usiamo la chiave temporanea "tg:name:{name_lower}"
        member_ids_to_check.add(f"tg:name:{name_lower}")

    # 2. Tutti i birthday:tg:* e birthday:wa:* in storage
    # (storage JSON-file: accediamo alla chiave diretta)
    try:
        for _mid in _all_birthday_member_ids():
            member_ids_to_check.add(_mid)
    except Exception:
        pass

    for member_id in member_ids_to_check:
        try:
            # Gestisci "tg:name:{name_lower}" — pseudo-id per pre-seed non ancora collegati
            if member_id.startswith("tg:name:"):
                name_lower = member_id[len("tg:name:"):]
                if name_lower not in _PRESEED_TELEGRAM:
                    continue
                birthdate, display_name = _PRESEED_TELEGRAM[name_lower]
                # Cerca se esiste un from_id reale
                real_id = None
                try:
                    for _mid in _all_birthday_member_ids():
                        if _mid.startswith("tg:") and not _mid.startswith("tg:name:"):
                            d = await get_birthday(_mid)
                            if isinstance(d, dict) and d.get("name", "").lower() == name_lower:
                                real_id = _mid
                                break
                except Exception:
                    pass
                effective_id = real_id or member_id
            else:
                data = await get_birthday(member_id)
                if not data:
                    continue
                birthdate    = data.get("birthdate", "")
                display_name = data.get("name", member_id)
                effective_id = member_id

            if not birthdate:
                continue
            if not _is_birthday_today(birthdate, today):
                continue
            if sent_data.get(effective_id):
                continue  # auguri già inviati quest'anno

            age = _calc_age(birthdate, today)

            # Determina dove inviare
            if member_id.startswith("tg:") or member_id.startswith("tg:name:"):
                # Invia a tutti i gruppi Telegram noti (solo famiglia)
                for gid in tg_group_ids:
                    if gid < 0:
                        await _send_telegram_group_birthday(gid, display_name, age)
                # Invia anche al gruppo WhatsApp (stessa famiglia)
                await _send_wa_group_birthday(display_name, age)
                # Se ha anche una chat privata (chat_id salvato nel membro Telegram)
                try:
                    if member_id.startswith("tg:") and not member_id.startswith("tg:name:"):
                        from_id_int = int(member_id[3:])
                        from core.telegram_group_memory import get_member
                        mem = await get_member(from_id_int)
                        priv_chat_id = mem.get("private_chat_id")
                        if priv_chat_id:
                            await _send_telegram_private_birthday(priv_chat_id, display_name, age)
                except Exception:
                    pass

            elif member_id.startswith("wa:"):
                wa_id = member_id[3:]
                await _send_wa_private_birthday(wa_id, display_name, age)

            else:
                # Web app user — registra nel chat_memory per injection al prossimo accesso
                try:
                    from core.chat_memory import chat_memory
                    msg = await _generate_birthday_message(display_name, age)
                    chat_memory.add_message(
                        user_id=member_id,
                        message="",
                        response=msg,
                        intent="birthday_greeting",
                    )
                    log("BIRTHDAY_QUEUED_WEBAPP", user_id=member_id, name=display_name, age=age)
                except Exception:
                    pass

            # Segna auguri inviati
            sent_data[effective_id] = today.isoformat()
            await storage.save(sent_key, sent_data)

        except Exception as exc:
            logger.warning("BIRTHDAY_CHECK_ERROR member_id=%s err=%s", member_id, exc)


# ── Generatore Messaggio Proattivo LLM ─────────────────────────────────────────

_WEATHER_CACHE: dict[str, tuple[float, str]] = {}  # city_lower -> (ts, summary)
_WEATHER_TTL = 1800  # 30 min: il meteo non cambia a vista, evita chiamate ripetute


async def _get_quick_weather_summary(city_name: str) -> str:
    """Ritorna una sintesi meteo super concisa (es. 'Imola: Cielo sereno, 23°C') per lo scheduler proattivo."""
    import httpx
    import os
    OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
    if not OPENWEATHER_API_KEY:
        return ""
    # Cache: stessa città entro 30 min → niente seconda chiamata a OpenWeather
    _ck = (city_name or "").strip().lower()
    _now = time.time()
    _hit = _WEATHER_CACHE.get(_ck)
    if _hit and _now - _hit[0] < _WEATHER_TTL:
        return _hit[1]
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # 1. Geocoding
            geo_url = "https://api.openweathermap.org/geo/1.0/direct"
            q_query = f"{city_name},IT"
            geo_params = {"q": q_query, "limit": 3, "appid": OPENWEATHER_API_KEY}
            geo_resp = await client.get(geo_url, params=geo_params)
            if geo_resp.status_code != 200:
                return ""
            geo_data = geo_resp.json()
            if not geo_data:
                geo_params["q"] = city_name
                geo_resp = await client.get(geo_url, params=geo_params)
                if geo_resp.status_code != 200 or not geo_resp.json():
                    return ""
                geo_data = geo_resp.json()
            
            geo = geo_data[0]
            lat, lon = geo["lat"], geo["lon"]
            
            # 2. Weather
            weather_url = "https://api.openweathermap.org/data/2.5/weather"
            weather_params = {
                "lat": lat,
                "lon": lon,
                "appid": OPENWEATHER_API_KEY,
                "units": "metric",
                "lang": "it"
            }
            w_resp = await client.get(weather_url, params=weather_params)
            if w_resp.status_code != 200:
                return ""
            
            w_data = w_resp.json()
            temp = round(w_data.get("main", {}).get("temp", 0))
            desc = w_data.get("weather", [{}])[0].get("description", "").lower()
            _summary = f"{city_name}: {desc}, {temp}°C"
            _WEATHER_CACHE[_ck] = (_now, _summary)
            return _summary
    except Exception as e:
        logger.warning("PROACTIVE_GREETING_WEATHER_ERROR city=%s err=%s", city_name, e)
        return ""


async def _generate_proactive_greeting(birthdays: list, event_type: str, today_date: date, chat_id: int = 0, platform: str = "telegram") -> str:
    """Genera un messaggio di saluto proattivo mattutino coerente con LLM, su misura per lo specifico gruppo."""
    try:
        from core.llm_service import llm_service
        
        giorni_settimana = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
        giorno_nome = giorni_settimana[today_date.weekday()]
        
        # Recupera il nome del gruppo da storage
        group_title = await storage.load(f"group_title:{chat_id}", default="Casa Turrisi" if platform == "telegram" else "The Family")
        
        if chat_id == -1001267666655:
            system_prompt = (
                "Sei Genesi, l'AI assistente del gruppo di sviluppatori Swift e app Apple.\n"
                f"Ogni mattina invii un saluto spontaneo nel gruppo '{group_title}'.\n"
                "REGOLE CRITICHE DI STILE E CONCISIONE:\n"
                "- Scrivi un saluto brevissimo di MASSIMO 2 RIGHE.\n"
                "- Mantenere un tono professionale ma informale, NON familiare. Assolutamente niente baci o affetto smodato.\n"
                "- Integra nel saluto un rapidissimo cenno al tempo attuale nelle città degli sviluppatori presenti nel gruppo, basandoti sui dati forniti.\n"
                "- Se oggi ci sono compleanni nel gruppo, fai gli auguri."
            )
        elif chat_id in (-5007188402, -318483633) or platform == "whatsapp":
            system_prompt = (
                "Sei Genesi, il GUARDIANO EMOTIVO della famiglia. Vegli con affetto, calore e attenzione sui membri della famiglia.\n"
                f"Ogni mattina sei la prima a inviare un saluto spontaneo nel gruppo familiare '{group_title}'.\n"
                "REGOLE CRITICHE DI STILE E CONCISIONE:\n"
                "- Scrivi un saluto brevissimo di MASSIMO 2 RIGHE (1 o 2 frasi in tutto). Sii estremamente concisa, asciutta e affettuosa.\n"
                "- EVITA ASSOLUTAMENTE toni teatrali, enfatici, retorici o frasi fatte da intelligenza artificiale.\n"
                "- Il tono deve essere GENUINO, informale e terra-terra, esattamente come scriverebbe un membro vero della famiglia sulla chat di gruppo.\n"
                "- Integra nel saluto un rapidissimo e naturale cenno scherzoso al tempo attuale nelle città dei partecipanti di QUESTO specifico gruppo, descritte nel contesto.\n"
                "- Se oggi ci sono compleanni di membri della famiglia, fai gli auguri per prima con calore e semplicità."
            )
        else:
            system_prompt = (
                "Sei Genesi, un'intelligenza artificiale socievole e utile.\n"
                f"Ogni mattina invii un breve saluto nel gruppo '{group_title}'.\n"
                "REGOLE CRITICHE DI STILE E CONCISIONE:\n"
                "- Scrivi un saluto di MASSIMO 2 RIGHE.\n"
                "- Usa un tono amichevole, educato e cordiale.\n"
                "- Integra un rapido cenno al tempo attuale nelle città dei partecipanti, basandoti sui dati forniti.\n"
                "- Se oggi ci sono compleanni, fai gli auguri."
            )
        
        context_parts = [f"Giorno: {giorno_nome}, Data: {today_date.strftime('%d/%m/%Y')}."]
        
        # Recupera il meteo in tempo reale per i partecipanti di questo specifico gruppo
        locations = await get_group_members_locations(chat_id)
        weather_cities = list(set(locations.values()))
        if not weather_cities:
            weather_cities = ["Imola"] if platform == "whatsapp" else ["Motta Sant'Anastasia", "Bracciano", "Lentini", "Imola", "Franchetto"]
            
        weather_tasks = [_get_quick_weather_summary(c) for c in weather_cities]
        weather_results = await asyncio.gather(*weather_tasks, return_exceptions=True)
        weather_summaries = [r for r in weather_results if isinstance(r, str) and r]
        
        if weather_summaries:
            context_parts.append("METEO ATTUALE NELLE CITTÀ DEI PARTECIPANTI DI QUESTO GRUPPO:")
            for name, city in locations.items():
                context_parts.append(f"- {name}: {city}")
            context_parts.append("Dati OpenWeather:")
            for summary in weather_summaries:
                context_parts.append(f"  {summary}")
        
        hol = get_italian_holiday(today_date)
        if hol:
            context_parts.append(f"Festività Nazionale in Italia: {hol}.")
            
        locations = await get_group_members_locations(0)
        local_hols = []
        for name, city in locations.items():
            loc_hol = get_local_holiday(today_date, city)
            if loc_hol:
                local_hols.append(f"{name} a {city.capitalize()} festeggia {loc_hol}")
        if local_hols:
            context_parts.append("Festività locali dei membri: " + "; ".join(local_hols) + ".")
            
        if event_type == "birthday":
            bday_infos = []
            for name, age in birthdays:
                if name in locations or name == "Alfio":
                    age_info = f"compie {age} anni" if age else "compie gli anni"
                    bday_infos.append(f"{name} ({age_info})")
            if bday_infos:
                context_parts.append("COMPLEANNI OGGI DA FESTEGGIARE: " + ", ".join(bday_infos) + ". FAI GLI AUGURI PER PRIMA!")
            else:
                event_type = "weekend_holiday_greeting" if today_date.weekday() in (5, 6) or get_italian_holiday(today_date) else "weekday_greeting"
        
        if event_type == "weekend_holiday_greeting":
            context_parts.append("Tipo evento: Saluto proattivo del Weekend o Festivo. Augura una buona giornata rilassante o di festa!")
        elif event_type != "birthday":
            context_parts.append("Tipo evento: Saluto proattivo feriale (giorno di lavoro/scuola). Incoraggia la famiglia con affetto!")
            
        user_msg = "\n".join(context_parts)
        
        msg = await llm_service._call_model(
            "openai/gpt-4o-mini",
            system_prompt,
            user_msg,
            user_id="proactive-greeting-bot",
            route="memory",
        )
        if msg and msg.strip():
            return msg.strip()
    except Exception as exc:
        logger.warning("PROACTIVE_MSG_GEN_ERROR err=%s", exc)
        
    # Fallbacks deterministici caldi
    is_fam = (chat_id in (-5007188402, -318483633) or platform == "whatsapp")
    if event_type == "birthday":
        names = ", ".join(n for n, _ in birthdays)
        if is_fam:
            return f"Buon compleanno a {names}! 🎂 Che sia una giornata meravigliosa e speciale per voi, vi voglio bene! ❤️"
        return f"Buon compleanno a {names}! 🎂 Che sia una splendida giornata!"
    elif event_type == "weekend_holiday_greeting":
        hol = get_italian_holiday(today_date)
        if hol:
            if is_fam:
                return f"Buona festa a tutti! Oggi è {hol} 🌸 Godetevi questa giornata speciale, vi abbraccio forte! ❤️"
            return f"Buona festa a tutti! Oggi è {hol} 🌸 Godetevi questa giornata!"
        if is_fam:
            return "Buongiorno e buon fine settimana a tutti! 😘 Riposatevi e passate una splendida giornata in famiglia! ❤️"
        return "Buongiorno e buon fine settimana a tutti! Riposatevi e passate una splendida giornata!"
    else:
        if is_fam:
            return "Buongiorno a tutti! 😘 Inizia una nuova giornata feriale, vi auguro buon lavoro e buona scuola. Forza! ❤️"
        return "Buongiorno a tutti! Inizia una nuova giornata, buon lavoro e buona giornata a tutti!"


async def _generate_morning_image(greeting_text: str, chat_id: int, platform: str = "whatsapp") -> str:
    """
    Genera un'immagine mattutina coerente con il testo del saluto e con il meteo
    reale del posto. Ritorna l'URL pubblico (static/ig_posts) o "" se non riuscita.
    """
    try:
        # 1. Meteo reale del gruppo (stesse fonti del saluto)
        locations = await get_group_members_locations(chat_id)
        cities = list(set(locations.values())) or ["Imola"]
        wres = await asyncio.gather(
            *[_get_quick_weather_summary(c) for c in cities], return_exceptions=True
        )
        weather = "; ".join(r for r in wres if isinstance(r, str) and r) or "cielo sereno"

        # 2. Prompt immagine coerente con saluto + meteo (LLM, con fallback)
        from core.llm_service import llm_service
        img_prompt = await llm_service._call_model(
            "openai/gpt-4o-mini",
            "Sei un art director. Produci SOLO un prompt in inglese per un generatore di "
            "immagini, senza spiegazioni né virgolette.",
            ("Crea il prompt per un'illustrazione/foto calda e accogliente da 'buongiorno', "
             "UNA sola scena, coerente con questo saluto e con il meteo reale.\n"
             f"Saluto: \"{greeting_text}\"\n"
             f"Meteo reale ora: {weather}\n"
             "Rispecchia fedelmente le condizioni meteo (sole/nuvole/pioggia, luce, stagione). "
             "Nessun testo nell'immagine, nessun volto riconoscibile. Massimo 60 parole."),
            user_id="morning-image",
            route="memory",
        )
        if not img_prompt or not img_prompt.strip():
            img_prompt = (
                f"A warm, cozy good-morning illustration that reflects the real weather "
                f"({weather}). Soft natural morning light, inviting family atmosphere, "
                "no text, no recognizable faces."
            )

        # 3. Genera e salva → URL pubblico (riusa la pipeline immagini di Instagram)
        from core.instagram_publisher import _create_image
        url = await _create_image(img_prompt.strip())
        if url:
            log("MORNING_IMAGE_OK", chat_id=chat_id, weather=weather[:60])
        else:
            log("MORNING_IMAGE_FAIL", chat_id=chat_id)
        return url or ""
    except Exception as e:
        logger.warning("MORNING_IMAGE_ERROR chat_id=%s err=%s", chat_id, e)
        return ""


# ── Scheduler loop ─────────────────────────────────────────────────────────────

async def birthday_scheduler():
    """
    Background loop: gestisce l'invio proattivo mattutino (compleanni alle 6:30,
    giorni feriali alle 6:45, weekend/festivi alle 8:45) e le notifiche private.
    """
    log("BIRTHDAY_SCHEDULER_STARTED")

    # Pre-carica dati pre-seed in storage (run once all'avvio)
    await _ensure_preseed_loaded()

    while True:
        try:
            now = datetime.now(_TZ)
            today_str = now.date().isoformat()
            today_date = now.date()
            
            # Verifichiamo se ci sono compleanni oggi
            birthdays_today = []
            member_ids_to_check = set()
            for name_lower in _PRESEED_TELEGRAM:
                member_ids_to_check.add(f"tg:name:{name_lower}")
            try:
                for _mid in _all_birthday_member_ids():
                    member_ids_to_check.add(_mid)
            except Exception:
                pass
                
            for member_id in member_ids_to_check:
                try:
                    if member_id.startswith("tg:name:"):
                        name_lower = member_id[len("tg:name:"):]
                        if name_lower not in _PRESEED_TELEGRAM:
                            continue
                        birthdate, display_name = _PRESEED_TELEGRAM[name_lower]
                    else:
                        data = await get_birthday(member_id)
                        if not data:
                            continue
                        birthdate = data.get("birthdate", "")
                        display_name = data.get("name", member_id)
                    
                    if birthdate and _is_birthday_today(birthdate, today_date):
                        age = _calc_age(birthdate, today_date)
                        birthdays_today.append((display_name, age, member_id))
                except Exception:
                    pass
            
            # Determiniamo gli orari target per oggi
            has_birthday = len(birthdays_today) > 0
            is_holiday = get_italian_holiday(today_date) is not None
            is_weekend = today_date.weekday() in (5, 6)
            
            if has_birthday:
                target_hour = 6
                target_minute = 30
                event_type = "birthday"
            elif is_weekend or is_holiday:
                target_hour = 8
                target_minute = 45
                event_type = "weekend_holiday_greeting"
            else:
                target_hour = 6
                target_minute = 45
                event_type = "weekday_greeting"
                
            # Verifica se siamo nello slot temporale di oggi per l'invio proattivo del gruppo
            target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            target_end = target_time.replace(minute=target_minute + 10)
            
            if target_time <= now <= target_end:
                # Controlliamo se abbiamo già inviato il saluto proattivo oggi
                sent_key = f"greetings:sent:{today_str}"
                already_sent = await storage.load(sent_key, default=False)
                
                if not already_sent:
                    logger.info("PROACTIVE_SCHEDULER: Triggering proactive event %s at %s", event_type, now)
                    
                    # Carica gruppi noti
                    known_groups = await get_known_groups()
                    tg_group_ids = [g["chat_id"] for g in known_groups if g["platform"] == "telegram"]
                    
                    # Generiamo ed inviamo messaggi differenziati per ciascun gruppo
                    known_groups = await get_known_groups()
                    now_ts = time.time()
                    
                    # Invia a Telegram
                    from core.telegram_bot import send_message as tg_send
                    for g in known_groups:
                        if g.get("platform") == "telegram":
                            gid = g["chat_id"]
                            if gid >= 0:
                                continue
                            msg = await _generate_proactive_greeting(
                                [(n, a) for n, a, _ in birthdays_today],
                                event_type,
                                today_date,
                                chat_id=gid,
                                platform="telegram"
                            )
                            if msg:
                                await tg_send(gid, msg)
                                # Registra il timestamp del saluto proattivo per il gap globale di 1 ora
                                tg_global_key = f"relational_state:last_group_greeting_ts_{gid}"
                                await storage.save(tg_global_key, now_ts)
                                
                    # Invia a TUTTI i gruppi WhatsApp noti (non più solo _WA_GROUP_JID).
                    # Il registry tiene il chat_id hashato; il JID originale è salvato in
                    # "wa_group_jid:{chat_id}" al passaggio dei messaggi di gruppo.
                    import httpx
                    from core.telegram_group_memory import stable_hash
                    wa_targets = {}  # {jid: chat_id}
                    for g in known_groups:
                        if g.get("platform") != "whatsapp":
                            continue
                        cid = g["chat_id"]
                        jid = await storage.load(f"wa_group_jid:{cid}", default="")
                        if not jid:
                            # Backward-compat: il gruppo storico hardcoded
                            if _WA_GROUP_JID and stable_hash(_WA_GROUP_JID) == cid:
                                jid = _WA_GROUP_JID
                            else:
                                continue  # JID non ancora noto: si salverà al primo messaggio
                        wa_targets[jid] = cid
                    # Assicura comunque la presenza del gruppo storico
                    if _WA_GROUP_JID and _WA_GROUP_JID not in wa_targets:
                        wa_targets[_WA_GROUP_JID] = stable_hash(_WA_GROUP_JID)

                    for jid, cid in wa_targets.items():
                        msg = await _generate_proactive_greeting(
                            [(n, a) for n, a, _ in birthdays_today],
                            event_type,
                            today_date,
                            chat_id=cid,
                            platform="whatsapp"
                        )
                        if not msg:
                            continue
                        payload = {"groupId": jid, "text": msg}
                        # Solo per il gruppo configurato: immagine mattutina generata,
                        # coerente con il saluto e col meteo del posto, inviata come caption.
                        if jid == _WA_MORNING_IMAGE_JID:
                            _img_url = await _generate_morning_image(msg, cid, "whatsapp")
                            if _img_url:
                                payload = {"groupId": jid, "imageUrl": _img_url, "caption": msg}
                        if _BAILEYS_SEND_SECRET:
                            payload["secret"] = _BAILEYS_SEND_SECRET
                        try:
                            async with httpx.AsyncClient(timeout=10) as client:
                                _wa_res = await client.post(_BAILEYS_SEND_URL, json=payload)
                                # Logga SEMPRE l'esito: un "forbidden" silenzioso
                                # ha nascosto per giorni il saluto WA mai recapitato
                                if _wa_res.status_code == 200:
                                    log("PROACTIVE_GREETING_WA_OK", jid=jid)
                                else:
                                    log("PROACTIVE_GREETING_WA_FAIL", jid=jid,
                                        status=_wa_res.status_code, body=_wa_res.text[:120])
                        except Exception as _wae:
                            log("PROACTIVE_GREETING_WA_FAIL", jid=jid, status=0, body=str(_wae)[:120])
                        # Registra il timestamp del saluto proattivo per il gap globale di 1 ora
                        await storage.save(f"relational_state:last_group_greeting_ts_{cid}", now_ts)
                            
                    # Segna come inviato per oggi
                    await storage.save(sent_key, True)
                    log("PROACTIVE_GREETING_SENT", type=event_type, date=today_str)
                    
                    # Per i compleanni: segna anche l'avvenuto invio individuale degli auguri
                    if has_birthday:
                        year = today_date.year
                        sent_today_k = _sent_today_key(year)
                        sent_data = await storage.load(sent_today_k, default={}) or {}
                        for _, _, mid in birthdays_today:
                            sent_data[mid] = today_str
                        await storage.save(sent_today_k, sent_data)

            # Gestiamo anche le notifiche private e webapp individuali (compleanni)
            p_target = now.replace(hour=6, minute=30, second=0, microsecond=0)
            p_target_end = p_target.replace(minute=p_target.minute + 10)
            if p_target <= now <= p_target_end:
                # Chiama check_and_send_birthdays per processare notifiche private e webapp
                await check_and_send_birthdays()

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("BIRTHDAY_SCHEDULER_LOOP_ERROR err=%s", exc)
            
        await asyncio.sleep(30)



async def _ensure_preseed_loaded():
    """
    Al primo avvio: salva i dati pre-seed in storage (solo se non già presenti).
    """
    for name_lower, (birthdate, display) in _PRESEED_TELEGRAM.items():
        # Chiave temporanea per nomi non ancora collegati a from_id
        pseudo_id = f"tg:name:{name_lower}"
        existing = await get_birthday(pseudo_id)
        if not existing.get("birthdate"):
            await save_birthday(pseudo_id, birthdate, display, "telegram_group")
    log("BIRTHDAY_PRESEED_LOADED", count=len(_PRESEED_TELEGRAM))
