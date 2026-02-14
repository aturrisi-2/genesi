"""
MEMORY STORAGE - Genesi Core v2
Storage persistente per memoria strutturata
API unificata per tutti i moduli neurali
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, Optional
from core.log import log

class MemoryStorage:
    """
    Memory Storage - Persistenza strutturata per profili e stati relazionali
    API unificata: load/save per compatibilità con tutti i moduli
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
            f"{self.base_path}/semantic_facts",
            f"{self.base_path}/episodes",  # NUOVO per memoria episodica
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
    
    def _get_file_path(self, category: str, key: str) -> str:
        """Ottieni percorso file per categoria e chiave"""
        return f"{self.base_path}/{category}/{key}.json"
    
    async def load(self, key: str, default: Any = None) -> Any:
        """
        Carica dati dallo storage - API unificata
        Fail-fast per chiavi profile.
        
        Args:
            key: Chiave storage (formato: categoria:subchiave)
            default: Valore di default se non trovato
            
        Returns:
            Dati caricati o default
        """
        try:
            # Supporta sia formato "categoria:subchiave" sia path diretto
            if ":" in key:
                category, subkey = key.split(":", 1)
                file_path = self._get_file_path(category, subkey)
            else:
                # Path diretto (es: "episodes/user123")
                if "/" in key:
                    category, filename = key.rsplit("/", 1)
                    file_path = f"{self.base_path}/{category}/{filename}.json"
                else:
                    # Fallback a long_term_profile
                    file_path = self._get_file_path("long_term_profile", key)
            
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content.strip():
                        return json.loads(content)
                    else:
                        return default
            
            return default
            
        except json.JSONDecodeError as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.critical(
                "STORAGE_LOAD_FAILURE key=%s error=%s",
                key,
                e
            )
            raise RuntimeError(f"Corrupted JSON for key={key} — system halted")
        except Exception as e:
            log("MEMORY_LOAD_ERROR", error=str(e), key=key)
            return default
    
    async def save(self, key: str, value: Any) -> bool:
        """
        Strict JSON save.
        Fail-fast if data is not fully serializable.
        
        Args:
            key: Chiave storage (formato: categoria:subchiave)
            value: Valore da salvare
            
        Returns:
            Successo salvataggio
        """
        import logging
        logger = logging.getLogger(__name__)

        # HARD VALIDATION: ensure JSON serializable BEFORE writing
        try:
            json_string = json.dumps(value, ensure_ascii=False, indent=2)
        except TypeError as e:
            logger.critical(
                "STORAGE_SERIALIZATION_FAILURE key=%s data_type=%s error=%s",
                key,
                type(value),
                e
            )
            raise RuntimeError("Non-serializable data attempted to persist")

        try:
            # Supporta sia formato "categoria:subchiave" sia path diretto
            if ":" in key:
                category, subkey = key.split(":", 1)
                file_path = self._get_file_path(category, subkey)
            else:
                # Path diretto (es: "episodes/user123")
                if "/" in key:
                    category, filename = key.rsplit("/", 1)
                    file_path = f"{self.base_path}/{category}/{filename}.json"
                else:
                    # Fallback a long_term_profile
                    file_path = self._get_file_path("long_term_profile", key)
            
            # Assicura che directory esista
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Scrivi stringa JSON pre-validata
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(json_string)
            
            # Integrity check: re-read file immediately
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
            except Exception as e:
                logger.critical(
                    "STORAGE_CORRUPTION_DETECTED key=%s error=%s",
                    key,
                    e
                )
                raise RuntimeError("JSON integrity failure after write")

            log("STORAGE_SAVE", path=file_path, key=key)
            return True
            
        except RuntimeError:
            raise
        except Exception as e:
            log("MEMORY_SAVE_ERROR", error=str(e), key=key)
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
