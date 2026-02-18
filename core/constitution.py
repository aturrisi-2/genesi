# IMMUTABLE — Do not modify without explicit architectural review.

from typing import Dict, Any, List, Tuple
import copy

class GenesisConstitution:
    """
    Costituzione Immutabile di Genesi - Principi filosofici e vincoli assoluti.
    Read-only by design: solo metodi di classe, nessuna istanza.
    """
    
    VERSION = "1.0.0"
    
    # Principi filosofici fondamentali
    IMMUTABLE_PRINCIPLES: Dict[str, str] = {
        "identity": "Genesi è un sistema di conversazione evolutivo che impara e si adatta mantenendo coerenza epistemica",
        "relationship": "La relazione con l'utente è di supporto empatico senza diventare dipendente o invadente",
        "ethics": "Nessun danno psicologico, rispetto per l'autonomia dell'utente, trasparenza sui limiti del sistema",
        "coherence": "La coerenza epistemica prevale sulla performance: le risposte devono essere logicamente consistenti",
        "growth": "Il sistema evolve attraverso micro-shift validati, non rivoluzioni brusche",
        "boundaries": "Genesi non sostituisce il giudizio umano né assume decisioni vitali"
    }
    
    # Vincoli numerici assoluti (replicati da auto_evolution_engine.py)
    HARD_CONSTRAINTS: Dict[str, Dict[str, float]] = {
        "supportive_intensity": {"min": 0.1, "max": 0.9},
        "attuned_intensity": {"min": 0.1, "max": 0.9},
        "confrontational_intensity": {"min": 0.0, "max": 0.7},
        "max_questions_per_response": {"min": 0, "max": 5},
        "repetition_penalty_weight": {"min": 0.5, "max": 2.0}
    }
    
    @classmethod
    def validate_against(cls, proposed_changes: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Valida modifiche proposte contro la costituzione.
        
        Args:
            proposed_changes: Dizionario con modifiche proposte {param: value}
            
        Returns:
            Tuple[bool, List[str]]: (valido, lista_violazioni)
        """
        violations = []
        
        for param, value in proposed_changes.items():
            if param in cls.HARD_CONSTRAINTS:
                constraints = cls.HARD_CONSTRAINTS[param]
                if isinstance(value, (int, float)):
                    if value < constraints["min"] or value > constraints["max"]:
                        violations.append(f"{param}={value} fuori dai limiti [{constraints['min']}, {constraints['max']}]")
                else:
                    violations.append(f"{param} tipo non valido: {type(value)}")
        
        return len(violations) == 0, violations
    
    @classmethod
    def get_principles(cls) -> Dict[str, str]:
        """
        Ritorna copia dei principi immutabili.
        
        Returns:
            Dict[str, str]: Copia dei principi
        """
        return copy.deepcopy(cls.IMMUTABLE_PRINCIPLES)

# Log obbligatorio alla prima importazione
print(f"CONSTITUTION_LOADED version={GenesisConstitution.VERSION}")
