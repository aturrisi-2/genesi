from typing import Dict, List, Any

def compute_salience(event_type: str, content: Dict[str, Any], past_events: List[Dict[str, Any]]) -> float:
    # Salience base in base al tipo di evento
    base_salience = {
        "user_message": 0.4,
        "system_response": 0.2,
        "decision": 0.6,
        "error": 0.7
    }.get(event_type, 0.3)

    salience = base_salience
    text = content.get("text", "")

    # Bonus per testo lungo
    if len(text) > 120:
        salience += 0.1

    # Bonus per presenza di numeri
    if any(c.isdigit() for c in text):
        salience += 0.1

    # Bonus per parole chiave
    keywords = ["sempre", "mai", "importante"]
    if any(keyword in text.lower() for keyword in keywords):
        salience += 0.2

    # Bonus per duplicati
    if any(e.get("content", {}).get("text") == text for e in past_events):
        salience += 0.1

        # Clamp tra 0.0 e 1.0
    salience = max(0.0, min(1.0, salience))
    return salience
