"""
RELATIONAL STATE - Relational Engine v1
Gestione stato relazionale persistente con history e trends
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from core.log import log
from core.storage import storage

class RelationalState:
    """
    Relational State - Gestione stato relazionale persistente
    Con history, trends, e emotional variance tracking
    """
    
    def __init__(self):
        log("RELATIONAL_STATE_ACTIVE")
    
    async def load_state(self, user_id: str) -> Dict[str, Any]:
        """
        Carica stato relazionale persistente
        
        Args:
            user_id: ID utente
            
        Returns:
            Stato relazionale completo
        """
        try:
            state_data = await storage.get(f"relational_state:{user_id}")
            
            if state_data:
                state = json.loads(state_data)
            else:
                # Stato iniziale per nuovo utente
                state = {
                    "trust_level": 0.2,
                    "emotional_depth": 0.2,
                    "attachment_risk": 0.0,
                    "relationship_history": {
                        "first_interaction": datetime.now().isoformat(),
                        "total_messages": 0,
                        "emotional_variance": 0.0,
                        "trust_trend": 0.0,
                        "last_emotional_state": "neutral",
                        "last_interaction": datetime.now().isoformat()
                    },
                    "emotional_timeline": [],
                    "trust_evolution": []
                }
                
                # Salva stato iniziale
                await self._save_state(user_id, state)
            
            return state
            
        except Exception as e:
            log("RELATIONAL_STATE_LOAD_ERROR", error=str(e), user_id=user_id)
            return {}
    
    async def update_state(self, user_id: str, emotion_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aggiorna stato relazionale con history tracking
        
        Args:
            user_id: ID utente
            emotion_data: Dati emotivi
            
        Returns:
            Stato aggiornato
        """
        try:
            state = await self.load_state(user_id)
            
            # Salva trust precedente per trend
            old_trust = state["trust_level"]
            
            # Aggiorna metriche base
            state["trust_level"] = min(1.0, state["trust_level"] + 0.01)
            state["emotional_depth"] = min(1.0, emotion_data.get("intensity", 0.3))
            
            # Monitoraggio rischio dipendenza
            if emotion_data.get("vulnerability", 0) > 0.7:
                state["attachment_risk"] = min(1.0, state["attachment_risk"] + 0.05)
            
            # Aggiorna relationship history
            history = state["relationship_history"]
            history["total_messages"] += 1
            history["last_interaction"] = datetime.now().isoformat()
            history["last_emotional_state"] = emotion_data.get("emotion", "neutral")
            
            # Calcola trust trend
            trust_change = state["trust_level"] - old_trust
            history["trust_trend"] = self._calculate_trend(state.get("trust_evolution", []), trust_change)
            
            # Aggiungi timeline emotiva
            timeline_entry = {
                "timestamp": datetime.now().isoformat(),
                "emotion": emotion_data.get("emotion", "neutral"),
                "intensity": emotion_data.get("intensity", 0.3),
                "trust_level": state["trust_level"]
            }
            
            state["emotional_timeline"].append(timeline_entry)
            
            # Mantieni solo ultimi 100 eventi
            if len(state["emotional_timeline"]) > 100:
                state["emotional_timeline"] = state["emotional_timeline"][-100:]
            
            # Aggiungi trust evolution
            state["trust_evolution"].append({
                "timestamp": datetime.now().isoformat(),
                "trust_level": state["trust_level"]
            })
            
            # Mantieni solo ultimi 50 trust points
            if len(state["trust_evolution"]) > 50:
                state["trust_evolution"] = state["trust_evolution"][-50:]
            
            # Calcola emotional variance
            history["emotional_variance"] = self._calculate_emotional_variance(state["emotional_timeline"])
            
            # Salva stato aggiornato
            await self._save_state(user_id, state)
            
            log("RELATIONAL_UPDATE", 
                user_id=user_id,
                trust=round(state["trust_level"], 3),
                depth=round(state["emotional_depth"], 3),
                messages=history["total_messages"],
                variance=round(history["emotional_variance"], 3))
            
            return state
            
        except Exception as e:
            log("RELATIONAL_STATE_UPDATE_ERROR", error=str(e), user_id=user_id)
            return {}
    
    async def _save_state(self, user_id: str, state: Dict[str, Any]) -> bool:
        """
        Salva stato relazionale persistente
        
        Args:
            user_id: ID utente
            state: Stato da salvare
            
        Returns:
            Successo salvataggio
        """
        try:
            await storage.set(f"relational_state:{user_id}", json.dumps(state))
            return True
        except Exception as e:
            log("RELATIONAL_STATE_SAVE_ERROR", error=str(e), user_id=user_id)
            return False
    
    def _calculate_trend(self, evolution: list, current_change: float) -> float:
        """
        Calcola trend basato su evoluzione storica
        
        Args:
            evolution: Lista evoluzione trust
            current_change: Cambiamento attuale
            
        Returns:
            Trend value
        """
        if len(evolution) < 5:
            return current_change
        
        # Media ultimi cambiamenti
        recent_changes = []
        for i in range(1, min(6, len(evolution))):
            change = evolution[-i]["trust_level"] - evolution[-i-1]["trust_level"]
            recent_changes.append(change)
        
        return sum(recent_changes) / len(recent_changes)
    
    def _calculate_emotional_variance(self, timeline: list) -> float:
        """
        Calcola varianza emotiva dalla timeline
        
        Args:
            timeline: Timeline emotiva
            
        Returns:
            Varianza emotiva
        """
        if len(timeline) < 2:
            return 0.0
        
        # Estrai intensità emotive
        intensities = [entry["intensity"] for entry in timeline[-20:]]  # Ultimi 20
        
        if len(intensities) < 2:
            return 0.0
        
        # Calcola varianza
        mean_intensity = sum(intensities) / len(intensities)
        variance = sum((x - mean_intensity) ** 2 for x in intensities) / len(intensities)
        
        return variance
    
    async def get_state_summary(self, user_id: str) -> Dict[str, Any]:
        """
        Ottieni riepilogo stato relazionale completo
        
        Args:
            user_id: ID utente
            
        Returns:
            Riepilogo stato
        """
        try:
            state = await self.load_state(user_id)
            
            if not state:
                return {}
            
            return {
                "trust_level": round(state["trust_level"], 3),
                "emotional_depth": round(state["emotional_depth"], 3),
                "attachment_risk": round(state["attachment_risk"], 3),
                "relationship_stage": self._get_relationship_stage(state),
                "total_messages": state["relationship_history"]["total_messages"],
                "emotional_variance": round(state["relationship_history"]["emotional_variance"], 3),
                "trust_trend": round(state["relationship_history"]["trust_trend"], 3),
                "last_emotion": state["relationship_history"]["last_emotional_state"],
                "days_since_first": self._calculate_days_since(state["relationship_history"]["first_interaction"])
            }
            
        except Exception as e:
            log("RELATIONAL_SUMMARY_ERROR", error=str(e), user_id=user_id)
            return {}
    
    def _get_relationship_stage(self, state: Dict[str, Any]) -> str:
        """
        Determina fase relazionale basata su stato completo
        
        Args:
            state: Stato relazionale
            
        Returns:
            Fase relazionale
        """
        trust = state["trust_level"]
        depth = state["emotional_depth"]
        risk = state["attachment_risk"]
        messages = state["relationship_history"]["total_messages"]
        
        if messages < 5:
            return "initial"
        elif trust < 0.4:
            return "building"
        elif trust < 0.7 and depth < 0.6:
            return "developing"
        elif trust >= 0.7 and depth >= 0.6 and risk < 0.6:
            return "mature"
        else:
            return "balanced"
    
    def _calculate_days_since(self, first_interaction: str) -> int:
        """
        Calcola giorni dalla prima interazione
        
        Args:
            first_interaction: Data prima interazione
            
        Returns:
            Giorni trascorsi
        """
        try:
            first_date = datetime.fromisoformat(first_interaction.replace('Z', '+00:00'))
            days = (datetime.now() - first_date).days
            return max(0, days)
        except:
            return 0

# Istanza globale
relational_state = RelationalState()
