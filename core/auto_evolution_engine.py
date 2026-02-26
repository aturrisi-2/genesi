"""
AUTO EVOLUTION ENGINE - Sistema di Auto-Evoluzione Aggressiva Controllata
Monitora report Massive Training, applica AutoTuner, evolve Genesi in tempo reale
"""

import os
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from core.auto_tuner import AutoTuner
from core.llm_service import reload_tuning_state
from core.evolution_state_manager import get_evolution_state_manager

# META-GOVERNANCE EXTENSION START
from core.meta_governance_engine import MetaGovernanceEngine
from core.constitution import GenesisConstitution
# META-GOVERNANCE EXTENSION END

from core.log import log

logger = logging.getLogger(__name__)

# Limiti massimi di variazione per singolo step evolutivo
EVOLUTION_MAX_DELTA = {
    "supportive_intensity": 0.05,
    "attuned_intensity": 0.05,
    "confrontational_intensity": 0.03,  # più conservativo
    "max_questions_per_response": 0.5,
    "repetition_penalty_weight": 0.05,
}

EVOLUTION_DEFAULT_MAX_DELTA = 0.05  # fallback per parametri non listati

EVOLUTION_MIN_MESSAGES_BETWEEN_SHIFTS = 10  # minimo messaggi tra uno shift e il successivo

class ReportHandler(FileSystemEventHandler):
    """Handler per nuovi report JSON del Massive Training."""
    
    def __init__(self, evolution_engine):
        self.evolution_engine = evolution_engine
        self._processed_files = set()  # 🔵 DEDUPLICAZIONE EVENTI WINDOWS
        
    def on_created(self, event):
        """Quando viene creato un nuovo file."""
        if not event.is_directory and event.src_path.endswith('.json'):
            if 'massive_training_auth_report' in event.src_path:
                # 🔵 NORMALIZZAZIONE PATH ASSOLUTO
                import os
                raw_path = event.src_path
                normalized_path = os.path.abspath(raw_path)
                
                # 🔵 LOG PATH NORMALIZZATI
                logger.debug("WATCHDOG_EVENT_RECEIVED path=%s", raw_path)
                logger.debug("NORMALIZED_PATH path=%s", normalized_path)

                # 🔵 GUARD CLAUSE - verifica esistenza file
                if not os.path.exists(normalized_path):
                    logger.error("ERROR_INVALID_PATH %s - file does not exist", normalized_path)
                    return
                
                # 🔵 DEDUPLICAZIONE - ignora file già processati (usa path normalizzato)
                if normalized_path in self._processed_files:
                    return
                
                self._processed_files.add(normalized_path)
                
                # 🔵 DEBUG OBBLIGATORIO - report rilevato
                logger.info("REPORT_DETECTED %s", normalized_path)
                
                # 🔵 BLINDATURA THREAD + FUTURE - salva future e gestisci eccezioni
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self.evolution_engine.process_report(normalized_path),
                        self.evolution_engine.main_loop
                    )
                    
                    # Aggiungi callback per gestione risultati
                    future.add_done_callback(self._evolution_callback)
                    
                except Exception as e:
                    logger.error("EVOLUTION_EXCEPTION %s", e)

    def _evolution_callback(self, future):
        """Callback per gestire risultato evolution."""
        try:
            result = future.result()
            logger.info("EVOLUTION_COMPLETED %s", result)
        except Exception as e:
            logger.error("EVOLUTION_EXCEPTION (callback) %s", e)

class AutoEvolutionEngine:
    """Motore di auto-evoluzione controllata per Genesi."""
    
    def __init__(self, lab_dir: str = "lab"):
        self.lab_dir = Path(lab_dir)
        self.auto_tuner = AutoTuner()
        self.observer = None
        self.is_running = False
        self.main_loop = None  # 🔵 Salva loop principale FastAPI
        self.state_manager = get_evolution_state_manager()  # 🔵 TRANSAZIONALE
        
        # 🚨 VINCOLI HARD NON NEGOZIABILI
        self.HARD_CONSTRAINTS = {
            'supportive_rate_range': (0.15, 0.22),  # 15% - 22%
            'confrontational_rate_range': (0.02, 0.06),  # 2% - 6%
            'repetition_rate_max': 0.02,  # 2%
            'success_rate_min': 0.97,  # 97%
            'avg_response_time_max': 3.5  # 3.5s
        }
        
        # META-GOVERNANCE EXTENSION START
        self._meta_governance = MetaGovernanceEngine()
        logger.info("AUTO_EVOLUTION_META_GOVERNANCE_ATTACHED")
        # META-GOVERNANCE EXTENSION END
    
    def _apply_clamped_delta(self, param_name: str, current_value: float, proposed_value: float) -> float:
        """Applica max_delta e range assoluto, ritorna il valore finale clampato."""
        max_delta = EVOLUTION_MAX_DELTA.get(param_name, EVOLUTION_DEFAULT_MAX_DELTA)
        delta = proposed_value - current_value

        if abs(delta) > max_delta:
            clamped_delta = max_delta if delta > 0 else -max_delta
            logger.info("EVOLUTION_DELTA_CLAMPED param=%s requested=%.4f applied=%.4f", param_name, delta, clamped_delta)
            result = current_value + clamped_delta
        else:
            result = proposed_value

        # Clamp assoluto 0.2-0.8 per parametri comportamentali
        result = max(0.2, min(0.8, result))
        return result
    
    def _get_messages_since_last_shift(self, user_id: str) -> int:
        """Ottiene il numero di messaggi dall'ultimo shift applicato."""
        try:
            # Recupera il contatore messaggi dalla chat memory
            from core.chat_memory import ChatMemory
            chat_memory = ChatMemory()
            messages = chat_memory.get_messages(user_id, limit=1000)
            
            # Controlla se abbiamo salvato il message_count dell'ultimo shift
            last_shift_count = self.state_manager.load_current_state().get("last_shift_message_count", 0)
            current_count = len(messages)
            
            return current_count - last_shift_count
        except Exception as e:
            logger.error(f"Error getting messages since last shift: {e}")
            return 999  # fallback alto per non bloccare
    
    def _get_previous_tuning_params(self) -> Dict[str, Any]:
        """Ottiene i parametri di tuning dal precedente snapshot."""
        try:
            # Prova a ottenere dall'ultimo snapshot del meta-governance
            if hasattr(self._meta_governance, '_drift_snapshots') and len(self._meta_governance._drift_snapshots) > 1:
                # Prendi il penultimo snapshot come "previous"
                return self._meta_governance._drift_snapshots[-2]["params"]
            else:
                # Fallback: usa valori default
                return {
                    "supportive_intensity": 0.5,
                    "attuned_intensity": 0.5,
                    "confrontational_intensity": 0.5,
                    "max_questions_per_response": 1,
                    "repetition_penalty_weight": 1.0
                }
        except Exception as e:
            logger.error(f"Error getting previous tuning params: {e}")
            return {}
        
    async def start_monitoring(self):
        """Avvia monitoraggio cartella lab per nuovi report."""
        if self.is_running:
            return
            
        # 🔵 Salva loop principale FastAPI
        self.main_loop = asyncio.get_running_loop()
        
        self.is_running = True
        event_handler = ReportHandler(self)
        self.observer = Observer()
        
        # 🔵 VERIFICA MONITOR PATH ESATTO
        BASE_DIR = Path(__file__).resolve().parent.parent
        lab_path = (BASE_DIR / "lab").resolve()
        self.observer.schedule(event_handler, str(lab_path), recursive=False)
        self.observer.start()
        
        logger.info("WATCHDOG_ACTIVE path=%s - Auto Evolution Engine started", lab_path)
        
    def stop_monitoring(self):
        """Ferma monitoraggio."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
        self.is_running = False
        logger.info("EVOLUTION_STOPPED - Auto Evolution Engine stopped")
    
    async def process_report(self, report_path: str):
        """Processa un nuovo report di Massive Training con meta-governance EMA."""
        try:
            # 🔵 DEBUG OBBLIGATORIO - entrata process
            logger.info("EVOLUTION_ENTERED report=%s", report_path)
            
            # 🚨 PROTEZIONE ANTI-DEGENERAZIONE API
            if not await self._validate_report_safety(report_path):
                logger.error(f"🚨 Report INVALIDO - degenerazione rilevata: {report_path}")
                log("EVOLUTION_DECISION", status="ignore")
                return
            
            # 🔵 DEBUG OBBLIGATORIO - inizio processing
            logger.info("PROCESSING_REPORT %s", report_path)
            
            # Analizza report
            analysis = self.auto_tuner.analyze_report(report_path)
            if not analysis:
                log("EVOLUTION_DECISION", status="ignore")
                return
            
            # 🔵 DEBUG OBBLIGATORIO - metrics parsed
            logger.info("EVOLUTION_METRICS %s", analysis)
            
            # META-GOVERNANCE EXTENSION START
            # Detect drift nei parametri correnti
            current_params = self._get_current_tuning_params()
            drift_info = await self._meta_governance.detect_drift(current_params)
            
            # Alert se drift significativo
            if drift_info["drift_detected"] and drift_info["drift_magnitude"] > 0.3:
                logger.warning("META_GOVERNANCE_DRIFT_ALERT magnitude=%.3f", drift_info['drift_magnitude'])
                # Aggiungi flag decisione senza sovrascrivere logica esistente
                analysis["meta_drift_detected"] = True
                analysis["meta_drift_magnitude"] = drift_info["drift_magnitude"]
            # META-GOVERNANCE EXTENSION END
            
            # 🔵 META-GOVERNANCE - Verifica blocco evoluzione
            previous_params = self._get_previous_tuning_params()
            block, reason = self._meta_governance.should_block_evolution(current_params, previous_params)
            if block:
                logger.warning("EVOLUTION_BLOCKED reason=%s", reason)
                return  # ritorna parametri invariati
            
            # 🔵 META-GOVERNANCE - Calcola decision flags
            has_hard_violation = await self._check_hard_constraints_violation(analysis)
            is_rollback_decision = has_hard_violation  # Sempre rollback su hard violation
            is_apply_decision = not has_hard_violation and analysis.get("within_target_ranges", False) == False
            
            # 🔵 META-GOVERNANCE - Applica governance completa
            updated_state = self.state_manager.apply_meta_governance(
                analysis, has_hard_violation, is_rollback_decision, is_apply_decision
            )
            
            # 🔵 GOVERNANCE - Verifica lock status
            is_locked = updated_state.get("auto_evolution_locked", False)
            
            # 🔵 CONTINUA solo se NON locked
            if has_hard_violation:
                logger.error("🚨 HARD CONSTRAINTS VIOLATION - initiating rollback")
                log("EVOLUTION_DECISION", status="rollback")
                await self._emergency_rollback()
                return
            
            if is_locked:
                log("EVOLUTION_DECISION", status="locked")
                logger.warning("🔒 Evolution locked - skipping tuning")
                return
            
            # 🔵 THROTTLING - Verifica frequenza evoluzione
            # Nota: user_id non disponibile qui, usiamo un approccio basato su tempo
            import time
            current_time = time.time()
            last_shift_time = self.state_manager.load_current_state().get("last_shift_timestamp", 0)
            min_interval = 300  # 5 minuti minimo tra shift (fallback quando user_id non disponibile)
            
            if current_time - last_shift_time < min_interval:
                logger.info("EVOLUTION_THROTTLED time_since_last=%.0fs min=%ds", current_time - last_shift_time, min_interval)
                return
            
            # 🔵 MESSAGING THROTTLING - Verifica numero messaggi per utente system
            try:
                from core.chat_memory import ChatMemory
                chat_memory = ChatMemory()
                system_message_count = chat_memory.get_message_count("system")
                
                if system_message_count < EVOLUTION_MIN_MESSAGES_BETWEEN_SHIFTS:
                    logger.info("EVOLUTION_THROTTLED_MESSAGES current=%d min=%d", system_message_count, EVOLUTION_MIN_MESSAGES_BETWEEN_SHIFTS)
                    return
            except Exception as e:
                # Se fallisce il conteggio, continua con logica tempo
                logger.warning("EVOLUTION_MESSAGE_COUNT_ERROR error=%s", e)
            
            # Esegui ciclo di auto-tuning
            result = self.auto_tuner.run_auto_tuning_cycle(report_path)
            
            # 🔵 DEBUG OBBLIGATORIO - decision
            log("EVOLUTION_DECISION", status=result['status'])
            
            # 🔵 TUNING SUPPORTIVE ISOLATO - Solo se optimal e unlocked
            if result['status'] == 'optimal' and not is_locked:
                changed = self._tune_supportive_only(analysis, updated_state)
                
                if changed:
                    # Crea snapshot e applica stato
                    self.state_manager.create_snapshot()
                    self.state_manager.save_current_state(updated_state)
                    reload_tuning_state()
                    logger.info("STATE_APPLIED_SUPPORTIVE_ONLY")
                else:
                    logger.info("NO_SUPPORTIVE_TUNING_NEEDED")
                return
            
            if result['status'] == 'adjusted':
                await self._log_tuning_applied(result)
                # 🔵 TRANSAZIONALE - applica con state manager
                await self._apply_tuning_transaction(result)
            elif result['status'] == 'rollback':
                await self._log_tuning_rollback(result)
                # 🔵 TRANSAZIONALE - rollback con state manager
                await self._rollback_transaction()
                
        except Exception as e:
            logger.error("EVOLUTION_EXCEPTION report=%s error=%s", report_path, e)
    
    async def _validate_report_safety(self, report_path: str) -> bool:
        """Valida che il report non contenga degenerazione API."""
        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                report = json.load(f)
            
            metrics = report.get('metrics', {})
            
            # 🚨 Controlli anti-degenerazione
            error_rate = metrics.get('error_count', 0) / max(metrics.get('total_messages', 1), 1)
            
            # Se error rate > 5% o LLM_SERVICE_ALL_FAIL
            if error_rate > 0.05:
                logger.error(f"🚨 High error rate: {error_rate:.2%}")
                return False
            
            # Controlla se ci sono fallimenti LLM
            if 'llm_service_all_fail' in report.get('errors', []):
                logger.error("🚨 LLM_SERVICE_ALL_FAIL detected")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating report safety: {e}")
            return False
    
    async def _check_hard_constraints_violation(self, analysis: Dict[str, Any]) -> bool:
        """Verifica violazione vincoli hard."""
        constraints = self.HARD_CONSTRAINTS
        
        # Supportive rate
        supportive_rate = analysis.get('supportive_rate', 0)
        if not (constraints['supportive_rate_range'][0] <= supportive_rate <= constraints['supportive_rate_range'][1]):
            logger.error(f"🚨 Supportive rate violation: {supportive_rate:.2%}")
            return True
        
        # Confrontational rate
        confrontational_rate = analysis.get('confrontational_rate', 0)
        if not (constraints['confrontational_rate_range'][0] <= confrontational_rate <= constraints['confrontational_rate_range'][1]):
            logger.error(f"🚨 Confrontational rate violation: {confrontational_rate:.2%}")
            return True
        
        # Repetition rate
        repetition_rate = analysis.get('repetition_rate', 0)
        if repetition_rate > constraints['repetition_rate_max']:
            logger.error(f"🚨 Repetition rate violation: {repetition_rate:.2%}")
            return True
        
        # Success rate
        success_rate = analysis.get('success_rate', 0)
        if success_rate < constraints['success_rate_min']:
            logger.error(f"🚨 Success rate violation: {success_rate:.2%}")
            return True
        
        # Response time
        avg_response_time = analysis.get('avg_response_time', 0)
        if avg_response_time > constraints['avg_response_time_max']:
            logger.error(f"🚨 Response time violation: {avg_response_time:.2f}s")
            return True
        
        return False
    
    async def _emergency_rollback(self):
        """Rollback di emergenza per violazione vincoli hard."""
        try:
            # Trova ultimo snapshot e rollback
            latest_snapshot = self.auto_tuner._get_latest_snapshot()
            if latest_snapshot:
                snapshot_id = self.auto_tuner.rollback_to_snapshot(latest_snapshot.get('id', 'unknown'))
                logger.critical(f"🚨 EMERGENCY ROLLBACK to snapshot: {snapshot_id}")
                
                # 🔵 DEBUG OBBLIGATORIO - rollback log
                logger.info("TUNING_ROLLBACK emergency_rollback")
                
                # 🔵 LOG OBBLIGATORIO rollback
                result = {
                    'snapshot_id': snapshot_id,
                    'reason': 'hard_constraints_violation'
                }
                await self._log_tuning_rollback(result)
            else:
                logger.critical("TUNING_ROLLBACK no_snapshots_available - emergency rollback impossible")
        except Exception as e:
            logger.error("EVOLUTION_EXCEPTION emergency rollback failed: %s", e)

        # META-GOVERNANCE EXTENSION START
        # Invalida shift proposti con stato corrente dopo rollback
        current_params = self._get_current_tuning_params()
        await self._meta_governance.evaluate_pending_shifts(current_params)
        logger.info("META_GOVERNANCE_SHIFTS_CLEARED_ON_ROLLBACK")
        # META-GOVERNANCE EXTENSION END
    
    async def _log_tuning_applied(self, result: Dict[str, Any]):
        """Log obbligatorio per tuning applicato."""
        old_state = result.get('previous_state', {})
        new_state = result.get('new_state', {})
        adjustments = result.get('adjustments', {})
        
        logger.info("🔧 TUNING_APPLIED")
        logger.info(f"OLD_STATE: {old_state}")
        logger.info(f"NEW_STATE: {new_state}")
        logger.info(f"DELTA: {adjustments}")
        
        # 🔵 DEBUG OBBLIGATORIO - tuning applicato
        log("TUNING_APPLIED", new_state=new_state)
        
        # Dettaglio per ogni parametro
        for param, delta in adjustments.items():
            logger.info("  TUNING_PARAM %s: %s", param, delta)
    
    async def _log_tuning_rollback(self, result: Dict[str, Any]):
        """Log obbligatorio per tuning rollback."""
        logger.critical("🔧 TUNING_ROLLBACK")
        logger.critical(f"ROLLBACK_REASON: {result}")
        
        # 🔵 DEBUG OBBLIGATORIO - rollback
        reason = result.get('reason', 'unknown')
        log("TUNING_ROLLBACK", reason=reason)
        logger.info("TUNING_ROLLBACK")  # Per test che cerca solo questa stringa
    
    # 🔵 TUNING SUPPORTIVE ISOLATO - Metodo privato
    def _tune_supportive_only(self, metrics: dict, state: dict) -> bool:
        """Tuning isolato del parametro supportive_intensity."""
        try:
            # Regole di sicurezza
            if metrics.get("within_target_ranges", False):
                return False
            
            if "supportive_rate" not in metrics:
                return False
            
            target_min = 0.15
            target_max = 0.22
            midpoint = (target_min + target_max) / 2

            observed = metrics["supportive_rate"]
            current = state["parameters"]["supportive_intensity"]

            if observed < target_min or observed > target_max:
                delta = (midpoint - observed) * 0.5
                proposed_value = current + delta
                
                # Applica max_delta clamp
                new_value = self._apply_clamped_delta("supportive_intensity", current, proposed_value)

                logger.info("TUNING_SUPPORTIVE delta=%.6f old=%.6f new=%.6f", delta, current, new_value)

                state["parameters"]["supportive_intensity"] = new_value
                return True

            return False
            
        except Exception as e:
            logger.error(f"❌ Error in _tune_supportive_only: {e}")
            return False
    
    async def _apply_tuning_transaction(self, result: Dict[str, Any]):
        """Applica transazione di tuning atomica."""
        try:
            # Carica stato corrente
            current_state = self.state_manager.load_current_state()
            
            # Estrai nuovi parametri
            new_parameters = result.get('new_state', {})
            
            # Applica transazione
            success = self.state_manager.apply_evolution_transaction(
                current_state, new_parameters
            )
            
            if success:
                # 🔵 GARANZIA INTEGRAZIONE llm_service - ricarica tuning state
                reload_tuning_state()
                logger.info("✅ Tuning transaction applied successfully")
            else:
                logger.error("❌ Tuning transaction failed")
                
        except Exception as e:
            logger.error(f"❌ Apply tuning transaction error: {e}")
    
    async def _rollback_transaction(self):
        """Esegue transazione di rollback."""
        try:
            success = self.state_manager.rollback_evolution_transaction()
            
            if success:
                # 🔵 GARANZIA INTEGRAZIONE llm_service - ricarica dopo rollback
                reload_tuning_state()
                logger.info("✅ Rollback transaction completed")
            else:
                logger.error("❌ Rollback transaction failed")
                
        except Exception as e:
            logger.error(f"❌ Rollback transaction error: {e}")
    
    async def get_current_tuning_state(self) -> Dict[str, Any]:
        """Ottieni stato corrente dei parametri di tuning."""
        return self.state_manager.load_current_state()
    
    async def manual_tuning_cycle(self, report_path: str) -> Dict[str, Any]:
        """Esegui ciclo di tuning manuale su report specifico."""
        return await self.process_report(report_path)

# META-GOVERNANCE EXTENSION START
    async def get_meta_governance_summary(self) -> Dict[str, Any]:
        """Ritorna sommario stato meta-governance."""
        return self._meta_governance.get_governance_summary()
    
    def _get_current_tuning_params(self) -> Dict[str, Any]:
        """Estrae parametri tuning correnti dal sistema."""
        try:
            # Prova a caricare stato corrente
            current_state = self.state_manager.load_current_state()
            return current_state.get("parameters", {})
        except Exception:
            # Fallback a valori default
            return {
                "supportive_intensity": 0.5,
                "attuned_intensity": 0.5,
                "confrontational_intensity": 0.5,
                "max_questions_per_response": 1,
                "repetition_penalty_weight": 1.0
            }
    # META-GOVERNANCE EXTENSION END

# Singleton globale per l'evolution engine
_evolution_engine = None

def get_evolution_engine() -> AutoEvolutionEngine:
    """Ottieni istanza singleton dell'evolution engine."""
    global _evolution_engine
    if _evolution_engine is None:
        _evolution_engine = AutoEvolutionEngine()
    return _evolution_engine

async def start_auto_evolution():
    """Avvia l'auto-evoluzione in background."""
    engine = get_evolution_engine()
    await engine.start_monitoring()

def stop_auto_evolution():
    """Ferma l'auto-evoluzione."""
    engine = get_evolution_engine()
    engine.stop_monitoring()
