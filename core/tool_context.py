"""
TOOL CONTEXT MEMORY - Genesi Core
Persiste contesto dell'ultimo tool call (weather, news) per follow-up ellittici.
Es: "che tempo fa a Roma?" -> salva city=Roma
    "e domani?" -> riusa city=Roma
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# user_id -> last tool context
_tool_contexts: Dict[str, Dict] = defaultdict(dict)

# Elliptical follow-up patterns (Italian)
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
