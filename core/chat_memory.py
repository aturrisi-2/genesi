"""
CHAT MEMORY - Genesi Core v2
Memory conversazionale in-memory
1 intent → 1 funzione, zero persistenza
"""

from typing import List, Dict, Any, Optional
from core.memory_storage import memory_storage
from core.log import log

class ChatMemory:
    """
    Memory conversazionale - 1 intent → 1 funzione
    Storage in-memory per validazione comportamento
    """
    
    def __init__(self, max_messages: int = 100):
        self.max_messages = max_messages
        self.prefix = "chat:"
    
    def add_message(self, user_id: str, message: str, response: str, intent: str) -> bool:
        """
        Aggiungi messaggio alla memoria - 1 intent → 1 funzione
        
        Args:
            user_id: ID utente
            message: Messaggio utente
            response: Risposta sistema
            intent: Intent classificato
            
        Returns:
            Successo operazione
        """
        try:
            key = f"{self.prefix}{user_id}"
            messages = memory_storage.load(key) or []
            
            # Nuovo messaggio
            new_message = {
                "timestamp": "now",
                "user_message": message,
                "system_response": response,
                "intent": intent
            }
            
            # Aggiungi alla lista
            messages.append(new_message)
            
            # Mantieni solo gli ultimi max_messages
            if len(messages) > self.max_messages:
                messages = messages[-self.max_messages:]
            
            # Salva in memoria
            memory_storage.save(key, messages)
            
            log("CHAT_MEMORY_ADD", user_id=user_id, intent=intent, total=len(messages))
            return True
            
        except Exception as e:
            log("CHAT_MEMORY_ADD_ERROR", user_id=user_id, error=str(e))
            return False
    
    def get_messages(self, user_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Ottieni messaggi utente - 1 intent → 1 funzione
        
        Args:
            user_id: ID utente
            limit: Limite messaggi (opzionale)
            
        Returns:
            Lista messaggi
        """
        try:
            key = f"{self.prefix}{user_id}"
            messages = memory_storage.load(key) or []
            
            if limit and limit > 0:
                messages = messages[-limit:]
            
            log("CHAT_MEMORY_GET", user_id=user_id, count=len(messages))
            return messages
            
        except Exception as e:
            log("CHAT_MEMORY_GET_ERROR", user_id=user_id, error=str(e))
            return []
    
    def get_last_message(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Ottieni ultimo messaggio - 1 intent → 1 funzione
        
        Args:
            user_id: ID utente
            
        Returns:
            Ultimo messaggio o None
        """
        messages = self.get_messages(user_id, 1)
        return messages[0] if messages else None
    
    def clear_messages(self, user_id: str) -> bool:
        """
        Pulisci messaggi utente - 1 intent → 1 funzione
        
        Args:
            user_id: ID utente
            
        Returns:
            Successo operazione
        """
        try:
            key = f"{self.prefix}{user_id}"
            success = memory_storage.delete(key)
            
            if success:
                log("CHAT_MEMORY_CLEAR", user_id=user_id)
            else:
                log("CHAT_MEMORY_CLEAR_NOT_FOUND", user_id=user_id)
            
            return success
            
        except Exception as e:
            log("CHAT_MEMORY_CLEAR_ERROR", user_id=user_id, error=str(e))
            return False
    
    def get_message_count(self, user_id: str) -> int:
        """
        Conta messaggi utente - 1 intent → 1 funzione
        
        Args:
            user_id: ID utente
            
        Returns:
            Numero messaggi
        """
        messages = self.get_messages(user_id)
        return len(messages)
    
    def get_intents_summary(self, user_id: str) -> Dict[str, int]:
        """
        Riassunto intent per utente - 1 intent → 1 funzione
        
        Args:
            user_id: ID utente
            
        Returns:
            Dizionario intent → count
        """
        messages = self.get_messages(user_id)
        intents_count = {}
        
        for msg in messages:
            intent = msg.get("intent", "unknown")
            intents_count[intent] = intents_count.get(intent, 0) + 1
        
        log("CHAT_MEMORY_INTENTS_SUMMARY", user_id=user_id, intents=intents_count)
        return intents_count

# Istanza globale
chat_memory = ChatMemory()
