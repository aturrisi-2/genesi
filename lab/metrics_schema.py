"""
Genesi Lab v1 - Metrics Schema
Dataclass per la valutazione qualitativa delle conversazioni
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any
import json


@dataclass
class ConversationMetrics:
    """
    Schema per le metriche di valutazione qualitativa delle conversazioni.
    
    Tutti i score sono float nel range 0-1 dove:
    - 1.0 = eccellente
    - 0.0 = molto scarso
    """
    clarity_score: float  # Chiarezza e specificità della risposta
    coherence_score: float  # Coerenza logica e consistenza
    contextual_memory_score: float  # Utilizzo corretto dei dati del profilo
    human_likeness_score: float  # Naturalità e umanità del linguaggio
    redundancy_score: float  # Basso livello di ripetizioni (inverted: 1 = no ridondanza)
    hallucination_risk: float  # Rischio di invenzioni (inverted: 1 = basso rischio)
    overall_score: float  # Score complessivo ponderato
    
    def __post_init__(self):
        """Validazione dei valori dopo l'inizializzazione"""
        for field_name, value in self.__dict__.items():
            if isinstance(value, (int, float)):
                if not 0.0 <= value <= 1.0:
                    raise ValueError(f"{field_name} must be between 0.0 and 1.0, got {value}")
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Converte la dataclass in dizionario per serializzazione JSON.
        
        Returns:
            Dict[str, Any]: Rappresentazione dizionario delle metriche
        """
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationMetrics':
        """
        Crea istanza ConversationMetrics da dizionario.
        
        Args:
            data: Dizionario con i valori delle metriche
            
        Returns:
            ConversationMetrics: Istanza della dataclass
        """
        # Filtra solo i campi attesi per evitare errori
        expected_fields = {
            'clarity_score', 'coherence_score', 'contextual_memory_score',
            'human_likeness_score', 'redundancy_score', 'hallucination_risk',
            'overall_score'
        }
        
        filtered_data = {k: v for k, v in data.items() if k in expected_fields}
        
        return cls(**filtered_data)
    
    def to_json(self) -> str:
        """
        Serializza in JSON string.
        
        Returns:
            str: JSON string delle metriche
        """
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ConversationMetrics':
        """
        Deserializza da JSON string.
        
        Args:
            json_str: JSON string delle metriche
            
        Returns:
            ConversationMetrics: Istanza della dataclass
        """
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def get_quality_level(self) -> str:
        """
        Determina il livello qualitativo basato sull'overall_score.
        
        Returns:
            str: Livello qualitativo (excellent, good, fair, poor)
        """
        if self.overall_score >= 0.8:
            return "excellent"
        elif self.overall_score >= 0.6:
            return "good"
        elif self.overall_score >= 0.4:
            return "fair"
        else:
            return "poor"
    
    def get_improvement_areas(self) -> list[str]:
        """
        Identifica aree di miglioramento basate su score < 0.6.
        
        Returns:
            list[str]: Lista delle aree che necessitano miglioramento
        """
        areas = []
        
        if self.clarity_score < 0.6:
            areas.append("clarity")
        if self.coherence_score < 0.6:
            areas.append("coherence")
        if self.contextual_memory_score < 0.6:
            areas.append("memory_usage")
        if self.human_likeness_score < 0.6:
            areas.append("naturalness")
        if self.redundancy_score < 0.6:
            areas.append("redundancy")
        if self.hallucination_risk < 0.6:
            areas.append("hallucination_risk")
        
        return areas
