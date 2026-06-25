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

# Explicit, generic markers that a line is NOT operational (personal/domestic/
# off-topic note). No domain object is hardcoded — only the speaker's own
# "this is not operational" framing is honoured.
_NON_OPERATIONAL_MARKERS = (
    "nota non operativa",
    "non operativa",
    "non operativo",
    "fuori contesto",
    "off topic",
    "off-topic",
    "nota personale",
    "promemoria personale",
    "promemoria domestico",
    "questione personale",
    "niente di operativo",
    "nulla di operativo",
    "not operational",
    "non-operational",
    "personal note",
)


def is_non_operational_note(text: str) -> bool:
    """True when the line explicitly frames itself as non-operational/personal.

    Generic and conservative: it triggers only on an explicit marker, never on
    the domestic object itself — so a real operational project ignores it while a
    domestic/family project (which never adds such markers) keeps its items."""
    normalized = normalize_quality_text(text)
    if not normalized:
        return False
    return any(marker in normalized for marker in _NON_OPERATIONAL_MARKERS)


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


# Generic markers that a message is about the SYSTEM/bot/test itself, not the
# project's operational work. No chat/domain/person token hardcoded.
_META_SYSTEM_MARKERS = (
    "genesi", "gemini", "chatgpt", "chatbot", "assistente virtuale", "assistente ai",
    "intelligenza artificiale", "per testare", "sto testando", "test del sistema",
    "progetto di test", "progetto per testare", "bot nel gruppo", "testare la gestione",
)


def _looks_meta_system(text: str) -> bool:
    normalized = normalize_quality_text(text)
    return any(marker in normalized for marker in _META_SYSTEM_MARKERS)


# Pure media-trigger phrases: they only ask Genesi to look at an attachment, they
# are NOT operational items themselves (the real content comes from OCR/vision).
_MEDIA_TRIGGER_PHRASES = (
    "analizza questa immagine", "analizza l'immagine", "analizza immagine",
    "guarda questa immagine", "guarda questa foto", "guarda la foto",
    "guarda questo video", "guarda il video", "ascolta questo audio",
    "analizza questo video", "analizza questo audio",
)


def _is_media_trigger(text: str) -> bool:
    normalized = normalize_quality_text(text)
    if not normalized:
        return False
    # Trigger only if the message is essentially just the phrase (short), not when
    # the phrase is embedded in a longer operational sentence.
    return any(normalized == p or normalized.startswith(p) for p in _MEDIA_TRIGGER_PHRASES) and len(normalized) <= 60


def classify_ingest(item: OperationalItem, category: str, parent_context: str = "") -> tuple[str, str]:
    """Triage an extracted item into one of: 'accepted' | 'needs_review' | 'ignored'.

    Returns (decision, reason). Deterministic, generic (no domain/chat token). Only
    `accepted` items belong in the active operational state; `needs_review` go to a
    reviewable queue; `ignored` is dropped. Conservative: items with real technical
    signal or explicit context are accepted; clear noise/meta is ignored; weak or
    contextless items are deferred to review, never silently kept as active."""
    text = item.text or ""
    ctx = has_item_context(item)
    # Broader technical signal: reuse the context extractor (codes/zones/components,
    # handles hyphenated codes like QF-01 / EWC-10). A bare generic keyword
    # ("verificare", "documentazione") yields no tag → NOT strong enough to accept.
    try:
        from core.operational_memory.context_extractor import extract_context
        extracted_tags = extract_context(text).context_tags
    except Exception:
        extracted_tags = []
    strong = ctx or bool(extracted_tags) or bool(_TECHNICAL_CODE_RE.search(text))
    weak_conf = getattr(item, "confidence", "medium") == "low"

    # A meta-system message (about Genesi/bot/test) is dropped unless it carries a
    # REAL technical code (generic tags like "progetto"/"test" do NOT rescue it).
    has_code = bool(_TECHNICAL_CODE_RE.search(text))

    # Clear drops first.
    if is_non_operational_note(text):
        return ("ignored", "non_operational_marker")
    if _is_media_trigger(text):
        return ("ignored", "media_trigger")
    if _looks_meta_system(text) and not has_code:
        return ("ignored", "meta_system")
    if is_noise_text(text) and not strong:
        return ("ignored", "possible_joke")

    sig = is_technically_significant(text)

    # Decisions are high-value and rare (incl. conditional safety-net) → never
    # diverted by the noise filter; meta/noise drops above still apply.
    if category == "decision":
        return ("accepted", "")
    # Question/task are the noisy categories → require a strong signal (code/zone/
    # context), a generic keyword is NOT enough.
    if category == "question":
        if strong or (parent_context or "").strip():
            return ("accepted", "")
        return ("needs_review", "vague_question")
    if category == "task":
        actionable = bool(getattr(item, "owner", None) or getattr(item, "due", None)) or strong
        if actionable and not weak_conf:
            return ("accepted", "")
        return ("needs_review", "weak_task")
    # Issue/information: accept on strong signal OR real technical significance
    # (keyword/anomaly), so genuine issues ("mancano 12 pannelli") are not lost.
    if category == "issue":
        if strong or sig:
            return ("accepted", "")
        return ("needs_review", "missing_context")
    if category == "information":
        if strong or sig:
            return ("accepted", "")
        return ("needs_review", "low_confidence")
    # Unknown category → conservative accept (don't lose data).
    return ("accepted", "")


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
