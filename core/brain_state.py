"""
BrainState - Autorità Unica per lo Stato Cognitivo

Struttura centralizzata che contiene tutto lo stato mentale dell'utente.
Tutti gli aggiornamenti devono passare attraverso i metodi di questa classe.
"""

import logging
from typing import Dict, Any, List, Optional
from core.storage import storage
import asyncio

logger = logging.getLogger(__name__)

class BrainState:
    """Autorità unica per lo stato cognitivo dell'utente."""
    
    def __init__(self):
        self._state = {
            "profile": {},
            "relational_state": {},
            "episodic_memory": [],
            "patterns": {},
            "traits": {}
        }
    
    @property
    def profile(self) -> Dict[str, Any]:
        """Profilo utente corrente."""
        return self._state["profile"]
    
    @property
    def relational_state(self) -> Dict[str, Any]:
        """Stato relazionale corrente."""
        return self._state["relational_state"]
    
    @property
    def episodic_memory(self) -> List[Dict[str, Any]]:
        """Memoria episodica corrente."""
        return self._state["episodic_memory"]
    
    @property
    def patterns(self) -> Dict[str, Any]:
        """Pattern riconosciuti corrente."""
        return self._state["patterns"]
    
    @property
    def traits(self) -> Dict[str, Any]:
        """Tratti personali corrente."""
        return self._state["traits"]
    
    def update_profile(self, user_id: str, field: str, value: Any) -> None:
        """Aggiorna campo del profilo e salva persistentemente."""
        self._state["profile"][field] = value
        
        # Salva su storage in modo sicuro
        self._save_profile_sync(user_id)
        
        logger.info("BRAIN_PROFILE_UPDATED user=%s field=%s", user_id, field)
    
    def add_episode(self, user_id: str, episode: Dict[str, Any]) -> None:
        """Aggiunge episodio alla memoria."""
        self._state["episodic_memory"].append(episode)
        
        # Mantieni solo ultimi 100 episodi
        if len(self._state["episodic_memory"]) > 100:
            self._state["episodic_memory"] = self._state["episodic_memory"][-100:]
        
        logger.info("BRAIN_EPISODE_ADDED user=%s episodes=%d", user_id, len(self._state["episodic_memory"]))
    
    def consolidate(self, user_id: str) -> None:
        """Consolida la memoria corrente."""
        # Implementazione base - può essere estesa
        logger.info("BRAIN_CONSOLIDATION user=%s", user_id)
    
    def load_from_storage(self, user_id: str) -> None:
        """Carica stato completo dal storage."""
        try:
            # Carica profilo
            profile = self._load_sync(f"long_term_profile:{user_id}", default={})
            self._state["profile"] = profile
            
            # Carica stato relazionale
            relational = self._load_sync(f"relational_state:{user_id}", default={})
            self._state["relational_state"] = relational
            
            # Carica episodi
            episodes = self._load_sync(f"episodes/{user_id}", default=[])
            self._state["episodic_memory"] = episodes
            
            logger.info("BRAIN_STATE_LOADED user=%s", user_id)
        except Exception as e:
            logger.error("BRAIN_STATE_LOAD_ERROR user=%s error=%s", user_id, str(e))
    
    def _save_profile_sync(self, user_id: str) -> None:
        """Salva profilo in modo sincrono sicuro."""
        try:
            # Salva sync in _storage per accesso immediato
            storage._storage[f"long_term_profile:{user_id}"] = self._state["profile"].copy()
            
            # Trigger async save in background
            try:
                loop = asyncio.get_running_loop()
                asyncio.create_task(storage.save(f"long_term_profile:{user_id}", self._state["profile"].copy()))
            except RuntimeError:
                # No event loop - usa asyncio.run
                asyncio.run(storage.save(f"long_term_profile:{user_id}", self._state["profile"].copy()))
        except Exception as e:
            logger.error("BRAIN_PROFILE_SAVE_ERROR user=%s error=%s", user_id, str(e))
    
    def _load_sync(self, key: str, default: Any) -> Any:
        """Carica dato in modo sincrono sicuro."""
        try:
            # Prima prova _storage per accesso immediato
            if key in storage._storage:
                return storage._storage[key]
            
            # Altrimenti carica da storage in modo sicuro
            try:
                loop = asyncio.get_running_loop()
                # Se loop è attivo, non possiamo usare asyncio.run()
                # Usiamo _storage come fallback
                return storage._storage.get(key, default)
            except RuntimeError:
                # No event loop - usa asyncio.run
                return asyncio.run(storage.load(key, default=default))
        except Exception as e:
            logger.error("BRAIN_LOAD_ERROR key=%s error=%s", key, str(e))
            return default

# Singleton globale
brain_state = BrainState()
