"""
MEMORY STORAGE - Genesi Core v2
Storage persistente per memoria strutturata
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, Optional
from core.log import log

class MemoryStorage:
    """
    Memory Storage - Persistenza strutturata per profili e stati relazionali
    Separazione netta tra chat log e memoria persistente
    """
    
    def __init__(self):
        self.base_path = "memory"
        self._ensure_directories()
        log("MEMORY_STORAGE_ACTIVE", base_path=self.base_path)
    
    def _ensure_directories(self):
        """Crea struttura directory memoria"""
        directories = [
            f"{self.base_path}/short_term_chat",
            f"{self.base_path}/long_term_profile", 
            f"{self.base_path}/relational_state",
            f"{self.base_path}/semantic_facts"
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
    
    def _get_file_path(self, category: str, key: str) -> str:
        """Ottieni percorso file per categoria e chiave"""
        return f"{self.base_path}/{category}/{key}.json"
    
    async def get(self, key: str) -> Optional[str]:
        """
        Ottieni valore dallo storage
        
        Args:
            key: Chiave storage (formato: categoria:subchiave)
            
        Returns:
            Valore salvato o None
        """
        try:
            parts = key.split(":", 1)
            if len(parts) != 2:
                return None
            
            category, subkey = parts
            file_path = self._get_file_path(category, subkey)
            
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            
            return None
            
        except Exception as e:
            log("MEMORY_STORAGE_GET_ERROR", error=str(e), key=key)
            return None
    
    async def set(self, key: str, value: str) -> bool:
        """
        Salva valore nello storage
        
        Args:
            key: Chiave storage (formato: categoria:subchiave)
            value: Valore da salvare
            
        Returns:
            Successo salvataggio
        """
        try:
            parts = key.split(":", 1)
            if len(parts) != 2:
                return False
            
            category, subkey = parts
            file_path = self._get_file_path(category, subkey)
            
            # Assicura che directory esista
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(value)
            
            log("STORAGE_WRITE", path=file_path, category=category, subkey=subkey)
            return True
            
        except Exception as e:
            log("MEMORY_STORAGE_SET_ERROR", error=str(e), key=key)
            return False
    
    async def delete(self, key: str) -> bool:
        """
        Elimina valore dallo storage
        
        Args:
            key: Chiave storage
            
        Returns:
            Successo eliminazione
        """
        try:
            parts = key.split(":", 1)
            if len(parts) != 2:
                return False
            
            category, subkey = parts
            file_path = self._get_file_path(category, subkey)
            
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            
            return False
            
        except Exception as e:
            log("MEMORY_STORAGE_DELETE_ERROR", error=str(e), key=key)
            return False
    
    async def list_keys(self, category: str) -> list:
        """
        Lista tutte le chiavi in una categoria
        
        Args:
            category: Categoria storage
            
        Returns:
            Lista chiavi
        """
        try:
            category_path = f"{self.base_path}/{category}"
            if not os.path.exists(category_path):
                return []
            
            keys = []
            for filename in os.listdir(category_path):
                if filename.endswith('.json'):
                    keys.append(filename[:-5])  # Rimuovi .json
            
            return keys
            
        except Exception as e:
            log("MEMORY_STORAGE_LIST_ERROR", error=str(e), category=category)
            return []
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """
        Ottieni statistiche storage
        
        Returns:
            Statistiche storage
        """
        try:
            stats = {}
            
            categories = ["short_term_chat", "long_term_profile", "relational_state", "semantic_facts"]
            
            for category in categories:
                keys = await self.list_keys(category)
                stats[category] = {
                    "count": len(keys),
                    "keys": keys[:10]  # Prime 10 chiavi
                }
            
            return stats
            
        except Exception as e:
            log("MEMORY_STORAGE_STATS_ERROR", error=str(e))
            return {}

# Istanza globale
storage = MemoryStorage()
