"""
Evolution State Manager - Sistema Transazionale Robusto
Gestisce snapshot versionati, apply atomico e rollback reale per auto-evoluzione
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import shutil
import logging

logger = logging.getLogger(__name__)

class EvolutionStateManager:
    """Gestore transazionale per stato evolutivo con snapshot versionati."""
    
    def __init__(self, base_dir: str = "data/evolution"):
        self.base_dir = Path(base_dir)
        self.current_state_file = self.base_dir / "current_state.json"
        self.snapshots_dir = self.base_dir / "snapshots"
        self.evolution_log_file = self.base_dir / "evolution_log.json"
        
        # Assicura che le directory esistano
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        
        # Stato iniziale se non esiste
        self._ensure_initial_state()
    
    def _ensure_initial_state(self):
        """Crea stato iniziale se current_state.json non esiste."""
        if not self.current_state_file.exists():
            initial_state = {
                "version": "1.0.0",
                "timestamp": datetime.now().isoformat(),
                "parameters": {
                    "supportive_intensity": 0.5,
                    "attuned_intensity": 0.5,
                    "confrontational_intensity": 0.5,
                    "max_questions_per_response": 1,
                    "repetition_penalty_weight": 1.0
                },
                "last_snapshot": None,
                "evolution_count": 0,
                # 🔵 META-GOVERNANCE EMA STABILITY
                "stability_score": 1.0,
                "ema_stability": 1.0,
                "rollback_streak": 0,
                "apply_streak": 0,
                "hard_violation_streak": 0,
                "consecutive_valid_reports": 0,  # 🔵 FASE 3 - Tracciamento report validazione
                "evolution_health": "stable",
                "auto_evolution_locked": False,
                # 🔵 HARDENING STEP C.1 - POST-UNLOCK ANTI-RIMBALZO PROTECTION
                "post_unlock_observation": False,
                "post_unlock_remaining_reports": 0
            }
            self.save_current_state(initial_state)
            logger.info("🆕 Initial evolution state created")
        else:
            # 🔵 Assicura che campi EMA esistano in stato esistente
            self._ensure_ema_fields_exist()
    
    def load_current_state(self) -> Dict[str, Any]:
        """Carica stato corrente da file."""
        try:
            # Assicura che la directory esista
            os.makedirs(self.current_state_file.parent, exist_ok=True)
            
            with open(self.current_state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            return state
        except Exception as e:
            logger.error(f"❌ Failed to load current state: {e}")
            # Fallback to initial state
            return self._get_fallback_state()
    
    def _get_fallback_state(self) -> Dict[str, Any]:
        """Stato di fallback in caso di errore."""
        fallback_state = {
            "version": "1.0.0",
            "timestamp": datetime.now().isoformat(),
            "parameters": {
                "supportive_intensity": 0.5,
                "attuned_intensity": 0.5,
                "confrontational_intensity": 0.5,
                "max_questions_per_response": 1,
                "repetition_penalty_weight": 1.0
            },
            "last_snapshot": None,
            "evolution_count": 0,
            # 🔵 META-GOVERNANCE EMA STABILITY
            "stability_score": 1.0,
            "ema_stability": 1.0,
            "rollback_streak": 0,
            "apply_streak": 0,
            "hard_violation_streak": 0,
            "consecutive_valid_reports": 0,  # 🔵 FASE 3 - Tracciamento report validazione
            "evolution_health": "stable",
            "auto_evolution_locked": False,
            # 🔵 HARDENING STEP C.1 - POST-UNLOCK ANTI-RIMBALZO PROTECTION
            "post_unlock_observation": False,
            "post_unlock_remaining_reports": 0
        }
        return fallback_state
    
    def _ensure_ema_fields_exist(self):
        """Assicura che campi EMA esistano in stato esistente."""
        try:
            state = self.load_current_state()
            updated = False
            
            # Campi EMA richiesti
            ema_fields = {
                "stability_score": 1.0,
                "ema_stability": 1.0,
                "rollback_streak": 0,
                "apply_streak": 0,
                "hard_violation_streak": 0,
                "consecutive_valid_reports": 0,  # 🔵 FASE 3 - Tracciamento report validazione
                "evolution_health": "stable",
                "auto_evolution_locked": False,
                # 🔵 HARDENING STEP C.1 - POST-UNLOCK ANTI-RIMBALZO PROTECTION
                "post_unlock_observation": False,
                "post_unlock_remaining_reports": 0
            }
            
            for field, default_value in ema_fields.items():
                if field not in state:
                    state[field] = default_value
                    updated = True
            
            if updated:
                self.save_current_state(state)
                logger.info("🔧 EMA fields added to existing state")
                
        except Exception as e:
            logger.error(f"❌ Failed to ensure EMA fields: {e}")
    
    def save_current_state(self, state: Dict[str, Any]) -> bool:
        """Salva stato corrente su file."""
        try:
            # Aggiorna timestamp
            state["timestamp"] = datetime.now().isoformat()
            
            # Assicura che la directory esista
            os.makedirs(self.current_state_file.parent, exist_ok=True)
            
            with open(self.current_state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"❌ Failed to save current state: {e}")
            return False
    
    def create_snapshot(self, state: Dict[str, Any]) -> Optional[str]:
        """Crea snapshot versionato dello stato."""
        try:
            # Genera version ID
            version = self._generate_version_id()
            snapshot_file = self.snapshots_dir / f"snapshot_{version}.json"
            
            # Prepara snapshot
            snapshot = {
                "version": version,
                "timestamp": datetime.now().isoformat(),
                "state": state.copy(),
                "created_by": "evolution_engine"
            }
            
            # Salva snapshot
            with open(snapshot_file, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, indent=2)
            
            print(f"SNAPSHOT_CREATED version={version}")
            logger.info(f"📸 Snapshot created: {version}")
            
            return version
        except Exception as e:
            logger.error(f"❌ Failed to create snapshot: {e}")
            return None
    
    def _generate_version_id(self) -> str:
        """Genera ID versione univoco."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Include millisecondi
        return f"v{timestamp}"
    
    def list_snapshots(self) -> List[Dict[str, Any]]:
        """Elenca tutti gli snapshot disponibili."""
        snapshots = []
        try:
            for snapshot_file in sorted(self.snapshots_dir.glob("snapshot_*.json")):
                with open(snapshot_file, 'r', encoding='utf-8') as f:
                    snapshot = json.load(f)
                snapshots.append(snapshot)
        except Exception as e:
            logger.error(f"❌ Failed to list snapshots: {e}")
        
        return snapshots
    
    def restore_last_snapshot(self) -> Optional[Dict[str, Any]]:
        """Ripristina ultimo snapshot disponibile."""
        try:
            snapshots = self.list_snapshots()
            if not snapshots:
                logger.warning("⚠️ No snapshots available for restore")
                return None
            
            # Prendi ultimo snapshot
            last_snapshot = snapshots[-1]
            restored_state = last_snapshot["state"].copy()
            
            # Salva come stato corrente
            if self.save_current_state(restored_state):
                version = last_snapshot["version"]
                print(f"STATE_ROLLED_BACK version={version}")
                logger.info(f"🔄 State restored to snapshot: {version}")
                return restored_state
            else:
                return None
                
        except Exception as e:
            logger.error(f"❌ Failed to restore snapshot: {e}")
            return None
    
    def append_evolution_log(self, entry: Dict[str, Any]) -> bool:
        """Aggiunge entry al log evolutivo."""
        try:
            # Carica log esistente
            logs = []
            if self.evolution_log_file.exists():
                with open(self.evolution_log_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            
            # Aggiungi timestamp
            entry["timestamp"] = datetime.now().isoformat()
            
            # Aggiungi entry
            logs.append(entry)
            
            # Salva log
            with open(self.evolution_log_file, 'w', encoding='utf-8') as f:
                json.dump(logs, f, indent=2)
            
            print("EVOLUTION_LOG_WRITTEN")
            logger.info(f"📝 Evolution log entry added: {entry.get('action', 'unknown')}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to write evolution log: {e}")
            return False
    
    def apply_evolution_transaction(self, current_state: Dict[str, Any], new_parameters: Dict[str, Any]) -> bool:
        """Applica transazione evolutiva atomica."""
        try:
            # A) Carica stato corrente (già fornito)
            # B) Crea snapshot
            snapshot_version = self.create_snapshot(current_state)
            if not snapshot_version:
                return False
            
            # C) Applica tuning
            updated_state = current_state.copy()
            updated_state["parameters"].update(new_parameters)
            updated_state["evolution_count"] = updated_state.get("evolution_count", 0) + 1
            updated_state["last_snapshot"] = snapshot_version
            
            # D) Salva stato corrente
            if not self.save_current_state(updated_state):
                # Rollback automatico su fallimento
                self.restore_last_snapshot()
                return False
            
            # E) Scrivi log
            log_entry = {
                "action": "apply",
                "snapshot_version": snapshot_version,
                "previous_parameters": current_state["parameters"],
                "new_parameters": new_parameters,
                "evolution_count": updated_state["evolution_count"]
            }
            self.append_evolution_log(log_entry)
            
            print(f"STATE_APPLIED version={snapshot_version}")
            logger.info(f"✅ Evolution applied: {snapshot_version}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Evolution transaction failed: {e}")
            # Rollback automatico
            self.restore_last_snapshot()
            return False
    
    def rollback_evolution_transaction(self) -> bool:
        """Esegue transazione di rollback."""
        try:
            # A) Ripristina ultimo snapshot
            restored_state = self.restore_last_snapshot()
            if not restored_state:
                return False
            
            # B) Salva come stato corrente (già fatto in restore)
            # C) Scrivi log
            log_entry = {
                "action": "rollback",
                "restored_to": restored_state.get("last_snapshot", "unknown"),
                "parameters": restored_state["parameters"]
            }
            self.append_evolution_log(log_entry)
            
            logger.info("🔄 Rollback transaction completed")
            return True
            
        except Exception as e:
            logger.error(f"❌ Rollback transaction failed: {e}")
            return False
    
    # 🔵 META-GOVERNANCE EMA STABILITY METHODS
    
    def calculate_stability_score(self, report_metrics: Dict[str, Any], has_hard_violation: bool, is_rollback_decision: bool) -> float:
        """Calcola stability score per report."""
        try:
            success_rate = report_metrics.get("success_rate", 0.0)
            
            # Calcolo stability score
            stability_score = success_rate
            if has_hard_violation:
                stability_score -= 0.5
            if is_rollback_decision:
                stability_score -= 0.3
            
            # Clamp 0-1
            stability_score = max(0.0, min(1.0, stability_score))
            
            print(f"STABILITY_SCORE_CALCULATED value={stability_score:.3f}")
            logger.info(f"📊 Stability score calculated: {stability_score:.3f}")
            
            return stability_score
            
        except Exception as e:
            logger.error(f"❌ Failed to calculate stability score: {e}")
            return 0.5  # Default neutro
    
    def update_ema_stability(self, current_state: Dict[str, Any], stability_score: float) -> Dict[str, Any]:
        """Aggiorna EMA stability con alpha=0.4."""
        try:
            alpha = 0.4
            old_ema = current_state.get("ema_stability", 1.0)
            new_ema = alpha * stability_score + (1 - alpha) * old_ema
            
            # Clamp 0-1
            new_ema = max(0.0, min(1.0, new_ema))
            
            # Aggiorna stato
            updated_state = current_state.copy()
            updated_state["ema_stability"] = new_ema
            updated_state["stability_score"] = stability_score
            
            print(f"EMA_UPDATED old={old_ema:.3f} new={new_ema:.3f}")
            logger.info(f"📈 EMA updated: {old_ema:.3f} → {new_ema:.3f}")
            
            return updated_state
            
        except Exception as e:
            logger.error(f"❌ Failed to update EMA: {e}")
            return current_state
    
    def classify_evolution_health(self, ema_stability: float) -> str:
        """Classifica evolution health basato su EMA."""
        if ema_stability > 0.8:
            health = "stable"
        elif ema_stability > 0.6:
            health = "adaptive"
        elif ema_stability > 0.4:
            health = "unstable"
        else:
            health = "critical"
        
        print(f"EVOLUTION_HEALTH status={health}")
        logger.info(f"🏥 Evolution health: {health}")
        
        return health
    
    def update_streaks(self, current_state: Dict[str, Any], has_hard_violation: bool, is_rollback_decision: bool, is_apply_decision: bool) -> Dict[str, Any]:
        """Aggiorna streak counters."""
        try:
            updated_state = current_state.copy()
            
            # Reset streaks appropriati
            if is_apply_decision:
                updated_state["apply_streak"] = updated_state.get("apply_streak", 0) + 1
                updated_state["rollback_streak"] = 0
            elif is_rollback_decision:
                updated_state["rollback_streak"] = updated_state.get("rollback_streak", 0) + 1
                updated_state["apply_streak"] = 0
            
            if has_hard_violation:
                updated_state["hard_violation_streak"] = updated_state.get("hard_violation_streak", 0) + 1
            else:
                # Reset hard violation streak solo se non c'è violazione
                if updated_state.get("hard_violation_streak", 0) > 0:
                    updated_state["hard_violation_streak"] = 0
            
            return updated_state
            
        except Exception as e:
            logger.error(f"❌ Failed to update streaks: {e}")
            return current_state
    
    def evaluate_lock_status(self, current_state: Dict[str, Any]) -> tuple[bool, str]:
        """Valuta se l'evoluzione deve essere locked."""
        try:
            hard_violation_streak = current_state.get("hard_violation_streak", 0)
            ema_stability = current_state.get("ema_stability", 1.0)
            currently_locked = current_state.get("auto_evolution_locked", False)
            post_unlock_observation = current_state.get("post_unlock_observation", False)
            post_unlock_remaining_reports = current_state.get("post_unlock_remaining_reports", 0)
            
            # 🔴 Lock automatico (invariato)
            if not currently_locked:
                if hard_violation_streak >= 2 or ema_stability < 0.4:
                    return True, f"hard_violation_streak={hard_violation_streak} OR ema_stability={ema_stability:.3f}"
            
            # 🔵 HARDENING STEP C.1 - POST-UNLOCK ANTI-RIMBALZO PROTECTION
            if post_unlock_observation and post_unlock_remaining_reports > 0:
                # Durante observation: permettere lock solo per hard_violation_streak >= 2
                if hard_violation_streak >= 2:
                    return True, f"hard_violation_during_observation_streak={hard_violation_streak}"
                # Altrimenti non permettere lock
                return currently_locked, "post_unlock_observation_active"
            
            # 🔵 FASE 2 - NUOVA LOGICA DI UNLOCK MATEMATICA
            if currently_locked:
                consecutive_valid_reports = current_state.get("consecutive_valid_reports", 0)
                
                # UNLOCK se e solo se: ema_stability > 0.6 AND consecutive_valid_reports >= 3
                if ema_stability > 0.6 and consecutive_valid_reports >= 3:
                    return False, "ema_recovered_and_3_valid_reports"
            
            # Mantieni stato corrente
            return currently_locked, "no_change"
            
        except Exception as e:
            logger.error(f"❌ Failed to evaluate lock status: {e}")
            return True, "error_fallback_locked"
    
    def apply_meta_governance(self, report_metrics: Dict[str, Any], has_hard_violation: bool, is_rollback_decision: bool, is_apply_decision: bool) -> Dict[str, Any]:
        """Applica meta-governance completa su report."""
        try:
            # 1. Carica stato corrente
            current_state = self.load_current_state()
            
            # 2. Calcola stability score
            stability_score = self.calculate_stability_score(report_metrics, has_hard_violation, is_rollback_decision)
            
            # 3. Aggiorna EMA
            current_state = self.update_ema_stability(current_state, stability_score)
            
            # 4. Classifica health
            ema_stability = current_state.get("ema_stability", 1.0)
            health = self.classify_evolution_health(ema_stability)
            current_state["evolution_health"] = health
            
            # 5. Aggiorna streaks
            current_state = self.update_streaks(current_state, has_hard_violation, is_rollback_decision, is_apply_decision)
            
            # 🔵 FASE 3 - AGGIORNA CONSECUTIVE VALID REPORTS
            current_state = self.update_consecutive_valid_reports(current_state, report_metrics)
            
            # 6. Valuta lock status
            should_lock, reason = self.evaluate_lock_status(current_state)
            currently_locked = current_state.get("auto_evolution_locked", False)
            
            if should_lock and not currently_locked:
                current_state["auto_evolution_locked"] = True
                print(f"EVOLUTION_LOCKED reason={reason}")
                logger.warning(f"🔒 Evolution locked: {reason}")
            elif not should_lock and currently_locked:
                current_state["auto_evolution_locked"] = False
                # 🔵 FASE 5 - PROTEZIONE ANTI-RIMBALZO
                current_state["hard_violation_streak"] = 0
                # 🔵 HARDENING STEP C.1 - ATTIVA POST-UNLOCK OBSERVATION
                current_state["post_unlock_observation"] = True
                current_state["post_unlock_remaining_reports"] = 2
                print("EVOLUTION_UNLOCKED reason=ema_recovered_and_3_valid_reports")
                print("POST_UNLOCK_OBSERVATION_STARTED")
                print("POST_UNLOCK_OBSERVATION_REMAINING=2")
                logger.info("🔓 Evolution unlocked: EMA recovered and 3 valid reports")
                logger.info("🔍 Post-unlock observation started: 2 reports remaining")
            
            # 🔵 HARDENING STEP C.1 - GESTIONE OBSERVATION
            if current_state.get("post_unlock_observation", False):
                post_unlock_remaining_reports = current_state.get("post_unlock_remaining_reports", 0)
                
                # Se report valido, decrementa remaining
                if self._is_report_valid(report_metrics):
                    current_state["post_unlock_remaining_reports"] = post_unlock_remaining_reports - 1
                    print(f"POST_UNLOCK_OBSERVATION_REMAINING={post_unlock_remaining_reports - 1}")
                    
                    # Se arrivati a 0, termina observation
                    if current_state["post_unlock_remaining_reports"] <= 0:
                        current_state["post_unlock_observation"] = False
                        current_state["post_unlock_remaining_reports"] = 0
                        print("POST_UNLOCK_OBSERVATION_ENDED")
                        logger.info("🔍 Post-unlock observation ended")
            
            # 7. Salva stato aggiornato
            self.save_current_state(current_state)
            
            return current_state
            
        except Exception as e:
            logger.error(f"❌ Failed to apply meta-governance: {e}")
            return self.load_current_state()
    
    # 🔵 FASE 3 - NUOVO METODO PER CONSECUTIVE VALID REPORTS
    def update_consecutive_valid_reports(self, current_state: Dict[str, Any], report_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Aggiorna consecutive_valid_reports basato su validazione report."""
        try:
            # Estrai metriche dal report
            within_target_ranges = report_metrics.get("within_target_ranges", False)
            success_rate = report_metrics.get("success_rate", 0.0)
            error_rate = report_metrics.get("error_rate", 0.0)
            
            # 🔵 FASE 2 - LOGICA VALIDAZIONE REPORT
            is_valid_report = (
                within_target_ranges == True and
                success_rate >= 0.90 and
                error_rate <= 0.05
            )
            
            updated_state = current_state.copy()
            
            if is_valid_report:
                # Report valido - incrementa consecutivi
                updated_state["consecutive_valid_reports"] = updated_state.get("consecutive_valid_reports", 0) + 1
                logger.info(f"✅ Valid report: consecutive_valid_reports = {updated_state['consecutive_valid_reports']}")
            else:
                # Report non valido - reset consecutivi
                updated_state["consecutive_valid_reports"] = 0
                logger.info(f"❌ Invalid report: consecutive_valid_reports reset to 0")
            
            return updated_state
            
        except Exception as e:
            logger.error(f"❌ Failed to update consecutive valid reports: {e}")
            return current_state
    
    def _is_report_valid(self, report_metrics: Dict[str, Any]) -> bool:
        """Verifica se un report è valido secondo i criteri EMA."""
        try:
            within_target_ranges = report_metrics.get("within_target_ranges", False)
            success_rate = report_metrics.get("success_rate", 0.0)
            error_rate = report_metrics.get("error_rate", 1.0)
            
            # 🔵 FASE 2 - LOGICA VALIDAZIONE REPORT
            is_valid_report = (
                within_target_ranges == True and
                success_rate >= 0.90 and
                error_rate <= 0.05
            )
            
            return is_valid_report
            
        except Exception as e:
            logger.error(f"❌ Failed to validate report: {e}")
            return False

# Singleton globale
_evolution_state_manager = None

def get_evolution_state_manager() -> EvolutionStateManager:
    """Ottieni singleton EvolutionStateManager."""
    global _evolution_state_manager
    if _evolution_state_manager is None:
        _evolution_state_manager = EvolutionStateManager()
    return _evolution_state_manager
