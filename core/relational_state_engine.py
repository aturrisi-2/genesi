"""
Relational State Engine - Sistema di stati relazionali per Genesi
Determina lo stato relazionale basato su pattern emotivi e metriche conversazionali.
"""

import logging
from enum import Enum
from typing import Dict, Any

logger = logging.getLogger(__name__)


class RelationalState(Enum):
    """Stati relazionali possibili per Genesi."""
    NEUTRAL = "neutral"
    ATTUNED = "attuned"
    ENGAGED = "engaged"
    REFLECTIVE = "reflective"
    SUPPORTIVE_DEEP = "supportive_deep"
    CONFRONTATIONAL = "confrontational"


class RelationalStateEngine:
    """
    Motore per determinare lo stato relazionale basato su metriche conversazionali.
    
    Logica deterministica e semplice per valutare il rapporto utente-Genesi.
    """
    
    def __init__(self):
        """Inizializza il motore degli stati relazionali."""
        self.state_history = []
        self.last_state = RelationalState.NEUTRAL.value
        self.state_persistence_counter = 0
    
    def evaluate_state(
        self,
        emotional_pattern_count: int,
        repetition_rate: float,
        message_count: int,
        last_intent: str
    ) -> str:
        """
        Valuta lo stato relazionale basato sulle metriche fornite.
        
        Args:
            emotional_pattern_count: Numero di pattern emotivi rilevati
            repetition_rate: Tasso di ripetizione (0.0-1.0)
            message_count: Numero totale di messaggi scambiati
            last_intent: Ultimo intent rilevato
            
        Returns:
            str: Stato relazionale come stringa
        """
        # Regole prioritarie in ordine di importanza
        
        # 1. Alta ripetizione -> stato confrontazionale
        if repetition_rate > 0.6:
            state = RelationalState.CONFRONTATIONAL.value
        
        # 2. Pattern emotivi intensi -> stato di supporto profondo
        elif emotional_pattern_count >= 5:
            state = RelationalState.SUPPORTIVE_DEEP.value
        
        # 3. Pattern emotivi moderati -> stato sintonizzato
        elif emotional_pattern_count >= 3:
            state = RelationalState.ATTUNED.value
        
        # 4. Engagment basato su intent e messaggi
        elif (last_intent in ["chat_free", "how_are_you"] and 
              message_count > 5):
            state = RelationalState.ENGAGED.value
        
        # 5. Fallback neutro
        else:
            state = RelationalState.NEUTRAL.value
        
        # 🆕 Relational Stability Layer
        old_state = self.last_state
        applied_state = state
        
        # Eccezione: confrontational bypassa stabilità
        if state != RelationalState.CONFRONTATIONAL.value:
            if state == old_state:
                # Stesso stato -> incrementa counter
                self.state_persistence_counter += 1
            else:
                # Nuovo stato -> verifica stabilità
                if self.state_persistence_counter < 2:
                    # Non abbastanza persistente -> mantieni vecchio stato
                    applied_state = old_state
                    self.state_persistence_counter += 1
                else:
                    # Abbastanza persistente -> accetta nuovo stato
                    self.last_state = state
                    self.state_persistence_counter = 0
        else:
            # Confrontational entra subito
            self.last_state = state
            self.state_persistence_counter = 0
        
        # Log stabilità
        logger.info("RELATIONAL_STABILITY old=%s new=%s applied=%s", 
                   old_state, state, applied_state)
        
        # Salva nella storia per analisi future
        self.state_history.append({
            "state": applied_state,
            "emotional_pattern_count": emotional_pattern_count,
            "repetition_rate": repetition_rate,
            "message_count": message_count,
            "last_intent": last_intent
        })
        
        # Mantieni solo ultimi 50 stati
        if len(self.state_history) > 50:
            self.state_history = self.state_history[-50:]
        
        return applied_state
    
    def get_state_history(self, limit: int = 10) -> Dict[str, Any]:
        """
        Restituisce la cronologia degli stati recenti.
        
        Args:
            limit: Numero massimo di stati da restituire
            
        Returns:
            Dict con cronologia stati
        """
        return {
            "recent_states": self.state_history[-limit:],
            "total_states": len(self.state_history),
            "current_state": self.state_history[-1]["state"] if self.state_history else RelationalState.NEUTRAL.value
        }
    
    def get_state_description(self, state: str) -> str:
        """
        Restituisce una descrizione dello stato relazionale.
        
        Args:
            state: Stato relazionale
            
        Returns:
            str: Descrizione dello stato
        """
        descriptions = {
            RelationalState.NEUTRAL.value: "Stato neutro e bilanciato",
            RelationalState.ATTUNED.value: "Sintonizzato emotivamente con l'utente",
            RelationalState.ENGAGED.value: "Coinvolto attivamente nella conversazione",
            RelationalState.REFLECTIVE.value: "Modalità riflessiva e contemplativa",
            RelationalState.SUPPORTIVE_DEEP.value: "Supporto profondo e empatico",
            RelationalState.CONFRONTATIONAL.value: "Modalità diretta e confrontazionale"
        }
        return descriptions.get(state, "Stato sconosciuto")
