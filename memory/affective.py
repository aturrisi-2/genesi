from typing import Dict, Any

def compute_affect(event_type: str, content: Dict[str, Any]) -> float:
    affect = 0.0
    text = content.get("text", "").lower()
    
    # Valutazione parole chiave
    positive_words = ["grazie", "bene", "ottimo"]
    negative_words = ["male", "odio", "problema"]
    
    if any(word in text for word in positive_words):
        affect += 0.3
    if any(word in text for word in negative_words):
        affect -= 0.4
    
    # Segni di enfasi
    if "!" in text:
        affect += 0.1
    if text.isupper() and len(text) > 1:
        affect += 0.1
    
    # Impatto del tipo di evento
    if event_type == "error":
        affect -= 0.6
    
    # Clamp tra -1.0 e +1.0
    return max(-1.0, min(1.0, affect))