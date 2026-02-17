"""
Test Supportive Tuning Isolated
Verifica tuning isolato del parametro supportive_intensity
"""

import pytest
from unittest.mock import Mock, patch
from core.auto_evolution_engine import AutoEvolutionEngine

class TestSupportiveTuning:
    
    @pytest.fixture
    def engine(self):
        """AutoEvolutionEngine instance per test."""
        return AutoEvolutionEngine()
    
    @pytest.fixture
    def mock_state(self):
        """State mock per test."""
        return {
            "parameters": {
                "supportive_intensity": 0.5,
                "attuned_intensity": 0.5,
                "confrontational_intensity": 0.5,
                "max_questions_per_response": 1,
                "repetition_penalty_weight": 1.0
            }
        }
    
    def test_supportive_increase_when_low(self, engine, mock_state):
        """Test aumento supportive quando observed rate è basso."""
        # Metrics con supportive_rate basso (< 0.15)
        metrics = {
            "supportive_rate": 0.10,  # < target_min
            "within_target_ranges": False
        }
        
        # Mock state manager per evitare filesystem
        with patch.object(engine, 'state_manager') as mock_sm:
            mock_sm.create_snapshot.return_value = True
            mock_sm.save_current_state.return_value = True
            
            # Esegui tuning
            changed = engine._tune_supportive_only(metrics, mock_state)
            
            # Verifica cambiamento
            assert changed == True, "Should return True when tuning applied"
            new_value = mock_state["parameters"]["supportive_intensity"]
            assert new_value > 0.5, f"Should increase from 0.5, got {new_value}"
            assert 0.2 <= new_value <= 0.8, f"Should be clamped in [0.2, 0.8], got {new_value}"
    
    def test_supportive_decrease_when_high(self, engine, mock_state):
        """Test diminuzione supportive quando observed rate è alto."""
        # Metrics con supportive_rate alto (> 0.22)
        metrics = {
            "supportive_rate": 0.30,  # > target_max
            "within_target_ranges": False
        }
        
        # Mock state manager
        with patch.object(engine, 'state_manager') as mock_sm:
            mock_sm.create_snapshot.return_value = True
            mock_sm.save_current_state.return_value = True
            
            # Esegui tuning
            changed = engine._tune_supportive_only(metrics, mock_state)
            
            # Verifica cambiamento
            assert changed == True, "Should return True when tuning applied"
            new_value = mock_state["parameters"]["supportive_intensity"]
            assert new_value < 0.5, f"Should decrease from 0.5, got {new_value}"
            assert 0.2 <= new_value <= 0.8, f"Should be clamped in [0.2, 0.8], got {new_value}"
    
    def test_no_tuning_when_within_range(self, engine, mock_state):
        """Test nessun tuning quando supportive_rate è nel range."""
        # Metrics con supportive_rate nel range [0.15, 0.22]
        metrics = {
            "supportive_rate": 0.18,  # Nel range
            "within_target_ranges": False
        }
        
        # Esegui tuning
        changed = engine._tune_supportive_only(metrics, mock_state)
        
        # Verifica nessun cambiamento
        assert changed == False, "Should return False when within range"
        assert mock_state["parameters"]["supportive_intensity"] == 0.5, "Should not change when within range"
    
    def test_clamp_lower_bound(self, engine, mock_state):
        """Test clamp lower bound a 0.2."""
        # Metrics che porterebbero a valore < 0.2
        metrics = {
            "supportive_rate": 0.05,  # Molto basso
            "within_target_ranges": False
        }
        
        # Imposta current basso per testare clamp
        mock_state["parameters"]["supportive_intensity"] = 0.1
        
        # Esegui tuning
        changed = engine._tune_supportive_only(metrics, mock_state)
        
        # Verifica clamp
        assert changed == True, "Should return True when tuning applied"
        new_value = mock_state["parameters"]["supportive_intensity"]
        assert new_value >= 0.2, f"Should be clamped to >= 0.2, got {new_value}"
    
    def test_clamp_upper_bound(self, engine, mock_state):
        """Test clamp upper bound a 0.8."""
        # Metrics che porterebbero a valore > 0.8
        metrics = {
            "supportive_rate": 0.50,  # Molto alto
            "within_target_ranges": False
        }
        
        # Imposta current alto per testare clamp
        mock_state["parameters"]["supportive_intensity"] = 0.9
        
        # Esegui tuning
        changed = engine._tune_supportive_only(metrics, mock_state)
        
        # Verifica clamp
        assert changed == True, "Should return True when tuning applied"
        new_value = mock_state["parameters"]["supportive_intensity"]
        assert new_value <= 0.8, f"Should be clamped to <= 0.8, got {new_value}"
    
    def test_no_tuning_when_within_target_ranges(self, engine, mock_state):
        """Test nessun tuning quando within_target_ranges è True."""
        # Metrics con within_target_ranges True
        metrics = {
            "supportive_rate": 0.10,  # Fuori range ma...
            "within_target_ranges": True  # ...questo blocca il tuning
        }
        
        # Esegui tuning
        changed = engine._tune_supportive_only(metrics, mock_state)
        
        # Verifica nessun cambiamento
        assert changed == False, "Should return False when within_target_ranges is True"
        assert mock_state["parameters"]["supportive_intensity"] == 0.5, "Should not change when within_target_ranges is True"
    
    def test_no_tuning_when_missing_supportive_rate(self, engine, mock_state):
        """Test nessun tuning quando supportive_rate è mancante."""
        # Metrics senza supportive_rate
        metrics = {
            "within_target_ranges": False
            # supportive_rate mancante
        }
        
        # Esegui tuning
        changed = engine._tune_supportive_only(metrics, mock_state)
        
        # Verifica nessun cambiamento
        assert changed == False, "Should return False when supportive_rate is missing"
        assert mock_state["parameters"]["supportive_intensity"] == 0.5, "Should not change when supportive_rate is missing"
    
    def test_mathematical_precision(self, engine, mock_state):
        """Test precisione matematica del calcolo delta."""
        # Test con valori precisi
        metrics = {
            "supportive_rate": 0.10,  # target_min = 0.15, target_max = 0.22, midpoint = 0.185
            "within_target_ranges": False
        }
        
        # Esegui tuning
        changed = engine._tune_supportive_only(metrics, mock_state)
        
        # Verifica calcolo: delta = (0.185 - 0.10) * 0.5 = 0.0425
        # new_value = 0.5 + 0.0425 = 0.5425
        assert changed == True, "Should return True"
        expected_value = 0.5 + (0.185 - 0.10) * 0.5
        actual_value = mock_state["parameters"]["supportive_intensity"]
        assert abs(actual_value - expected_value) < 0.001, f"Expected {expected_value}, got {actual_value}"
    
    def test_integration_with_flow(self, engine):
        """Test integrazione con flow principale."""
        # Mock completo per test integrazione
        mock_state = {
            "parameters": {"supportive_intensity": 0.5},
            "auto_evolution_locked": False
        }
        
        mock_analysis = {
            "supportive_rate": 0.10,
            "within_target_ranges": False
        }
        
        mock_result = {"status": "optimal"}
        
        with patch.object(engine, 'state_manager') as mock_sm, \
             patch.object(engine, 'auto_tuner') as mock_at, \
             patch('core.auto_evolution_engine.reload_tuning_state') as mock_reload:
            
            mock_sm.load_current_state.return_value = mock_state
            mock_sm.create_snapshot.return_value = True
            mock_sm.save_current_state.return_value = True
            mock_at.run_auto_tuning_cycle.return_value = mock_result
            
            # Simula parte del flow
            changed = engine._tune_supportive_only(mock_analysis, mock_state)
            
            # Verifica integrazione
            assert changed == True, "Should apply tuning in integration test"
            assert mock_state["parameters"]["supportive_intensity"] != 0.5, "Should change parameter"
