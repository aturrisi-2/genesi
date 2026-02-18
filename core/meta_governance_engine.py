"""
Meta-Governance Engine - Sistema di sovragovernanza per Genesi
Monitora qualità epistemica, banalità, drift filosofico e propone micro-shift.
"""

import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
import re

from core.constitution import GenesisConstitution


class MetaGovernanceEngine:
    """
    Motore di meta-governanza per validare e guidare l'evoluzione del sistema.
    Mantiene stato in memoria, nessuna persistenza su disco.
    """
    
    def __init__(self):
        """Inizializza il motore di meta-governanza."""
        # Strutture dati interne
        self._epistemic_quality_history: List[float] = []
        self._banality_history: List[float] = []
        self._drift_snapshots: List[Dict[str, Any]] = []
        self._proposed_shifts: List[Dict[str, Any]] = []
        self._rejected_shifts: List[Dict[str, Any]] = []
        
        # Validazione costituzione
        try:
            GenesisConstitution.get_principles()
        except Exception as e:
            raise RuntimeError(f"Failed to load GenesisConstitution: {e}")
        
        print("META_GOVERNANCE_ENGINE_INITIALIZED")
    
    async def analyze_epistemic_quality(self, message: str, response: str) -> float:
        """
        Calcola punteggio qualità epistemica basato su euristiche.
        
        Args:
            message: Messaggio dell'utente
            response: Risposta del sistema
            
        Returns:
            float: Punteggio 0.0-1.0
        """
        score = 0.0
        
        # Lunghezza risposta (30%)
        response_len = len(response.split())
        if response_len >= 10:
            score += 0.3
        elif response_len >= 5:
            score += 0.15
        
        # Presenza domande aperte (40%)
        open_questions = len(re.findall(r'\b(chi|cosa|come|perché|quando|dove|per)\b', response.lower()))
        if open_questions >= 1:
            score += 0.4
        elif open_questions >= 2:
            score += 0.3
        
        # Varietà lessicale (30%)
        words = response.lower().split()
        unique_words = len(set(words))
        if len(words) > 0:
            variety_ratio = unique_words / len(words)
            score += variety_ratio * 0.3
        
        # Normalizza e mantieni storia
        score = min(1.0, score)
        self._epistemic_quality_history.append(score)
        if len(self._epistemic_quality_history) > 50:
            self._epistemic_quality_history.pop(0)
        
        print(f"META_EPISTEMIC_QUALITY score={score:.3f}")
        return score
    
    async def analyze_banality(self, message: str, response: str) -> float:
        """
        Calcola punteggio di banalità della risposta.
        
        Args:
            message: Messaggio dell'utente
            response: Risposta del sistema
            
        Returns:
            float: Punteggio 0.0-1.0
        """
        score = 0.0
        
        # Risposte molto corte (40%)
        response_len = len(response.split())
        if response_len <= 3:
            score += 0.4
        elif response_len <= 5:
            score += 0.2
        
        # Pattern ripetitivi (30%)
        words = response.lower().split()
        if len(words) > 0:
            repeated_words = len(words) - len(set(words))
            repetition_ratio = repeated_words / len(words)
            score += repetition_ratio * 0.3
        
        # Assenza elaborazione (30%)
        generic_phrases = ["ok", "va bene", "certo", "capisco", "intendo"]
        generic_count = sum(1 for phrase in generic_phrases if phrase in response.lower())
        if generic_count >= 2:
            score += 0.3
        elif generic_count >= 1:
            score += 0.15
        
        # Normalizza e mantieni storia
        score = min(1.0, score)
        self._banality_history.append(score)
        if len(self._banality_history) > 50:
            self._banality_history.pop(0)
        
        print(f"META_BANALITY_SCORE score={score:.3f}")
        return score
    
    async def detect_drift(self, current_tuning_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Rileva drift rispetto agli ultimi snapshot.
        
        Args:
            current_tuning_params: Parametri correnti di tuning
            
        Returns:
            Dict: Informazioni sul drift rilevato
        """
        if not self._drift_snapshots:
            self._drift_snapshots.append({
                "params": current_tuning_params.copy(),
                "timestamp": datetime.now().isoformat()
            })
            return {"drift_detected": False, "drift_magnitude": 0.0, "drifted_params": []}
        
        last_snapshot = self._drift_snapshots[-1]["params"]
        drifted_params = []
        total_drift = 0.0
        param_count = 0
        
        for param, current_value in current_tuning_params.items():
            if param in last_snapshot and isinstance(current_value, (int, float)):
                last_value = last_snapshot[param]
                if isinstance(last_value, (int, float)):
                    drift = abs(current_value - last_value)
                    total_drift += drift
                    param_count += 1
                    
                    # Soglia drift per parametro
                    if drift > 0.1:
                        drifted_params.append(param)
        
        # Calcola magnitudine media
        drift_magnitude = total_drift / param_count if param_count > 0 else 0.0
        drift_detected = len(drifted_params) > 0 and drift_magnitude > 0.05
        
        # Aggiorna snapshot
        self._drift_snapshots.append({
            "params": current_tuning_params.copy(),
            "timestamp": datetime.now().isoformat()
        })
        if len(self._drift_snapshots) > 10:
            self._drift_snapshots.pop(0)
        
        print(f"META_DRIFT_DETECTED magnitude={drift_magnitude:.3f} params={drifted_params}")
        return {
            "drift_detected": drift_detected,
            "drift_magnitude": drift_magnitude,
            "drifted_params": drifted_params
        }
    
    async def propose_micro_shift(self, reason: str, target_param: str, delta: float) -> Dict[str, Any]:
        """
        Propone micro-shift validato contro costituzione.
        
        Args:
            reason: Motivazione dello shift
            target_param: Parametro target
            delta: Variazione proposta
            
        Returns:
            Dict: Proposta di shift o {} se rifiutata
        """
        # Validazione costituzionale
        is_valid, violations = GenesisConstitution.validate_against({target_param: delta})
        
        if not is_valid:
            print(f"META_SHIFT_REJECTED_BY_CONSTITUTION param={target_param}")
            self._rejected_shifts.append({
                "reason": reason,
                "target_param": target_param,
                "delta": delta,
                "violations": violations,
                "timestamp": datetime.now().isoformat()
            })
            return {}
        
        # Crea proposta
        proposal = {
            "id": str(uuid.uuid4()),
            "reason": reason,
            "target_param": target_param,
            "delta": delta,
            "timestamp": datetime.now().isoformat(),
            "status": "pending"
        }
        
        self._proposed_shifts.append(proposal)
        print(f"META_SHIFT_PROPOSED id={proposal['id']} param={target_param} delta={delta}")
        return proposal
    
    async def evaluate_pending_shifts(self, current_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Valuta shift pending contro parametri correnti.
        
        Args:
            current_params: Parametri correnti
            
        Returns:
            List[Dict]: Shift approvati
        """
        approved_shifts = []
        
        for shift in self._proposed_shifts:
            if shift["status"] != "pending":
                continue
            
            target_param = shift["target_param"]
            delta = shift["delta"]
            
            if target_param in current_params:
                current_value = current_params[target_param]
                proposed_value = current_value + delta
                
                # Validazione contro hard constraints
                is_valid, violations = GenesisConstitution.validate_against({target_param: proposed_value})
                
                if is_valid:
                    shift["status"] = "approved"
                    approved_shifts.append(shift)
                    print(f"META_SHIFT_EVALUATED id={shift['id']} status=approved")
                else:
                    shift["status"] = "rejected"
                    print(f"META_SHIFT_EVALUATED id={shift['id']} status=rejected")
        
        return approved_shifts
    
    def get_governance_summary(self) -> Dict[str, Any]:
        """
        Ritorna snapshot dello stato di governance.
        
        Returns:
            Dict: Sommario stato governance
        """
        avg_epistemic = sum(self._epistemic_quality_history) / len(self._epistemic_quality_history) if self._epistemic_quality_history else 0.0
        avg_banality = sum(self._banality_history) / len(self._banality_history) if self._banality_history else 0.0
        
        last_drift = self._drift_snapshots[-1] if self._drift_snapshots else None
        pending_count = len([s for s in self._proposed_shifts if s["status"] == "pending"])
        approved_count = len([s for s in self._proposed_shifts if s["status"] == "approved"])
        rejected_count = len(self._rejected_shifts)
        
        return {
            "avg_epistemic_quality": avg_epistemic,
            "avg_banality": avg_banality,
            "last_drift": last_drift,
            "pending_shifts": pending_count,
            "approved_shifts": approved_count,
            "rejected_shifts": rejected_count
        }
