"""
SEMANTIC MEMORY - Genesi Core v2
Memoria semantica persistente per profili utente e dati personali
"""

import re
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from core.log import log
from core.storage import storage

class SemanticMemory:
    """
    Semantic Memory - Estrazione e persistenza dati personali utente
    Pattern recognition per nome, età, città, professione, traits
    """
    
    def __init__(self):
        self.patterns = {
            # Pattern nome
            "name": [
                r"mi chiamo\s+(\w+)",
                r"io mi chiamo\s+(\w+)",
                r"il mio nome è\s+(\w+)",
                r"sono\s+(\w+)(?:\s+e|,|$)",
                r"chiamami\s+(\w+)"
            ],
            # Pattern età
            "age": [
                r"ho\s+(\d+)\s+anni",
                r"(\d+)\s+anni",
                r"età\s+(\d+)"
            ],
            # Pattern città
            "city": [
                r"vivo a\s+(\w+)",
                r"abito a\s+(\w+)",
                r"sono di\s+(\w+)",
                r"vengo da\s+(\w+)"
            ],
            # Pattern professione
            "profession": [
                r"sono un? (\w+(?:\s+\w+)*)\s+(?:lavoro|professione|impiego)",
                r"lavoro come\s+(\w+(?:\s+\w+)*)",
                r"faccio il\s+(\w+(?:\s+\w+)*)",
                r"sono un? (\w+(?:\s+\w+)*)",
                r"professione:\s*(\w+(?:\s+\w+)*)"
            ],
            # Pattern traits
            "traits": [
                r"sono\s+(adventuroso|creativo|timido|estroverso|introverso|ottimista|pessimista|curioso|pratico|sognatore)",
                r"mi considero\s+(\w+)",
                r"carattere:\s*(\w+)"
            ]
        }
        
        log("SEMANTIC_MEMORY_ACTIVE", patterns=len(self.patterns))
    
    async def extract_and_store_personal_data(self, message: str, user_id: str) -> Dict[str, Any]:
        """
        Estrae e salva dati personali dal messaggio
        
        Args:
            message: Messaggio utente
            user_id: ID utente
            
        Returns:
            Dati estratti e salvati
        """
        try:
            # Carica profilo esistente
            profile = await self._load_user_profile(user_id)
            extracted = {}
            
            # Estrai per ogni categoria
            for field, patterns in self.patterns.items():
                for pattern in patterns:
                    matches = re.search(pattern, message, re.IGNORECASE)
                    if matches:
                        value = matches.group(1).strip()
                        
                        # Validazione e pulizia
                        if field == "name":
                            value = value.capitalize()
                        elif field == "age":
                            try:
                                value = int(value)
                                if value < 1 or value > 120:
                                    continue
                            except:
                                continue
                        elif field == "profession":
                            value = value.lower()
                        
                        # Salva solo se nuovo o diverso
                        if field not in profile or profile[field] != value:
                            profile[field] = value
                            extracted[field] = value
                            log("SEMANTIC_MEMORY_EXTRACT", user_id=user_id, field=field, value=value)
                            
                            # Salva immediatamente
                            await self._save_user_profile(user_id, profile)
                            log("SEMANTIC_MEMORY_SAVE", user_id=user_id, field=field, value=value)
                            break
            
            return extracted
            
        except Exception as e:
            log("SEMANTIC_MEMORY_ERROR", error=str(e), user_id=user_id)
            return {}
    
    async def _load_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Carica profilo utente dallo storage con API unificata
        
        Args:
            user_id: ID utente
            
        Returns:
            Profilo utente
        """
        try:
            # Usa API unificata load
            profile_data = await storage.load(f"profile:{user_id}", default={})
            log("PROFILE_AFTER_LOAD", user_id=user_id, profile=profile_data)
            if profile_data:
                return profile_data
            else:
                # Profilo vuoto di default
                return {
                    "name": None,
                    "age": None,
                    "city": None,
                    "profession": None,
                    "traits": [],
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
        except Exception as e:
            log("SEMANTIC_MEMORY_LOAD_ERROR", error=str(e), user_id=user_id)
            return {}
    
    async def _save_user_profile(self, user_id: str, profile: Dict[str, Any]) -> bool:
        """
        Salva profilo utente nello storage con API unificata
        
        Args:
            user_id: ID utente
            profile: Profilo da salvare
        
        Returns:
            Successo salvataggio
        """
        try:
            profile["updated_at"] = datetime.now().isoformat()
            # Usa API unificata save
            await storage.save(f"profile:{user_id}", profile)
            log("PROFILE_PERSISTED", user_id=user_id, fields=list(profile.keys()))
            return True
        except Exception as e:
            log("SEMANTIC_MEMORY_SAVE_ERROR", error=str(e), user_id=user_id)
            return False
    
    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Ottieni profilo utente completo
        
        Args:
            user_id: ID utente
            
        Returns:
            Profilo utente
        """
        return await self._load_user_profile(user_id)
    
    def get_profile(self, user_id: str) -> Dict[str, Any]:
        """Sync wrapper for get_user_profile."""
        import asyncio
        return asyncio.run(self.get_user_profile(user_id))
    
    async def save_user_profile(self, user_id: str, profile: Dict[str, Any]) -> bool:
        """
        Salva profilo utente completo con API unificata
        
        Args:
            user_id: ID utente
            profile: Profilo da salvare
        
        Returns:
            Successo salvataggio
        """
        return await self._save_user_profile(user_id, profile)
    
    async def update_emotional_pattern(self, user_id: str, emotion: str, intensity: float):
        """
        Aggiorna pattern emotivi utente
        
        Args:
            user_id: ID utente
            emotion: Emozione corrente
            intensity: Intensità emozione
        """
        try:
            emotional_pattern = await self._load_emotional_pattern(user_id)
            
            if emotional_pattern is None:
                emotional_pattern = []
            
            # Aggiungi pattern emotivo
            pattern_entry = {
                "emotion": emotion,
                "intensity": intensity,
                "timestamp": datetime.now().isoformat()
            }
            
            emotional_pattern.append(pattern_entry)
            
            # Mantieni solo ultimi 50 pattern
            if len(emotional_pattern) > 50:
                emotional_pattern = emotional_pattern[-50:]
            
            await self._save_emotional_pattern(user_id, emotional_pattern)
            
        except Exception as e:
            log("EMOTIONAL_PATTERN_ERROR", error=str(e), user_id=user_id)
    
    async def _load_emotional_pattern(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Carica pattern emotivi utente dallo storage con API unificata
        
        Args:
            user_id: ID utente
            
        Returns:
            Pattern emotivi utente
        """
        try:
            # Usa API unificata load
            emotional_pattern_data = await storage.load(f"emotional_pattern:{user_id}", default=[])
            log("EMOTIONAL_PATTERN_AFTER_LOAD", user_id=user_id, emotional_pattern=emotional_pattern_data)
            return emotional_pattern_data
        except Exception as e:
            log("EMOTIONAL_PATTERN_LOAD_ERROR", error=str(e), user_id=user_id)
            return []
    
    async def _save_emotional_pattern(self, user_id: str, emotional_pattern: List[Dict[str, Any]]) -> bool:
        """
        Salva pattern emotivi utente nello storage con API unificata
        
        Args:
            user_id: ID utente
            emotional_pattern: Pattern emotivi da salvare
        
        Returns:
            Successo salvataggio
        """
        try:
            # Usa API unificata save
            await storage.save(f"emotional_pattern:{user_id}", emotional_pattern)
            log("EMOTIONAL_PATTERN_PERSISTED", user_id=user_id, fields=len(emotional_pattern))
            return True
        except Exception as e:
            log("EMOTIONAL_PATTERN_SAVE_ERROR", error=str(e), user_id=user_id)
            return False
    
    async def get_memory_summary(self, user_id: str) -> Dict[str, Any]:
        """
        Ottieni riepilogo memoria utente
        
        Args:
            user_id: ID utente
        
        Returns:
            Riepilogo memoria
        """
        try:
            profile = await self._load_user_profile(user_id)
            emotional_pattern = await self._load_emotional_pattern(user_id)
            
            return {
                "user_id": user_id,
                "has_name": bool(profile.get("name")),
                "has_age": bool(profile.get("age")),
                "has_city": bool(profile.get("city")),
                "has_profession": bool(profile.get("profession")),
                "traits_count": len(profile.get("traits", [])),
                "emotional_patterns_count": len(emotional_pattern),
                "created_at": profile.get("created_at"),
                "updated_at": profile.get("updated_at")
            }
        except Exception as e:
            log("MEMORY_SUMMARY_ERROR", error=str(e), user_id=user_id)
            return {}

# Istanza globale
semantic_memory = SemanticMemory()
