from typing import Dict, List


# Segnali che rendono un evento importante da ricordare
IDENTITY_SIGNALS = [
    "mi chiamo", "il mio nome è", "lavoro come", "sono un", "sono una",
    "ho un figlio", "ho una figlia", "mia moglie", "mio marito",
    "il mio cane", "la mia gatta", "vivo a", "abito a"
]

EMOTIONAL_SIGNALS = [
    "paura", "ansia", "felice", "triste", "odio", "amore",
    "confuso", "perso", "stanco", "arrabbiato", "depresso",
    "preoccupato", "stress", "in crisi", "non ce la faccio",
    "mi sento solo", "sto male", "mi sento male"
]

MEMORY_SIGNALS = [
    "ricorda", "memorizza", "tieni a mente", "ricordati",
    "non dimenticare", "è importante"
]


def compute_salience(
    event_type: str,
    content: Dict,
    past_events: List[Dict]
) -> float:

    salience = 0.3
    text = content.get("text", "").lower()

    # Domande dirette
    if "?" in text:
        salience += 0.2

    # Contenuto emotivo
    if any(w in text for w in EMOTIONAL_SIGNALS):
        salience += 0.3

    # Informazioni identitarie (alta salienza — da ricordare)
    if any(w in text for w in IDENTITY_SIGNALS):
        salience += 0.4

    # Richieste esplicite di memoria
    if any(w in text for w in MEMORY_SIGNALS):
        salience += 0.3

    # Fatti personali rilevati dal tipo evento
    if event_type == "personal_fact":
        salience += 0.3

    # Messaggi lunghi tendono ad essere più salienti
    if len(text.split()) > 20:
        salience += 0.1

    # Ripetizione di temi → più saliente
    for ev in past_events[-5:]:
        ev_text = str(ev.get("content", "")).lower()
        if ev_text and any(word in text for word in ev_text.split()[:5]):
            salience += 0.05

    return min(round(salience, 2), 1.0)
