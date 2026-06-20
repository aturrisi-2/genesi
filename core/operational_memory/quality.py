from __future__ import annotations

import re
import unicodedata

from core.operational_memory.models import OperationalItem, OperationalTask


_PLACEHOLDER_PATTERNS = (
    "sticker non incluso",
    "sticker omitted",
    "immagine omessa",
    "image omitted",
    "video omesso",
    "video omitted",
    "audio omesso",
    "audio omitted",
    "messaggio eliminato",
    "message deleted",
    "media omesso",
    "media omitted",
)

_ISOLATED_SOCIAL_WORDS = {
    "ok",
    "okay",
    "si",
    "s",
    "no",
    "grazie",
    "top",
    "perfetto",
    "bene",
    "va",
    "benissimo",
}

_SOCIAL_PHRASES = {
    "va bene",
    "ok grazie",
    "grazie mille",
    "perfetto grazie",
    "top top",
    "top top top",
    "non mi risulta",
    "adesso",
}

_GENERIC_OPERATIONAL_PHRASES = {
    "da controllare",
    "controllare",
    "da verificare",
    "verificare",
}

_TECHNICAL_KEYWORDS = (
    "manca",
    "mancano",
    "mancante",
    "non parte",
    "non funziona",
    "guasto",
    "errore",
    "blocco",
    "problema",
    "sostituire",
    "sostituzione",
    "verificare",
    "controllare",
    "installare",
    "collegare",
    "configurare",
    "ripristinare",
    "consegna",
    "conferma",
    "confermare",
    "scadenza",
    "spostare",
    "spostata",
    "spostato",
    "materiale",
    "quadro",
    "stuccatura",
    "servomotore",
    "potenziometro",
    "motore",
    "scheda",
    "sensore",
    "impianto",
    "linea",
)

_TECHNICAL_CODE_RE = re.compile(r"\b[A-Z]{1,4}\d{1,4}\b|\b\d{1,3}[A-Z]\b")


def normalize_quality_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


def is_noise_text(text: str) -> bool:
    normalized = normalize_quality_text(text)
    if not normalized:
        return True
    if any(pattern in normalized for pattern in _PLACEHOLDER_PATTERNS):
        return True
    if normalized in _SOCIAL_PHRASES:
        return True

    tokens = re.findall(r"[a-z]+", normalized)
    if tokens and len(tokens) <= 4 and all(token in _ISOLATED_SOCIAL_WORDS for token in tokens):
        return True
    return False


def is_technically_significant(text: str) -> bool:
    normalized = normalize_quality_text(text)
    if is_noise_text(normalized):
        return False
    if normalized in _GENERIC_OPERATIONAL_PHRASES:
        return False
    if any(keyword in normalized for keyword in _TECHNICAL_KEYWORDS):
        return True
    return bool(_TECHNICAL_CODE_RE.search(text or ""))


def should_include_in_report(item: OperationalItem) -> bool:
    if is_noise_text(item.text):
        return False
    if should_verify_item(item):
        return False
    if item.confidence == "high":
        return True
    if item.confidence == "medium":
        if isinstance(item, OperationalTask) and (item.owner or item.due):
            return True
        return is_technically_significant(item.text)
    return False


def has_item_context(item: OperationalItem) -> bool:
    return bool(
        item.context_area
        or item.context_system
        or item.context_level
        or item.context_location
        or item.context_tags
    )


def should_verify_item(item: OperationalItem) -> bool:
    if is_noise_text(item.text):
        return False
    if item.confidence == "low":
        return False
    return not has_item_context(item) and not is_technically_significant(item.text)


def next_action_priority(item: OperationalItem) -> int:
    if isinstance(item, OperationalTask):
        if not item.due:
            return 20
        if not item.owner:
            return 30
        return 90
    if is_technically_significant(item.text):
        return 10
    return 80
