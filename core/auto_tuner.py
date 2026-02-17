"""
AutoTuner - Sistema di AutoTuning controllato del carattere per Genesi
Identità target: DIALOGICO BRILLANTE
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class AutoTuner:
    """Sistema di auto-tuning controllato per il carattere di Genesi."""
    
    # 📊 PALLETTI MATEMATICI OBBLIGATORI
    TARGET_RANGES = {
        'supportive_target_range': (0.15, 0.22),  # 15% - 22%
        'confrontational_range': (0.02, 0.06),     # 2% - 6%
        'repetition_max': 0.02,                    # 2%
        'autonomous_fallback_max': 0.05,           # 5%
        'avg_response_time_max': 3.5,               # 3.5s
        'max_parameter_variation_per_cycle': 0.05  # 5%
    }
    
    # 🎯 IDENTITÀ TARGET: DIALOGICO BRILLANTE
    IDENTITY_TARGET = {
        'description': 'Intelligente ma non accademico, fluido e naturale, breve quando serve, una domanda mirata massimo, mai aggressivo, mai freddo, no frasi template ripetitive, no eccesso di contenimento emotivo'
    }
    
    def __init__(self, snapshots_dir: str = "data/tuning_snapshots"):
        self.snapshots_dir = Path(snapshots_dir)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.tuning_state_file = Path("data/tuning_state.json")
        
    def analyze_report(self, report_path: str) -> Dict[str, Any]:
        """Analizza il report JSON del Massive Training."""
        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                report = json.load(f)
            
            metrics = report.get('metrics', {})
            
            # Calcola percentuali
            total_messages = metrics.get('total_messages', 1)
            
            # 🔵 PROTEZIONE DIVISION BY ZERO - Se total_messages = 0, usa 1 per evitare divisione
            if total_messages == 0:
                total_messages = 1
            
            supportive_rate = metrics.get('supportive_count', 0) / total_messages
            confrontational_rate = metrics.get('confrontational_count', 0) / total_messages
            repetition_rate = metrics.get('repetition_detected', 0) / total_messages
            
            # 🔵 CORREZIONE BUG CRITICO - Calcola success_rate correttamente
            success_count = metrics.get('success_count', 0)
            original_total = metrics.get('total_messages', 1)
            
            if original_total > 0:
                success_rate = success_count / original_total
            else:
                success_rate = 0.0
            
            # Clamp 0.0 - 1.0
            success_rate = max(0.0, min(1.0, success_rate))
            
            print(f"SUCCESS_RATE_CALCULATED success={success_count} total={original_total} rate={success_rate}")
            logger.info(f"📊 Success rate calculated: {success_count}/{original_total} = {success_rate}")
            
            analysis = {
                'supportive_rate': supportive_rate,
                'confrontational_rate': confrontational_rate,
                'repetition_rate': repetition_rate,
                'success_rate': success_rate,  # Usa valore calcolato
                'avg_response_time': metrics.get('avg_response_time', 0),
                'error_rate': metrics.get('error_count', 0) / total_messages,
                'within_target_ranges': self._check_target_ranges(supportive_rate, confrontational_rate, repetition_rate)
            }
            
            logger.info(f"Report analysis: {analysis}")
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing report: {e}")
            return {}
    
    def _check_target_ranges(self, supportive_rate: float, confrontational_rate: float, repetition_rate: float) -> bool:
        """Verifica se le metriche sono nei range target."""
        ranges = self.TARGET_RANGES
        
        supportive_ok = ranges['supportive_target_range'][0] <= supportive_rate <= ranges['supportive_target_range'][1]
        confrontational_ok = ranges['confrontational_range'][0] <= confrontational_rate <= ranges['confrontational_range'][1]
        repetition_ok = repetition_rate <= ranges['repetition_max']
        
        return supportive_ok and confrontational_ok and repetition_ok
    
    def compute_adjustments(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Calcola micro-correzioni basate sull'analisi."""
        adjustments = {}
        max_variation = self.TARGET_RANGES['max_parameter_variation_per_cycle']
        
        supportive_rate = analysis.get('supportive_rate', 0)
        confrontational_rate = analysis.get('confrontational_rate', 0)
        repetition_rate = analysis.get('repetition_rate', 0)
        
        # 🎯 Calcolo delta proporzionale (mai > 5%)
        
        # Se supportive è troppo basso, aumenta intensità supportive_deep
        if supportive_rate < self.TARGET_RANGES['supportive_target_range'][0]:
            delta = min(max_variation, (self.TARGET_RANGES['supportive_target_range'][0] - supportive_rate) * 0.5)
            adjustments['supportive_deep_intensity'] = delta
            adjustments['attuned_intensity'] = delta * 0.7  # Meno aggressivo
        
        # Se supportive è troppo alto, riduci intensità
        elif supportive_rate > self.TARGET_RANGES['supportive_target_range'][1]:
            delta = min(max_variation, (supportive_rate - self.TARGET_RANGES['supportive_target_range'][1]) * 0.5)
            adjustments['supportive_deep_intensity'] = -delta
            adjustments['attuned_intensity'] = -delta * 0.7
        
        # Se confrontational è troppo alto, riduci intensità
        if confrontational_rate > self.TARGET_RANGES['confrontational_range'][1]:
            delta = min(max_variation, (confrontational_rate - self.TARGET_RANGES['confrontational_range'][1]) * 0.5)
            adjustments['confrontational_intensity'] = -delta
        
        # Se confrontational è troppo basso, aumenta leggermente
        elif confrontational_rate < self.TARGET_RANGES['confrontational_range'][0]:
            delta = min(max_variation, (self.TARGET_RANGES['confrontational_range'][0] - confrontational_rate) * 0.3)
            adjustments['confrontational_intensity'] = delta
        
        # Se repetition è troppo alta, aumenta penalty
        if repetition_rate > self.TARGET_RANGES['repetition_max']:
            delta = min(max_variation, (repetition_rate - self.TARGET_RANGES['repetition_max']) * 2)
            adjustments['repetition_penalty_weight'] = delta
        
        # Se response time è troppo alto, riduci complessità
        if analysis.get('avg_response_time', 0) > self.TARGET_RANGES['avg_response_time_max']:
            delta = min(max_variation, 0.02)
            adjustments['max_questions_per_state'] = -delta
            adjustments['emotional_pattern_threshold'] = delta
        
        logger.info(f"Computed adjustments: {adjustments}")
        return adjustments
    
    def apply_adjustments(self, adjustments: Dict[str, Any]) -> Dict[str, Any]:
        """Applica le modifiche ai parametri comportamentali."""
        current_state = self._load_current_state()
        previous_snapshot = current_state.copy()
        
        # Applica aggiustamenti con limiti
        for param, delta in adjustments.items():
            if param in current_state:
                current_state[param] = max(0.0, min(1.0, current_state[param] + delta))
            else:
                current_state[param] = max(0.0, min(1.0, delta))
        
        # Salva nuovo stato
        self._save_current_state(current_state)
        
        # Salva snapshot per rollback
        snapshot_id = self.save_snapshot(previous_snapshot, current_state)
        
        logger.info(f"Applied adjustments, snapshot: {snapshot_id}")
        return {'snapshot_id': snapshot_id, 'new_state': current_state}
    
    def validate_constraints(self, state: Dict[str, Any]) -> bool:
        """Valida che i parametri rispettino i vincoli."""
        for param, value in state.items():
            if not isinstance(value, (int, float)) or value < 0 or value > 1:
                logger.error(f"Invalid parameter value: {param}={value}")
                return False
        return True
    
    def rollback_if_needed(self, current_analysis: Dict[str, Any], previous_analysis: Dict[str, Any]) -> Optional[str]:
        """Effettua rollback automatico se le metriche peggiorano."""
        current_success = current_analysis.get('success_rate', 0)
        previous_success = previous_analysis.get('success_rate', 0)
        current_repetition = current_analysis.get('repetition_rate', 0)
        previous_repetition = previous_analysis.get('repetition_rate', 0)
        
        # 🛑 Condizioni di rollback
        success_degradation = (previous_success - current_success) > 0.03  # > 3%
        repetition_increase = current_repetition > previous_repetition * 1.2  # > 20%
        supportive_out_of_range = not self._check_target_ranges(
            current_analysis.get('supportive_rate', 0),
            current_analysis.get('confrontational_rate', 0),
            current_analysis.get('repetition_rate', 0)
        )
        
        if success_degradation or repetition_increase or supportive_out_of_range:
            # Trova ultimo snapshot e rollback
            latest_snapshot = self._get_latest_snapshot()
            if latest_snapshot:
                return self.rollback_to_snapshot(latest_snapshot['id'])
        
        return None
    
    def save_snapshot(self, previous_state: Dict[str, Any], new_state: Dict[str, Any]) -> str:
        """Salva snapshot dello stato parametri."""
        snapshot_id = f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        snapshot = {
            'id': snapshot_id,
            'timestamp': datetime.now().isoformat(),
            'previous_state': previous_state,
            'new_state': new_state,
            'identity_target': self.IDENTITY_TARGET
        }
        
        snapshot_file = self.snapshots_dir / f"{snapshot_id}.json"
        with open(snapshot_file, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved snapshot: {snapshot_id}")
        return snapshot_id
    
    def rollback_to_snapshot(self, snapshot_id: str) -> str:
        """Ripristina stato da snapshot."""
        snapshot_file = self.snapshots_dir / f"{snapshot_id}.json"
        
        if not snapshot_file.exists():
            logger.error(f"Snapshot not found: {snapshot_id}")
            return ""
        
        with open(snapshot_file, 'r', encoding='utf-8') as f:
            snapshot = json.load(f)
        
        # Ripristina stato precedente
        previous_state = snapshot['previous_state']
        self._save_current_state(previous_state)
        
        logger.info(f"Rolled back to snapshot: {snapshot_id}")
        return snapshot_id
    
    def run_auto_tuning_cycle(self, report_path: str) -> Dict[str, Any]:
        """Ciclo automatico completo di auto-tuning."""
        try:
            # Analizza report
            analysis = self.analyze_report(report_path)
            
            # Se già nei target, nessuna modifica
            if analysis.get('within_target_ranges', False):
                return {'status': 'optimal', 'analysis': analysis}
            
            # Calcola aggiustamenti
            adjustments = self.compute_adjustments(analysis)
            
            if not adjustments:
                return {'status': 'no_adjustments_needed', 'analysis': analysis}
            
            # Applica aggiustamenti
            result = self.apply_adjustments(adjustments)
            
            return {
                'status': 'adjusted',
                'analysis': analysis,
                'adjustments': adjustments,
                'snapshot_id': result['snapshot_id'],
                'new_state': result['new_state']
            }
            
        except Exception as e:
            logger.error(f"Auto-tuning cycle failed: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def _load_current_state(self) -> Dict[str, Any]:
        """Carica stato corrente dei parametri."""
        if self.tuning_state_file.exists():
            with open(self.tuning_state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # Valori default
        return {
            'supportive_deep_intensity': 0.5,
            'attuned_intensity': 0.4,
            'confrontational_intensity': 0.3,
            'max_questions_per_state': 0.6,
            'repetition_penalty_weight': 0.5,
            'emotional_pattern_threshold': 0.4
        }
    
    def _save_current_state(self, state: Dict[str, Any]) -> None:
        """Salva stato corrente dei parametri."""
        self.tuning_state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.tuning_state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    
    def _get_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        """Ottiene l'ultimo snapshot salvato."""
        snapshots = list(self.snapshots_dir.glob("snapshot_*.json"))
        if not snapshots:
            return None
        
        latest = max(snapshots, key=lambda p: p.stat().st_mtime)
        with open(latest, 'r', encoding='utf-8') as f:
            return json.load(f)
