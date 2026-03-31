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

logger = logging.getLogger(__name__)
_TZ = ZoneInfo("Europe/Rome")

# ── Chiavi storage ─────────────────────────────────────────────────────────────

def _bday_key(member_id: str) -> str:
    """Chiave universale: può essere user_id webapp, 'tg:{from_id}', 'wa:{wa_id}'."""
    return f"birthday:{member_id}"

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


async def register_known_group(chat_id: int, platform: str = "telegram"):
    """Registra un gruppo attivo (chiamato al primo messaggio ricevuto)."""
    known = await storage.load(_known_groups_key(), default=[]) or []
    entry = {"chat_id": chat_id, "platform": platform}
    if entry not in known:
        known.append(entry)
        await storage.save(_known_groups_key(), known)


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
    today = date.today()
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
        all_keys = [k for k in storage._storage.keys() if k.startswith("birthday:")]
        for k in all_keys:
            mid = k[len("birthday:"):]
            if mid not in ("known_groups",) and not mid.startswith("sent:"):
                member_ids_to_check.add(mid)
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
                    for k in storage._storage.keys():
                        if k.startswith("birthday:tg:") and not k.startswith("birthday:tg:name:"):
                            d = storage._storage[k]
                            if isinstance(d, dict) and d.get("name", "").lower() == name_lower:
                                real_id = k[len("birthday:"):]
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
                # Invia a tutti i gruppi Telegram noti
                for gid in tg_group_ids:
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


# ── Scheduler loop ─────────────────────────────────────────────────────────────

async def birthday_scheduler():
    """
    Background loop: aspetta le 06:00 (Europe/Rome) di ogni giorno
    e invia gli auguri a chi compie gli anni.
    """
    log("BIRTHDAY_SCHEDULER_STARTED")

    # Pre-carica dati pre-seed in storage (run once all'avvio)
    await _ensure_preseed_loaded()

    while True:
        try:
            now    = datetime.now(_TZ)
            target = now.replace(hour=6, minute=0, second=0, microsecond=0)
            if now >= target:
                # Già passate le 6:00 di oggi — aspetta le 6:00 di domani
                from datetime import timedelta
                target += timedelta(days=1)

            wait_secs = (target - now).total_seconds()
            logger.info("BIRTHDAY_SCHEDULER next_check_in=%.0fs", wait_secs)
            await asyncio.sleep(wait_secs)

            await check_and_send_birthdays()

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("BIRTHDAY_SCHEDULER_ERROR err=%s", exc)
            await asyncio.sleep(3600)  # riprova tra 1h se errore


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
