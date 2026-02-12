"""
MEMORY STORAGE - Genesi Core v2
Storage in-memory thread-safe con validazione
"""

import logging
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class MemoryStorage:
    """
    Storage in-memory - 1 intent → 1 funzione
    Thread-safe, zero persistenza, solo per validazione comportamento
    """
    
    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._created_at = datetime.now()
        
        logger.info("MEMORY_STORAGE_INIT", extra={"status": "ready"})
    
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
            
            logger.info("MEMORY_SAVE", extra={"key": key, "value_type": type(value).__name__})
            return True
            
        except Exception as e:
            logger.error("MEMORY_SAVE_ERROR", exc_info=True, extra={"key": key, "error": str(e)})
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
                logger.info("MEMORY_LOAD", extra={"key": key, "value_type": type(entry["value"]).__name__})
                return entry["value"]
                
        except Exception as e:
            logger.error("MEMORY_LOAD_ERROR", exc_info=True, extra={"key": key, "error": str(e)})
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
                    logger.info("MEMORY_DELETE", extra={"key": key})
                    return True
                return False
                
        except Exception as e:
            logger.error("MEMORY_DELETE_ERROR", exc_info=True, extra={"key": key, "error": str(e)})
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
                logger.info("MEMORY_EXISTS", extra={"key": key, "exists": exists})
                return exists
                
        except Exception as e:
            logger.error("MEMORY_EXISTS_ERROR", exc_info=True, extra={"key": key, "error": str(e)})
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
                logger.info("MEMORY_LIST_KEYS", extra={"count": len(keys)})
                return keys
                
        except Exception as e:
            logger.error("MEMORY_LIST_KEYS_ERROR", exc_info=True, extra={"error": str(e)})
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
                logger.info("MEMORY_CLEAR", extra={"removed_count": count})
                return True
                
        except Exception as e:
            logger.error("MEMORY_CLEAR_ERROR", exc_info=True, extra={"error": str(e)})
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
                logger.info("MEMORY_STATS", extra=stats)
                return stats
                
        except Exception as e:
            logger.error("MEMORY_STATS_ERROR", exc_info=True, extra={"error": str(e)})
            return {}

# Istanza globale singleton
memory_storage = MemoryStorage()
