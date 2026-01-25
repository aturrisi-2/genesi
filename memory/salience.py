# core/salience.py
from typing import Dict, List


def compute_salience(
    event_type: str,
    content: Dict,
    past_events: List[Dict]
) -> float:
    """
    Compute how important (salient) an event is.
    Base implementation for Genesi.
    """

    # Default low salience
    salience = 0.3

    text = content.get("text", "").lower()

    # Direct questions are more salient
    if "?" in text:
        salience += 0.3

    # Emotional keywords increase salience
    emotional_keywords = [
        "paura", "ansia", "felice", "triste",
        "odio", "amore", "confuso", "perso"
    ]

    if any(word in text for word in emotional_keywords):
        salience += 0.3

    # Repeated topics increase salience
    for ev in past_events[-5:]:
        ev_text = str(ev.get("content", "")).lower()
        if ev_text and ev_text in text:
            salience += 0.1

    # Clamp between 0 and 1
    return min(salience, 1.0)
