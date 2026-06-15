"""
CHAT MEMORY - Genesi Core v2
Memory conversazionale: cache in-memory + persistenza su disco.
La cache RAM resta veloce; il mirror su disco sopravvive ai restart
(altrimenti ogni riavvio azzerava il filo della conversazione — P1).
1 intent → 1 funzione.
"""

import os
import re
import json
from typing import List, Dict, Any, Optional
from core.memory_storage import memory_storage
from core.log import log

_CHAT_BUFFER_DIR = "memory/chat_buffer"


def _disk_path(user_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(user_id))
    return os.path.join(_CHAT_BUFFER_DIR, f"{safe}.json")


def _persist_to_disk(user_id: str, messages: List[Dict[str, Any]]) -> None:
    """Mirror su disco (fail-silent: un errore disco non deve mai rompere la chat)."""
    try:
        os.makedirs(_CHAT_BUFFER_DIR, exist_ok=True)
        tmp = _disk_path(user_id) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False)
        os.replace(tmp, _disk_path(user_id))  # scrittura atomica
    except Exception as e:
        log("CHAT_MEMORY_PERSIST_ERROR", user_id=user_id, error=str(e))


def _restore_from_disk(user_id: str) -> Optional[List[Dict[str, Any]]]:
    try:
        p = _disk_path(user_id)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
    except Exception as e:
        log("CHAT_MEMORY_RESTORE_ERROR", user_id=user_id, error=str(e))
    return None


class ChatMemory:
    """
    Memory conversazionale - 1 intent → 1 funzione
    Cache RAM + mirror su disco (sopravvive ai restart).
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
            messages = memory_storage.load(key)
            if messages is None:
                # Post-restart: ripristina il filo dal disco prima di appendere
                messages = _restore_from_disk(user_id) or []

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

            # Salva in memoria + mirror su disco (sopravvive ai restart)
            memory_storage.save(key, messages)
            _persist_to_disk(user_id, messages)

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
            messages = memory_storage.load(key)
            if messages is None:
                # Cache RAM vuota (primo accesso o post-restart) → ripristina dal disco
                restored = _restore_from_disk(user_id)
                if restored:
                    memory_storage.save(key, restored)  # riscalda la cache
                    log("CHAT_MEMORY_RESTORED", user_id=user_id, count=len(restored))
                messages = restored or []

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
            # Rimuovi anche il mirror su disco
            try:
                _p = _disk_path(user_id)
                if os.path.exists(_p):
                    os.remove(_p)
            except Exception:
                pass

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
