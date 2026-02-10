"""
MEMORY STORAGE - Genesi Core v2
Storage in-memory per validazione comportamento
Zero I/O, zero effetti collaterali, zero persistenza fantasma
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import threading
from core.log import log

class MemoryStorage:
    """
    Storage in-memory - 1 intent → 1 funzione
    Thread-safe, zero persistenza, solo per validazione comportamento
    """
    
    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._created_at = datetime.now()
        
        log("MEMORY_STORAGE_INIT", status="ready")
    
    def save(self, key: str, value: Any) -> bool:
        """
        Salva dati in memoria - 1 intent → 1 funzione
        
        Args:
            key: Chiave univoca
            value: Valore da salvare
            
        Returns:
            Successo operazione
        """
        try:
            with self._lock:
                self._data[key] = {
                    "value": value,
                    "timestamp": datetime.now().isoformat(),
                    "operation": "save"
                }
            
            log("MEMORY_SAVE", key=key, value_type=type(value).__name__)
            return True
            
        except Exception as e:
            log("MEMORY_SAVE_ERROR", key=key, error=str(e))
            return False
    
    def load(self, key: str) -> Optional[Any]:
        """
        Carica dati dalla memoria - 1 intent → 1 funzione
        
        Args:
            key: Chiave univoca
            
        Returns:
            Valore caricato o None
        """
        try:
            with self._lock:
                if key not in self._data:
                    return None
                
                entry = self._data[key]
                log("MEMORY_LOAD", key=key, value_type=type(entry["value"]).__name__)
                return entry["value"]
                
        except Exception as e:
            log("MEMORY_LOAD_ERROR", key=key, error=str(e))
            return None
    
    def delete(self, key: str) -> bool:
        """
        Elimina dati dalla memoria - 1 intent → 1 funzione
        
        Args:
            key: Chiave univoca
            
        Returns:
            Successo operazione
        """
        try:
            with self._lock:
                if key in self._data:
                    del self._data[key]
                    log("MEMORY_DELETE", key=key)
                    return True
                return False
                
        except Exception as e:
            log("MEMORY_DELETE_ERROR", key=key, error=str(e))
            return False
    
    def exists(self, key: str) -> bool:
        """
        Verifica esistenza dati - 1 intent → 1 funzione
        
        Args:
            key: Chiave univoca
            
        Returns:
            True se esiste, False altrimenti
        """
        try:
            with self._lock:
                exists = key in self._data
                log("MEMORY_EXISTS", key=key, exists=exists)
                return exists
                
        except Exception as e:
            log("MEMORY_EXISTS_ERROR", key=key, error=str(e))
            return False
    
    def list_keys(self) -> List[str]:
        """
        Lista tutte le chiavi - 1 intent → 1 funzione
        
        Returns:
            Lista delle chiavi presenti
        """
        try:
            with self._lock:
                keys = list(self._data.keys())
                log("MEMORY_LIST_KEYS", count=len(keys))
                return keys
                
        except Exception as e:
            log("MEMORY_LIST_KEYS_ERROR", error=str(e))
            return []
    
    def clear(self) -> bool:
        """
        Pulisce tutta la memoria - 1 intent → 1 funzione
        
        Returns:
            Successo operazione
        """
        try:
            with self._lock:
                count = len(self._data)
                self._data.clear()
                log("MEMORY_CLEAR", removed_count=count)
                return True
                
        except Exception as e:
            log("MEMORY_CLEAR_ERROR", error=str(e))
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Statistiche storage - 1 intent → 1 funzione
        
        Returns:
            Statistiche correnti
        """
        try:
            with self._lock:
                stats = {
                    "total_keys": len(self._data),
                    "created_at": self._created_at.isoformat(),
                    "uptime_seconds": (datetime.now() - self._created_at).total_seconds(),
                    "keys": list(self._data.keys())
                }
                log("MEMORY_STATS", **stats)
                return stats
                
        except Exception as e:
            log("MEMORY_STATS_ERROR", error=str(e))
            return {}

# Istanza globale singleton
memory_storage = MemoryStorage()
