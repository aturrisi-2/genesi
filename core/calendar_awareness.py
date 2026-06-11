"""
calendar_awareness.py — Contesto calendario italiano per Genesi.

Fornisce: festività nazionali, ricorrenze culturali, logica first-of-day.
Standalone, zero dipendenze da altri moduli Genesi.
"""

from __future__ import annotations
from datetime import datetime, date
from typing import Optional, Tuple
import pytz


# ---------------------------------------------------------------------------
# Festività e ricorrenze italiane (MM-DD → (nome, tipo))
# tipo: "festivo" = giorno non lavorativo ufficiale
#       "ricorrenza" = momento culturale/sentimentale, non festivo ufficiale
# ---------------------------------------------------------------------------
_FIXED_DAYS: dict[str, Tuple[str, str]] = {
    "01-01": ("Capodanno", "festivo"),
    "01-06": ("Epifania", "festivo"),
    "02-14": ("San Valentino", "ricorrenza"),
    "03-08": ("Festa della donna", "ricorrenza"),
    "04-25": ("Festa della Liberazione", "festivo"),
    "05-01": ("Festa del Lavoro", "festivo"),
    "05-04": ("Star Wars Day", "ricorrenza"),
    "06-02": ("Festa della Repubblica", "festivo"),
    "06-21": ("Solstizio d'estate", "ricorrenza"),
    "08-15": ("Ferragosto", "festivo"),
    "10-31": ("Halloween", "ricorrenza"),
    "11-01": ("Ognissanti", "festivo"),
    "11-11": ("San Martino", "ricorrenza"),
    "12-08": ("Immacolata Concezione", "festivo"),
    "12-24": ("Vigilia di Natale", "ricorrenza"),
    "12-25": ("Natale", "festivo"),
    "12-26": ("Santo Stefano", "festivo"),
    "12-31": ("San Silvestro", "ricorrenza"),
}

_GIORNI_IT = [
    "Lunedì", "Martedì", "Mercoledì", "Giovedì",
    "Venerdì", "Sabato", "Domenica",
]

_MESI_IT = [
    "", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]

_STAGIONI = {
    (3, 4, 5): "primavera",
    (6, 7, 8): "estate",
    (9, 10, 11): "autunno",
    (12, 1, 2): "inverno",
}


def _pasqua(year: int) -> date:
    """Algoritmo di Gauss per calcolare la Pasqua cattolica."""
    a = year % 19
    b = year % 4
    c = year % 7
    k = year // 100
    p = (13 + 8 * k) // 25
    q = k // 4
    m = (15 - p + k - q) % 30
    n = (4 + k - q) % 7
    d = (19 * a + m) % 30
    e = (2 * b + 4 * c + 6 * d + n) % 7
    if d == 29 and e == 6:
        return date(year, 4, 19)
    if d == 28 and e == 6 and a > 10:
        return date(year, 4, 18)
    day = 22 + d + e
    if day > 31:
        return date(year, 4, day - 31)
    return date(year, 3, day)


def _get_mobile_days(year: int) -> dict[str, Tuple[str, str]]:
    """Festività mobili: Pasqua e Lunedì dell'Angelo."""
    pasqua = _pasqua(year)
    from datetime import timedelta
    lunedi_angelo = pasqua + timedelta(days=1)
    return {
        pasqua.strftime("%m-%d"): ("Pasqua", "festivo"),
        lunedi_angelo.strftime("%m-%d"): ("Pasquetta", "festivo"),
    }


def _get_stagione(month: int) -> str:
    for months, name in _STAGIONI.items():
        if month in months:
            return name
    return ""


def _get_prossimo_festivo(today: date, year: int) -> Optional[Tuple[str, str, int]]:
    """
    Ritorna (nome, data_iso, giorni_mancanti) del prossimo festivo/ricorrenza
    nei prossimi 30 giorni. None se nessuno.
    """
    from datetime import timedelta
    all_days = {**_FIXED_DAYS, **_get_mobile_days(year)}

    for delta in range(1, 31):
        candidate = today + timedelta(days=delta)
        key = candidate.strftime("%m-%d")
        if key in all_days:
            nome, _ = all_days[key]
            return (nome, candidate.isoformat(), delta)
    return None


# ---------------------------------------------------------------------------
# API pubblica
# ---------------------------------------------------------------------------

def get_calendar_context(tz: str = "Europe/Rome") -> dict:
    """
    Ritorna il contesto calendario completo per la data/ora corrente nel fuso indicato.

    Returns:
        {
          giorno_it, data_it, is_weekend, is_lunedi, is_venerdi,
          festivo, prossimo_festivo, stagione, mese_it, ora_it
        }
    """
    try:
        tz_obj = pytz.timezone(tz)
    except Exception:
        tz_obj = pytz.timezone("Europe/Rome")

    now = datetime.now(tz_obj)
    today = now.date()
    key = today.strftime("%m-%d")

    all_days = {**_FIXED_DAYS, **_get_mobile_days(today.year)}
    festivo = all_days.get(key)  # (nome, tipo) or None

    prossimo = _get_prossimo_festivo(today, today.year)

    return {
        "giorno_it": _GIORNI_IT[now.weekday()],
        "data_it": f"{today.day} {_MESI_IT[today.month]} {today.year}",
        "is_weekend": now.weekday() >= 5,
        "is_lunedi": now.weekday() == 0,
        "is_venerdi": now.weekday() == 4,
        "festivo": festivo,            # (nome, tipo) or None
        "prossimo_festivo": prossimo,  # (nome, data_iso, giorni) or None
        "stagione": _get_stagione(today.month),
        "mese_it": _MESI_IT[today.month],
        "ora_it": now.strftime("%H:%M"),
    }


def is_first_message_of_day(last_ts_str: Optional[str], tz: str = "Europe/Rome") -> bool:
    """
    Ritorna True se l'ultimo messaggio dell'utente era in un giorno precedente
    rispetto ad oggi (nel fuso orario utente). True anche se non c'è nessun messaggio.
    """
    if not last_ts_str:
        return True
    try:
        tz_obj = pytz.timezone(tz)
        today = datetime.now(tz_obj).date()
        last_dt = datetime.fromisoformat(last_ts_str)
        if last_dt.tzinfo is None:
            last_dt = tz_obj.localize(last_dt)
        else:
            last_dt = last_dt.astimezone(tz_obj)
        return today > last_dt.date()
    except Exception:
        return False
