"""
USER MANAGER - Genesi Core v2
Gestione utenti con storage in-memory
1 intent → 1 funzione, zero persistenza
"""

from typing import Dict, Any, Optional
from core.memory_storage import memory_storage
from core.log import log

class UserManager:
    """
    Gestione utenti - 1 intent → 1 funzione
    Storage in-memory per validazione comportamento
    """
    
    def __init__(self):
        self.prefix = "user:"
    
    def create_user(self, user_id: str) -> Dict[str, Any]:
        """
        Crea utente - 1 intent → 1 funzione
        
        Args:
            user_id: ID univoco utente
            
        Returns:
            Dati utente creati
        """
        user_data = {
            "user_id": user_id,
            "created_at": "now",
            "message_count": 0,
            "last_seen": "now",
            "preferences": {}
        }
        
        # Salva in memoria
        key = f"{self.prefix}{user_id}"
        memory_storage.save(key, user_data)
        
        log("USER_CREATE", user_id=user_id)
        return user_data
    
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Ottieni utente - 1 intent → 1 funzione
        
        Args:
            user_id: ID univoco utente
            
        Returns:
            Dati utente o None
        """
        key = f"{self.prefix}{user_id}"
        user_data = memory_storage.load(key)
        
        if user_data:
            log("USER_GET", user_id=user_id)
        else:
            log("USER_NOT_FOUND", user_id=user_id)
        
        return user_data
    
    def update_user(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """
        Aggiorna utente - 1 intent → 1 funzione
        
        Args:
            user_id: ID univoco utente
            updates: Dati da aggiornare
            
        Returns:
            Successo operazione
        """
        key = f"{self.prefix}{user_id}"
        user_data = memory_storage.load(key)
        
        if not user_data:
            log("USER_UPDATE_NOT_FOUND", user_id=user_id)
            return False
        
        # Aggiorna dati
        user_data.update(updates)
        memory_storage.save(key, user_data)
        
        log("USER_UPDATE", user_id=user_id, updates=list(updates.keys()))
        return True
    
    def delete_user(self, user_id: str) -> bool:
        """
        Elimina utente - 1 intent → 1 funzione
        
        Args:
            user_id: ID univoco utente
            
        Returns:
            Successo operazione
        """
        key = f"{self.prefix}{user_id}"
        success = memory_storage.delete(key)
        
        if success:
            log("USER_DELETE", user_id=user_id)
        else:
            log("USER_DELETE_NOT_FOUND", user_id=user_id)
        
        return success
    
    def increment_messages(self, user_id: str) -> bool:
        """
        Incrementa contatore messaggi - 1 intent → 1 funzione
        
        Args:
            user_id: ID univoco utente
            
        Returns:
            Successo operazione
        """
        return self.update_user(user_id, {
            "message_count": self.get_user(user_id).get("message_count", 0) + 1,
            "last_seen": "now"
        })
    
    def set_preference(self, user_id: str, key: str, value: Any) -> bool:
        """
        Imposta preferenza utente - 1 intent → 1 funzione
        
        Args:
            user_id: ID univoco utente
            key: Chiave preferenza
            value: Valore preferenza
            
        Returns:
            Successo operazione
        """
        user_data = self.get_user(user_id)
        if not user_data:
            return False
        
        preferences = user_data.get("preferences", {})
        preferences[key] = value
        
        return self.update_user(user_id, {"preferences": preferences})
    
    def get_preference(self, user_id: str, key: str, default: Any = None) -> Any:
        """
        Ottieni preferenza utente - 1 intent → 1 funzione
        
        Args:
            user_id: ID univoco utente
            key: Chiave preferenza
            default: Valore di default
            
        Returns:
            Valore preferenza o default
        """
        user_data = self.get_user(user_id)
        if not user_data:
            return default
        
        preferences = user_data.get("preferences", {})
        return preferences.get(key, default)

# Istanza globale
user_manager = UserManager()
