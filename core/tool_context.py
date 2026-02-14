"""
TOOL CONTEXT MEMORY - Genesi Core
Persiste contesto dell'ultimo tool call (weather, news) per follow-up ellittici.
Es: "che tempo fa a Roma?" -> salva city=Roma
    "e domani?" -> riusa city=Roma

Intent ereditario:
    Se ultimo_intent ∈ {weather, news} E messaggio breve (<6 parole)
    E contiene pattern follow-up geografico → forza stesso intent.
"""

import re
import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# user_id -> last tool context
_tool_contexts: Dict[str, Dict] = defaultdict(dict)

# ── Intent inheritance: geographic follow-up patterns ──
# Short messages (<6 words) containing these patterns inherit the previous tool intent
_GEO_FOLLOWUP_PATTERNS = [
    # "e a <city>?", "e per <city>?"
    r"^e\s+(?:a|ad|per|in|di|da)\s+\S+",
    # "a <city>?", "per <city>?"
    r"^(?:a|ad|per|in|di|da)\s+[A-ZÀ-Ú]\S*",
    # bare city name (capitalized, 1-3 words, optional connector)
    r"^[A-ZÀ-Ú][a-zà-ú']+(?:\s+(?:del|di|della|dello|d'|l'|al|alla|sul|sulla)?\s*[A-ZÀ-Ú][a-zà-ú']+)*\??$",
    # "anche a <city>", "pure a <city>"
    r"^(?:anche|pure)\s+(?:a|ad|per|in|di|da)\s+\S+",
    # "e <city>?" (bare city after "e")
    r"^e\s+[A-ZÀ-Ú][a-zà-ú']+\??$",
]

_GEO_FOLLOWUP_COMPILED = [re.compile(p, re.UNICODE) for p in _GEO_FOLLOWUP_PATTERNS]

# Intents that support inheritance
INHERITABLE_INTENTS = {"weather", "news"}

# Strong intents that must NOT be overridden by inheritance
_STRONG_INTENTS = {"identity", "time", "date", "tecnica", "debug", "spiegazione"}

# Elliptical follow-up patterns (Italian)
ELLIPTICAL_NEWS = [
    "e di politica", "e la politica", "e in politica",
    "e di sport", "e lo sport", "e nello sport",
    "e di cronaca", "e la cronaca", "e in cronaca",
    "e di finanza", "e la finanza", "e in finanza",
    "e di economia", "e l'economia", "e in economia",
    "e le altre notizie", "e le altre",
    "e di tecnologia", "e la tecnologia",
    "e di salute", "e la salute",
    "e di scienza", "e la scienza",
]

ELLIPTICAL_WEATHER = [
    "e domani", "e dopodomani", "e stasera", "e stanotte",
    "e lì", "e li", "e lì vicino", "e li vicino",
    "e la prossima settimana", "e nel weekend",
    "e sabato", "e domenica", "e lunedì", "e martedì",
    "e mercoledì", "e giovedì", "e venerdì",
    "e tra poco", "e più tardi", "e piu tardi",
    "e adesso", "e ora",
    "e là", "e la",
]


def save_tool_context(user_id: str, intent: str, **kwargs):
    """Save tool context after a successful tool call."""
    ctx = {
        "intent": intent,
        "timestamp": datetime.now().isoformat(),
    }
    ctx.update(kwargs)
    _tool_contexts[user_id] = ctx
    logger.info("TOOL_CONTEXT_SAVED user=%s intent=%s keys=%s", user_id, intent, list(kwargs.keys()))


def get_tool_context(user_id: str) -> Optional[Dict]:
    """Get last tool context for user, or None."""
    ctx = _tool_contexts.get(user_id)
    if ctx:
        return dict(ctx)
    return None


def is_elliptical_weather_followup(message: str) -> bool:
    """Check if message is an elliptical follow-up to a weather query."""
    msg_lower = message.lower().strip()
    return any(msg_lower.startswith(p) or msg_lower == p for p in ELLIPTICAL_WEATHER)


def resolve_elliptical_city(user_id: str, message: str) -> Optional[str]:
    """
    If message is an elliptical weather follow-up and we have a saved city,
    return the city. Otherwise None.
    """
    if not is_elliptical_weather_followup(message):
        return None

    ctx = get_tool_context(user_id)
    if not ctx or ctx.get("intent") != "weather":
        return None

    city = ctx.get("city")
    if city:
        logger.info("TOOL_CONTEXT_REUSE user=%s city=%s for_message=%s", user_id, city, message[:30])
        return city

    return None


def is_elliptical_news_followup(message: str) -> bool:
    """Check if message is an elliptical follow-up to a news query."""
    msg_lower = message.lower().strip()
    return any(msg_lower.startswith(p) or msg_lower == p for p in ELLIPTICAL_NEWS)


def resolve_elliptical_news(user_id: str, message: str) -> Optional[str]:
    """
    If message is an elliptical news follow-up and we have a saved news context,
    return the extracted topic. Otherwise None.
    """
    if not is_elliptical_news_followup(message):
        return None

    ctx = get_tool_context(user_id)
    if not ctx or ctx.get("intent") != "news":
        return None

    # Extract the topic from the elliptical message
    msg_lower = message.lower().strip()
    topic_match = re.sub(r"^e\s+(di|la|lo|le|l'|in|nello|nella)?\s*", "", msg_lower).strip().rstrip("?")
    if topic_match:
        logger.info("TOOL_CONTEXT_NEWS_REUSE user=%s topic=%s", user_id, topic_match)
        return topic_match

    return None


# ═══════════════════════════════════════════════════════════════
# INTENT INHERITANCE — geographic follow-up
# ═══════════════════════════════════════════════════════════════

def is_geo_followup(message: str) -> bool:
    """
    Check if a message is a short geographic follow-up.
    Must be <6 words and match a geo follow-up pattern.
    """
    msg = message.strip().rstrip("?!.")
    word_count = len(msg.split())
    if word_count >= 6:
        return False
    return any(p.search(msg) for p in _GEO_FOLLOWUP_COMPILED)


def resolve_inherited_intent(user_id: str, message: str, classified_intent: Optional[str]) -> Optional[str]:
    """
    Intent inheritance: if last_intent ∈ {weather, news} AND message is short (<6 words)
    AND contains a geographic follow-up pattern → force same intent.

    Does NOT override strong intents (identity, time, date, tecnica, etc.).

    Returns the inherited intent string, or None if no inheritance applies.
    """
    # Don't override strong intents
    if classified_intent and classified_intent in _STRONG_INTENTS:
        return None

    # Don't override if already classified as a tool intent
    if classified_intent in INHERITABLE_INTENTS:
        return None

    ctx = get_tool_context(user_id)
    if not ctx:
        return None

    last_intent = ctx.get("intent")
    if last_intent not in INHERITABLE_INTENTS:
        return None

    if not is_geo_followup(message):
        return None

    logger.info("INTENT_INHERITED user=%s from=%s message=%s", user_id, last_intent, message[:40])
    return last_intent
