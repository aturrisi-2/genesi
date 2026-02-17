"""
Genesi Lab v1 - Minimal Evolution Supervisor Engine
Sistema minimale di auto-evoluzione deterministica basata su massive training reports
"""

import json
import glob
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# LAB ONLY: Import for snapshot management
import sys
sys.path.append('.')
from core.evolution_state_manager import get_evolution_state_manager

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MinimalEvolutionV1:
    """
    Sistema minimale di auto-evoluzione v1.
    
    Logica deterministica e trasparente basata su regole fisse.
    Niente AI heuristics, randomness o machine learning.
    """
    
    def __init__(self):
        """Inizializza il sistema di evoluzione minimale."""
        self.lab_dir = Path("lab")
        self.state_manager = get_evolution_state_manager()
        
    def run_minimal_evolution(self) -> bool:
        """
        Esegue la logica di auto-evoluzione minimale v1.
        
        Returns:
            bool: True se l'evoluzione è stata applicata, False altrimenti
        """
        try:
            # A. Caricamento report dinamico
            report_file = self._find_latest_report()
            if not report_file:
                logger.info("MINIMAL_EVOLUTION_NO_REPORTS - No massive training reports found")
                return False
            
            logger.info(f"MINIMAL_EVOLUTION_REPORT_LOADED - {report_file}")
            report = self._load_report(report_file)
            
            # B. Estrai metriche
            metrics = report.get("metrics", {})
            total_messages = metrics.get("total_messages", 0)
            success_count = metrics.get("success_count", 0)
            supportive_count = metrics.get("supportive_count", 0)
            confrontational_count = metrics.get("confrontational_count", 0)
            repetition_detected = metrics.get("repetition_detected", 0)
            avg_response_time = metrics.get("avg_response_time", 0.0)
            
            # Calcola success rate
            success_rate = (success_count / total_messages * 100) if total_messages > 0 else 0.0
            
            # C. Regole di sicurezza
            if success_rate < 95:
                logger.warning("MINIMAL_EVOLUTION_BLOCKED_LOW_SUCCESS - Success rate below 95%")
                return False
            
            if avg_response_time > 4:
                logger.warning("MINIMAL_EVOLUTION_BLOCKED_SLOW_RESPONSE - Average response time above 4s")
                return False
            
            # D. Calcolo rapporti
            if total_messages == 0:
                logger.warning("MINIMAL_EVOLUTION_BLOCKED_NO_MESSAGES - No messages in report")
                return False
                
            support_ratio = supportive_count / total_messages
            confront_ratio = confrontational_count / total_messages
            
            # E. Carica stato corrente e prepara modifiche
            current_state = self.state_manager.load_current_state()
            parameters = current_state["parameters"].copy()
            
            changes_made = False
            
            # F. Regole di modifica parametri
            if support_ratio < 0.05:
                parameters["supportive_intensity"] += 0.05
                changes_made = True
                logger.info(f"MINIMAL_EVOLUTION_RULE - support_ratio {support_ratio:.3f} < 0.05, increasing supportive_intensity")
            
            if support_ratio > 0.25:
                parameters["supportive_intensity"] -= 0.05
                changes_made = True
                logger.info(f"MINIMAL_EVOLUTION_RULE - support_ratio {support_ratio:.3f} > 0.25, decreasing supportive_intensity")
            
            if confront_ratio > 0.20:
                parameters["confrontational_intensity"] -= 0.05
                changes_made = True
                logger.info(f"MINIMAL_EVOLUTION_RULE - confront_ratio {confront_ratio:.3f} > 0.20, decreasing confrontational_intensity")
            
            if repetition_detected > 2:
                parameters["repetition_penalty_weight"] += 0.1
                changes_made = True
                logger.info(f"MINIMAL_EVOLUTION_RULE - repetition_detected {repetition_detected} > 2, increasing repetition_penalty_weight")
            
            # G. Clamp valori
            parameters["supportive_intensity"] = max(0.2, min(0.8, parameters["supportive_intensity"]))
            parameters["confrontational_intensity"] = max(0.2, min(0.8, parameters["confrontational_intensity"]))
            parameters["repetition_penalty_weight"] = max(0.8, min(1.5, parameters["repetition_penalty_weight"]))
            
            # H. Applicazione controllata
            if not changes_made:
                logger.info("MINIMAL_EVOLUTION_NO_CHANGE - No parameter changes needed")
                return False
            
            # Applica le modifiche
            return self._apply_evolution_changes(current_state, parameters)
            
        except Exception as e:
            logger.error(f"MINIMAL_EVOLUTION_ERROR - {e}")
            return False
    
    def _find_latest_report(self) -> Optional[str]:
        """
        Trova il report più recente matching pattern massive_training_auth_report_*.json
        
        Returns:
            Optional[str]: Path del report più recente o None
        """
        try:
            pattern = str(self.lab_dir / "massive_training_auth_report_*.json")
            reports = glob.glob(pattern)
            
            if not reports:
                return None
            
            # Ordina per timestamp nel filename (più recente)
            reports.sort(reverse=True)
            return reports[0]
            
        except Exception as e:
            logger.error(f"Failed to find reports: {e}")
            return None
    
    def _load_report(self, report_file: str) -> Dict[str, Any]:
        """
        Carica report da file.
        
        Args:
            report_file: Path del file report
            
        Returns:
            Dict[str, Any]: Report caricato
        """
        try:
            with open(report_file, 'r', encoding='utf-8-sig') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load report {report_file}: {e}")
            return {}
    
    def _apply_evolution_changes(self, current_state: Dict[str, Any], new_parameters: Dict[str, Any]) -> bool:
        """
        Applica le modifiche evolutive in modo controllato.
        
        Args:
            current_state: Stato corrente
            new_parameters: Nuovi parametri da applicare
            
        Returns:
            bool: True se applicata con successo
        """
        try:
            # Incrementa evolution count
            current_state["evolution_count"] = current_state.get("evolution_count", 0) + 1
            current_state["timestamp"] = datetime.now().isoformat()
            
            # Aggiorna parametri
            current_state["parameters"] = new_parameters
            
            # Salva snapshot
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            snapshot_file = f"data/tuning_snapshots/snapshot_{timestamp}.json"
            
            # Crea directory snapshots se non esiste
            Path("data/tuning_snapshots").mkdir(parents=True, exist_ok=True)
            
            snapshot = {
                "timestamp": timestamp,
                "evolution_count": current_state["evolution_count"],
                "previous_parameters": current_state["parameters"],
                "report_used": "massive_training_auth_report_latest"
            }
            
            with open(snapshot_file, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, indent=2)
            
            # Salva stato corrente
            if self.state_manager.save_current_state(current_state):
                logger.info("MINIMAL_EVOLUTION_APPLIED - Evolution applied successfully")
                logger.info(f"Parameters updated: {new_parameters}")
                logger.info(f"Snapshot saved: {snapshot_file}")
                return True
            else:
                logger.error("MINIMAL_EVOLUTION_SAVE_FAILED - Failed to save current state")
                return False
                
        except Exception as e:
            logger.error(f"MINIMAL_EVOLUTION_APPLY_ERROR - {e}")
            return False


def run_minimal_evolution_v1():
    """
    Funzione main per eseguire MinimalEvolutionV1.
    
    Returns:
        bool: True se l'evoluzione è stata applicata con successo
    """
    evolution = MinimalEvolutionV1()
    return evolution.run_minimal_evolution()


if __name__ == "__main__":
    success = run_minimal_evolution_v1()
    if success:
        print("✅ Minimal Evolution V1 applied successfully")
    else:
        print("ℹ️ Minimal Evolution V1 - No changes applied")
