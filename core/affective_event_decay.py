"""
Affective Event Decay - gestione globale dello stato emotivo attivo.

Le memorie delicate restano disponibili come fatto storico, ma la loro forza
come istruzione di tono decade nel tempo salvo nuovi segnali contestuali.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable, Mapping, Optional

ACUTE_SUPPORT_DAYS = 3
GENTLE_AWARENESS_DAYS = 10
INACTIVE_UNLESS_REFERENCED_DAYS = 45

ACUTE_SUPPORT = "acute_support"
GENTLE_AWARENESS = "gentle_awareness"
BACKGROUND_MEMORY = "background_memory"
INACTIVE_UNLESS_REFERENCED = "inactive_unless_referenced"

_SENSITIVE_PATTERNS = (
    r"\blutto\b",
    r"\bcondoglianz",
    r"\bfuneral",
    r"\bdecedut",
    r"\bscompars",
    r"\bmort[oaie]?\b",
    r"\bperdit[aoe]\b",
    r"\bmancat[oaie]\b",
    r"\bci ha lasciat",
    r"\briposa in pace\b",
    r"\bmalatti",
    r"\bospedal",
    r"\bricover",
    r"\bincident",
    r"\boperat",
    r"\bcrisi\b",
    r"\bstress\b",
    r"\bansia\b",
    r"\bpanico\b",
    r"\bseparat",
    r"\bdivorzi",
    r"\blicenziat",
)
_SENSITIVE_RE = re.compile("|".join(_SENSITIVE_PATTERNS), re.IGNORECASE)

_CATEGORY_PATTERNS = {
    "loss": (
        r"\blutto\b", r"\bcondoglianz", r"\bfuneral", r"\bdecedut",
        r"\bscompars", r"\bmort[oaie]?\b", r"\bperdit[aoe]\b",
        r"\bmancat[oaie]\b", r"\bci ha lasciat", r"\briposa in pace\b",
    ),
    "health": (
        r"\bmalatti", r"\bospedal", r"\bricover", r"\bincident", r"\boperat",
    ),
    "distress": (
        r"\bcrisi\b", r"\bstress\b", r"\bansia\b", r"\bpanico\b",
    ),
    "relationship": (
        r"\bseparat", r"\bdivorzi",
    ),
    "work": (
        r"\blicenziat",
    ),
}
_CATEGORY_RES = {
    category: re.compile("|".join(patterns), re.IGNORECASE)
    for category, patterns in _CATEGORY_PATTERNS.items()
}


def is_sensitive_affective_text(text: str) -> bool:
    """True se il testo contiene un evento emotivo delicato generale."""
    return bool(text and _SENSITIVE_RE.search(text))


def sensitive_categories(text: str) -> set[str]:
    """Categorie affettive rilevate nel testo, per riattivazioni meno generiche."""
    if not text:
        return set()
    return {
        category
        for category, pattern in _CATEGORY_RES.items()
        if pattern.search(text)
    }


def parse_event_time(value) -> Optional[datetime]:
    """Accetta timestamp epoch o ISO e restituisce una datetime UTC naive-safe."""
    if value is None:
        return None
    try:
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            if text.isdigit():
                return datetime.fromtimestamp(float(text), tz=timezone.utc)
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    return None


def affective_decay_stage(event_time, now: Optional[datetime] = None) -> str:
    """Calcola lo stage di decay a partire dal timestamp dell'ultimo riferimento reale."""
    event_dt = parse_event_time(event_time)
    if not event_dt:
        return BACKGROUND_MEMORY
    current = now or datetime.now(timezone.utc)
    if event_dt.tzinfo is None:
        event_dt = event_dt.replace(tzinfo=timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (current - event_dt).total_seconds() / 86400)
    if age_days <= ACUTE_SUPPORT_DAYS:
        return ACUTE_SUPPORT
    if age_days <= GENTLE_AWARENESS_DAYS:
        return GENTLE_AWARENESS
    if age_days <= INACTIVE_UNLESS_REFERENCED_DAYS:
        return BACKGROUND_MEMORY
    return INACTIVE_UNLESS_REFERENCED


def current_message_reactivates(message: str, event_text: str = "") -> bool:
    """Riattiva solo se il messaggio corrente cita un tema compatibile."""
    current = sensitive_categories(message)
    if not current:
        return False
    if not event_text:
        return True
    historical = sensitive_categories(event_text)
    return bool(current & historical)


def classify_affective_event(
    text: str,
    event_time=None,
    *,
    current_message: str = "",
    now: Optional[datetime] = None,
) -> Optional[dict]:
    """Restituisce metadati di decay per un testo sensibile, oppure None."""
    if not is_sensitive_affective_text(text):
        return None
    reactivated = current_message_reactivates(current_message, text)
    stage = ACUTE_SUPPORT if reactivated else affective_decay_stage(event_time, now=now)
    active = stage in (ACUTE_SUPPORT, GENTLE_AWARENESS)
    return {
        "stage": stage,
        "active_support": active,
        "reactivated": reactivated,
    }


def latest_sensitive_reference(
    records: Iterable[Mapping],
    *,
    text_key: str = "text",
    ts_key: str = "ts",
) -> Optional[Mapping]:
    """Trova il riferimento sensibile piu recente in una lista di record."""
    latest = None
    latest_dt = None
    for record in records or []:
        text = str(record.get(text_key) or "")
        if not is_sensitive_affective_text(text):
            continue
        dt = parse_event_time(record.get(ts_key))
        if latest is None or (dt and (latest_dt is None or dt > latest_dt)):
            latest = record
            latest_dt = dt
    return latest
