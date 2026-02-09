"""
IDENTITY MEMORY
Memoria stabile per informazioni identitarie dell'utente (nome, etc.)
"""

import re
from typing import Optional, Dict, Any

# Memoria temporanea per test (in produzione usa database)
_identity_memory_store: Dict[str, Dict[str, Any]] = {}

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
    
    # Pattern per nomi singoli (es. "Alfio", "Marco")
    # Se il messaggio è solo un nome proprio
    words = message_lower.split()
    if len(words) == 1 and len(words[0]) >= 2 and words[0].isalpha():
        # Verifica che sia un nome italiano comune
        common_names = {
            'marco', 'paolo', 'luca', 'alessandro', 'francesco', 'lorenzo', 
            'mattia', 'davide', 'simone', 'andrea', 'riccardo', 'giulio',
            'maria', 'sara', 'giulia', 'sofia', 'alice', 'chiara', 'valentina',
            'alfio', 'mario', 'antonio', 'giuseppe', 'giovanni', 'stefano'
        }
        if words[0] in common_names:
            return words[0].capitalize()
    
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
        # Salva in memoria temporanea
        if user_id not in _identity_memory_store:
            _identity_memory_store[user_id] = {}
        
        _identity_memory_store[user_id]['name'] = name
        _identity_memory_store[user_id]['type'] = 'user_name'
        
        print(f"[IDENTITY_MEMORY] Saved name '{name}' for user {user_id}", flush=True)
        
        # Tentativo di salvare anche in memoria episodica
        try:
            from memory.episodic import store_event
            store_event(
                user_id=user_id,
                type="identity",
                content={"name": name, "type": "user_name"},
                salience=1.0,  # Massima importanza
                affect={"valence": 0.5, "arousal": 0.3}
            )
            print(f"[IDENTITY_MEMORY] Also saved to episodic memory", flush=True)
        except Exception as e:
            print(f"[IDENTITY_MEMORY] Episodic save failed: {e}", flush=True)
        
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
        # Prima controlla memoria temporanea
        if user_id in _identity_memory_store:
            name = _identity_memory_store[user_id].get('name')
            if name:
                print(f"[IDENTITY_MEMORY] Retrieved name '{name}' from temp memory for user {user_id}", flush=True)
                return name
        
        # Poi controlla memoria episodica
        try:
            from memory.episodic import get_recent_events
            events = get_recent_events(user_id, limit=20)
            
            for event in events:
                if hasattr(event, 'type') and event.type == "identity":
                    if hasattr(event, 'content') and isinstance(event.content, dict):
                        if event.content.get("type") == "user_name":
                            name = event.content.get("name")
                            if name and isinstance(name, str):
                                print(f"[IDENTITY_MEMORY] Retrieved name '{name}' from episodic memory for user {user_id}", flush=True)
                                # Salva anche in memoria temporanea per futuro
                                if user_id not in _identity_memory_store:
                                    _identity_memory_store[user_id] = {}
                                _identity_memory_store[user_id]['name'] = name
                                _identity_memory_store[user_id]['type'] = 'user_name'
                                return name
        except Exception as e:
            print(f"[IDENTITY_MEMORY] Episodic search failed: {e}", flush=True)
        
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
