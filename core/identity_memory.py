"""
IDENTITY MEMORY
Memoria stabile per informazioni identitarie dell'utente (nome, etc.)
"""

import re
from typing import Optional, Dict, Any
from memory.episodic import search_events, store_event

def extract_name_from_message(message: str) -> Optional[str]:
    """
    Estrae il nome da messaggi tipo "Mi chiamo Mario" o "Io sono Luca"
    
    Args:
        message: Messaggio utente
        
    Returns:
        Nome estratto o None
    """
    message_lower = message.lower().strip()
    
    # Pattern per estrazione nome
    patterns = [
        r"mi chiamo\s+([a-z]+)",
        r"il mio nome è\s+([a-z]+)",
        r"io sono\s+([a-z]+)",
        r"sono\s+([a-z]+)"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, message_lower)
        if match:
            name = match.group(1).capitalize()
            # Filtra nomi non validi
            if len(name) >= 2 and name.isalpha():
                return name
    
    return None

def save_user_name(user_id: str, name: str) -> bool:
    """
    Salva il nome utente in memoria stabile
    
    Args:
        user_id: ID utente
        name: Nome da salvare
        
    Returns:
        True se salvato con successo
    """
    try:
        # Salva come evento speciale di tipo identity
        store_event(
            user_id=user_id,
            type="identity",
            content={"name": name, "type": "user_name"},
            salience=1.0,  # Massima importanza
            affect={"valence": 0.5, "arousal": 0.3}
        )
        print(f"[IDENTITY_MEMORY] Saved name '{name}' for user {user_id}", flush=True)
        return True
    except Exception as e:
        print(f"[IDENTITY_MEMORY] Error saving name: {e}", flush=True)
        return False

def get_user_name(user_id: str) -> Optional[str]:
    """
    Recupera il nome utente dalla memoria
    
    Args:
        user_id: ID utente
        
    Returns:
        Nome utente o None
    """
    try:
        # Cerca eventi di tipo identity con nome
        events = search_events(user_id, "nome", limit=10)
        
        for event in events:
            if hasattr(event, 'content') and isinstance(event.content, dict):
                if event.content.get("type") == "user_name":
                    name = event.content.get("name")
                    if name and isinstance(name, str):
                        print(f"[IDENTITY_MEMORY] Retrieved name '{name}' for user {user_id}", flush=True)
                        return name
        
        print(f"[IDENTITY_MEMORY] No name found for user {user_id}", flush=True)
        return None
        
    except Exception as e:
        print(f"[IDENTITY_MEMORY] Error retrieving name: {e}", flush=True)
        return None

def is_name_query(message: str) -> bool:
    """
    Verifica se il messaggio è una domanda sul nome
    
    Args:
        message: Messaggio utente
        
    Returns:
        True se è una domanda sul nome
    """
    message_lower = message.lower().strip()
    
    name_query_patterns = [
        r"ti ricordi il mio nome",
        r"ricordi il mio nome", 
        r"come ti chiami",
        r"il mio nome",
        r"chi sono",
        r"ti ricordi chi sono"
    ]
    
    return any(re.search(pattern, message_lower) for pattern in name_query_patterns)
