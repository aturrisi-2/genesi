"""
RELATIONAL STATE - Relational Engine v1
Gestione stato relazionale in memoria per evoluzione empatica
"""

from typing import Dict

# Stato relazionale in memoria (V1)
_relational_memory: Dict[str, dict] = {}

def load_state(user_id: str) -> dict:
    """
    Carica stato relazionale utente, crea default se non esiste
    
    Args:
        user_id: ID utente
        
    Returns:
        dict: Stato relazionale con trust_level, emotional_depth, attachment_risk
    """
    if user_id not in _relational_memory:
        _relational_memory[user_id] = {
            "trust_level": 0.2,        # Livello fiducia (0-1)
            "emotional_depth": 0.2,    # Profondità emotiva (0-1)
            "attachment_risk": 0.0      # Rischio dipendenza (0-1)
        }
    return _relational_memory[user_id]

def update_state(user_id: str, emotion_data: dict):
    """
    Aggiorna stato relazionale basato su dati emotivi
    
    Args:
        user_id: ID utente
        emotion_data: Dati emotivi da analyze_emotion
        
    Returns:
        dict: Stato aggiornato
    """
    state = load_state(user_id)

    # Incremento graduale fiducia
    state["trust_level"] = min(1.0, state["trust_level"] + 0.01)
    
    # Allineamento profondità emotiva
    state["emotional_depth"] = min(1.0, emotion_data.get("intensity", 0.3))

    # Monitoraggio rischio dipendenza
    if emotion_data.get("vulnerability", 0) > 0.7:
        state["attachment_risk"] = min(1.0, state["attachment_risk"] + 0.05)

    return state

def get_state_summary(user_id: str) -> dict:
    """
    Ottieni riepilogo stato relazionale per monitoring
    
    Args:
        user_id: ID utente
        
    Returns:
        dict: Riepilogo stato con metriche chiave
    """
    state = load_state(user_id)
    return {
        "trust_level": round(state["trust_level"], 3),
        "emotional_depth": round(state["emotional_depth"], 3),
        "attachment_risk": round(state["attachment_risk"], 3),
        "relationship_stage": _get_relationship_stage(state)
    }

def _get_relationship_stage(state: dict) -> str:
    """
    Determina fase relazionale basata su stato
    
    Args:
        state: Stato relazionale
        
    Returns:
        str: Fase relazionale (initial, developing, mature, balanced)
    """
    trust = state["trust_level"]
    depth = state["emotional_depth"]
    risk = state["attachment_risk"]
    
    if trust < 0.4:
        return "initial"
    elif trust < 0.7 and depth < 0.6:
        return "developing"
    elif trust >= 0.7 and depth >= 0.6 and risk < 0.6:
        return "mature"
    else:
        return "balanced"
