"""Test per AutoTuner - Sistema di AutoTuning controllato del carattere per Genesi"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, mock_open

from core.auto_tuner import AutoTuner


class TestAutoTuner:
    """Test suite per AutoTuner."""
    
    def setup_method(self):
        """Setup per ogni test."""
        self.temp_dir = tempfile.mkdtemp()
        self.auto_tuner = AutoTuner(snapshots_dir=self.temp_dir)
        
    def test_compute_adjustments_range_limit(self):
        """Test che le correzioni rimangano nei limiti del 5%."""
        # Analisi con supportive molto basso
        analysis = {
            'supportive_rate': 0.05,  # Sotto 15%
            'confrontational_rate': 0.01,
            'repetition_rate': 0.01,
            'success_rate': 0.8,
            'avg_response_time': 2.0
        }
        
        adjustments = self.auto_tuner.compute_adjustments(analysis)
        
        # Verifica che nessun aggiustamento superi il 5%
        max_variation = self.auto_tuner.TARGET_RANGES['max_parameter_variation_per_cycle']
        for param, delta in adjustments.items():
            assert abs(delta) <= max_variation, f"Adjustment {param}={delta} exceeds 5% limit"
    
    def test_max_delta_5_percent(self):
        """Test specifico per limite massimo del 5%."""
        # Analisi estrema per massimizzare gli aggiustamenti
        analysis = {
            'supportive_rate': 0.0,  # Molto sotto target
            'confrontational_rate': 0.1,  # Molto sopra target
            'repetition_rate': 0.1,  # Molto sopra target
            'success_rate': 0.5,
            'avg_response_time': 10.0  # Molto lento
        }
        
        adjustments = self.auto_tuner.compute_adjustments(analysis)
        
        # Tutti gli aggiustamenti devono essere <= 0.05 (5%)
        for delta in adjustments.values():
            assert delta <= 0.05, f"Delta {delta} exceeds 5% maximum"
    
    def test_rollback(self):
        """Test funzionalità di rollback."""
        # Crea snapshot fittizio
        snapshot_id = "test_snapshot_001"
        snapshot = {
            'id': snapshot_id,
            'timestamp': '2026-02-17T00:00:00',
            'previous_state': {'supportive_intensity': 0.5},
            'new_state': {'supportive_intensity': 0.6},
            'identity_target': {'description': 'test'}
        }
        
        snapshot_file = Path(self.temp_dir) / f"{snapshot_id}.json"
        with open(snapshot_file, 'w') as f:
            json.dump(snapshot, f)
        
        # Test rollback
        result = self.auto_tuner.rollback_to_snapshot(snapshot_id)
        assert result == snapshot_id
        
        # Verifica che lo stato sia stato ripristinato
        current_state = self.auto_tuner._load_current_state()
        assert current_state['supportive_intensity'] == 0.5
    
    def test_snapshot_creation(self):
        """Test creazione snapshot."""
        previous_state = {'param1': 0.5}
        new_state = {'param1': 0.6}
        
        snapshot_id = self.auto_tuner.save_snapshot(previous_state, new_state)
        
        # Verifica esistenza file
        snapshot_file = Path(self.temp_dir) / f"{snapshot_id}.json"
        assert snapshot_file.exists()
        
        # Verifica contenuto
        with open(snapshot_file, 'r') as f:
            snapshot = json.load(f)
        
        assert snapshot['id'] == snapshot_id
        assert snapshot['previous_state'] == previous_state
        assert snapshot['new_state'] == new_state
    
    def test_no_regression_on_behavioral_modulation(self):
        """Test che non ci siano regressioni sulla behavioral modulation."""
        # Stato iniziale
        initial_state = {
            'supportive_deep_intensity': 0.5,
            'attuned_intensity': 0.4,
            'confrontational_intensity': 0.3,
            'max_questions_per_state': 0.6,
            'repetition_penalty_weight': 0.5,
            'emotional_pattern_threshold': 0.4
        }
        
        # Analisi che non richiede aggiustamenti (già nei target)
        analysis = {
            'supportive_rate': 0.18,  # Nel range 15-22%
            'confrontational_rate': 0.04,  # Nel range 2-6%
            'repetition_rate': 0.01,  # Sotto 2%
            'success_rate': 0.95,
            'avg_response_time': 2.0,
            'within_target_ranges': True
        }
        
        # Calcola aggiustamenti
        adjustments = self.auto_tuner.compute_adjustments(analysis)
        
        # Non dovrebbero esserci aggiustamenti se già nei target
        assert len(adjustments) == 0, "No adjustments should be made when already in target ranges"
    
    def test_validate_constraints(self):
        """Test validazione vincoli parametri."""
        # Stato valido
        valid_state = {'param1': 0.5, 'param2': 0.8}
        assert self.auto_tuner.validate_constraints(valid_state) == True
        
        # Stato invalido (valore fuori range)
        invalid_state = {'param1': -0.1, 'param2': 1.5}
        assert self.auto_tuner.validate_constraints(invalid_state) == False
        
        # Stato invalido (tipo non numerico)
        invalid_type_state = {'param1': 'string', 'param2': 0.5}
        assert self.auto_tuner.validate_constraints(invalid_type_state) == False
    
    def test_analyze_report(self):
        """Test analisi report."""
        # Report fittizio
        report = {
            'metrics': {
                'total_messages': 100,
                'success_count': 95,
                'error_count': 5,
                'supportive_count': 18,
                'confrontational_count': 4,
                'repetition_detected': 2,
                'avg_response_time': 2.5,
                'success_rate': 95  # Aggiunto success_rate diretto
            }
        }
        
        # Mock file
        with patch('builtins.open', mock_open(read_data=json.dumps(report))):
            analysis = self.auto_tuner.analyze_report('fake_path.json')
        
        # Verifica calcoli
        assert analysis['supportive_rate'] == 0.18  # 18/100
        assert analysis['confrontational_rate'] == 0.04  # 4/100
        assert analysis['repetition_rate'] == 0.02  # 2/100
        assert analysis['success_rate'] == 0.95  # 95/100
        assert analysis['avg_response_time'] == 2.5
    
    def test_target_ranges_check(self):
        """Test verifica range target."""
        # Nei target
        assert self.auto_tuner._check_target_ranges(0.18, 0.04, 0.01) == True
        
        # Fuori target (supportive troppo basso)
        assert self.auto_tuner._check_target_ranges(0.10, 0.04, 0.01) == False
        
        # Fuori target (confrontational troppo alto)
        assert self.auto_tuner._check_target_ranges(0.18, 0.08, 0.01) == False
        
        # Fuori target (repetition troppo alta)
        assert self.auto_tuner._check_target_ranges(0.18, 0.04, 0.03) == False
    
    def test_apply_adjustments_limits(self):
        """Test che gli aggiustamenti applicati rimangano nei limiti."""
        # Mock stato corrente e salvataggio
        with patch.object(self.auto_tuner, '_load_current_state', return_value={'param1': 0.5}), \
             patch.object(self.auto_tuner, '_save_current_state'), \
             patch.object(self.auto_tuner, 'save_snapshot', return_value='test_snapshot'):
            
            # Aggiustamento grande
            adjustments = {'param1': 0.5}  # Tentativo di raddoppiare
            
            result = self.auto_tuner.apply_adjustments(adjustments)
            new_state = result['new_state']
            
            # Il valore deve essere clamped a 1.0
            assert new_state['param1'] == 1.0
            
            # Reset stato per secondo test
            with patch.object(self.auto_tuner, '_load_current_state', return_value={'param1': 0.5}):
                # Aggiustamento negativo grande
                adjustments = {'param1': -0.8}  # Tentativo di andare sotto zero
                
                result = self.auto_tuner.apply_adjustments(adjustments)
                new_state = result['new_state']
                
                # Il valore deve essere clamped a 0.0
                assert new_state['param1'] == 0.0
