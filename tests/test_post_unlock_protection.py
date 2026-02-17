"""
Test Post-Unlock Anti-Rimbalzo Protection
Verifica che il sistema non venga rilockato immediatamente dopo unlock
"""

import pytest
from unittest.mock import Mock, patch
from core.evolution_state_manager import EvolutionStateManager

class TestPostUnlockProtection:
    
    @pytest.fixture
    def manager(self):
        """EvolutionStateManager instance per test."""
        return EvolutionStateManager()
    
    @pytest.fixture
    def locked_state(self):
        """Stato locked di base per test."""
        return {
            "auto_evolution_locked": True,
            "ema_stability": 0.7,
            "consecutive_valid_reports": 3,
            "hard_violation_streak": 0,
            "post_unlock_observation": False,
            "post_unlock_remaining_reports": 0
        }
    
    @pytest.fixture
    def valid_report_metrics(self):
        """Report metrics validi."""
        return {
            "within_target_ranges": True,
            "success_rate": 0.95,
            "error_rate": 0.03
        }
    
    @pytest.fixture
    def invalid_report_metrics(self):
        """Report metrics non validi."""
        return {
            "within_target_ranges": False,
            "success_rate": 0.85,
            "error_rate": 0.08
        }
    
    def test_unlock_activates_observation(self, manager, locked_state, valid_report_metrics):
        """Test che unlock attivi observation mode."""
        # Mock save_current_state per evitare filesystem
        with patch.object(manager, 'save_current_state') as mock_save, \
             patch.object(manager, 'load_current_state', return_value=locked_state):
            
            # Applica meta-governance per simulare unlock completo
            updated_state = manager.apply_meta_governance(
                valid_report_metrics, 
                has_hard_violation=False, 
                is_rollback_decision=False, 
                is_apply_decision=False
            )
            
            # Verifica observation attivata
            assert updated_state["post_unlock_observation"] == True, "Should activate observation after unlock"
            # Verifica che sia stato decrementato da 2 a 1 (perché il report è valido)
            assert updated_state["post_unlock_remaining_reports"] == 1, "Should decrement to 1 after valid report"
            assert updated_state["auto_evolution_locked"] == False, "Should be unlocked"
    
    def test_single_negative_report_during_observation_no_relock(self, manager, valid_report_metrics):
        """Test che un singolo report negativo durante observation non rilockhi."""
        # Stato in observation
        state = {
            "auto_evolution_locked": False,
            "post_unlock_observation": True,
            "post_unlock_remaining_reports": 2,
            "hard_violation_streak": 0,
            "ema_stability": 0.7
        }
        
        # Report non valido ma senza hard violation
        invalid_metrics = {
            "within_target_ranges": False,
            "success_rate": 0.85,
            "error_rate": 0.08
        }
        
        # Mock load_current_state per restituire nostro stato
        with patch.object(manager, 'load_current_state', return_value=state), \
             patch.object(manager, 'save_current_state') as mock_save:
            
            # Valuta lock status
            should_lock, reason = manager.evaluate_lock_status(state)
            
            # Verifica che non venga locked (solo hard_violation_streak >= 2 può lockare)
            assert should_lock == False, "Should not lock on single negative report during observation"
            assert reason == "post_unlock_observation_active", "Should be in observation mode"
    
    def test_two_hard_violations_during_observation_relock(self, manager, valid_report_metrics):
        """Test che due hard violation consecutive durante observation rilockhino."""
        # Stato in observation con hard_violation_streak = 2
        state = {
            "auto_evolution_locked": False,
            "post_unlock_observation": True,
            "post_unlock_remaining_reports": 2,
            "hard_violation_streak": 2,  # Due hard violation
            "ema_stability": 0.7
        }
        
        # Mock load_current_state per restituire nostro stato
        with patch.object(manager, 'load_current_state', return_value=state), \
             patch.object(manager, 'save_current_state') as mock_save:
            
            # Valuta lock status
            should_lock, reason = manager.evaluate_lock_status(state)
            
            # Verifica che venga locked per hard violation
            assert should_lock == True, "Should lock on hard_violation_streak >= 2 during observation"
            assert "hard_violation_during_observation" in reason or "hard_violation_streak" in reason, "Should mention hard violation in reason"
    
    def test_observation_terminates_correctly(self, manager, valid_report_metrics):
        """Test che observation termini correttamente dopo 2 report validi."""
        # Stato in observation con 1 remaining report
        state = {
            "auto_evolution_locked": False,
            "post_unlock_observation": True,
            "post_unlock_remaining_reports": 1,
            "hard_violation_streak": 0,
            "ema_stability": 0.7
        }
        
        # Mock load_current_state per restituire nostro stato
        with patch.object(manager, 'load_current_state', return_value=state), \
             patch.object(manager, 'save_current_state') as mock_save:
            
            # Applica meta-governance con report valido
            updated_state = manager.apply_meta_governance(
                valid_report_metrics, 
                has_hard_violation=False, 
                is_rollback_decision=False, 
                is_apply_decision=False
            )
            
            # Verifica observation terminata
            assert updated_state["post_unlock_observation"] == False, "Should end observation after 2 valid reports"
            assert updated_state["post_unlock_remaining_reports"] == 0, "Should reset remaining reports to 0"
            assert updated_state["auto_evolution_locked"] == False, "Should remain unlocked"
    
    def test_observation_decrements_on_valid_reports(self, manager, valid_report_metrics):
        """Test che observation decrementi remaining reports solo su report validi."""
        # Stato in observation con 2 remaining
        state = {
            "auto_evolution_locked": False,
            "post_unlock_observation": True,
            "post_unlock_remaining_reports": 2,
            "hard_violation_streak": 0,
            "ema_stability": 0.7
        }
        
        # Mock load_current_state per restituire nostro stato
        with patch.object(manager, 'load_current_state', return_value=state), \
             patch.object(manager, 'save_current_state') as mock_save:
            
            # Applica meta-governance con report valido
            updated_state = manager.apply_meta_governance(
                valid_report_metrics, 
                has_hard_violation=False, 
                is_rollback_decision=False, 
                is_apply_decision=False
            )
            
            # Verifica decremento
            assert updated_state["post_unlock_remaining_reports"] == 1, "Should decrement remaining reports on valid report"
            assert updated_state["post_unlock_observation"] == True, "Should remain in observation"
    
    def test_observation_no_decrement_on_invalid_reports(self, manager, invalid_report_metrics):
        """Test che observation non decrementi su report non validi."""
        # Stato in observation con 2 remaining
        state = {
            "auto_evolution_locked": False,
            "post_unlock_observation": True,
            "post_unlock_remaining_reports": 2,
            "hard_violation_streak": 0,
            "ema_stability": 0.7
        }
        
        # Mock load_current_state per restituire nostro stato
        with patch.object(manager, 'load_current_state', return_value=state), \
             patch.object(manager, 'save_current_state') as mock_save:
            
            # Applica meta-governance con report non valido
            updated_state = manager.apply_meta_governance(
                invalid_report_metrics, 
                has_hard_violation=False, 
                is_rollback_decision=False, 
                is_apply_decision=False
            )
            
            # Verifica nessun decremento
            assert updated_state["post_unlock_remaining_reports"] == 2, "Should not decrement on invalid report"
            assert updated_state["post_unlock_observation"] == True, "Should remain in observation"
    
    def test_report_validation_method(self, manager):
        """Test metodo _is_report_valid."""
        # Report valido
        valid_report = {
            "within_target_ranges": True,
            "success_rate": 0.95,
            "error_rate": 0.03
        }
        assert manager._is_report_valid(valid_report) == True, "Should validate correct report"
        
        # Report non valido - within_target_ranges False
        invalid_report1 = {
            "within_target_ranges": False,
            "success_rate": 0.95,
            "error_rate": 0.03
        }
        assert manager._is_report_valid(invalid_report1) == False, "Should reject report with within_target_ranges=False"
        
        # Report non valido - success_rate basso
        invalid_report2 = {
            "within_target_ranges": True,
            "success_rate": 0.85,
            "error_rate": 0.03
        }
        assert manager._is_report_valid(invalid_report2) == False, "Should reject report with success_rate < 0.90"
        
        # Report non valido - error_rate alto
        invalid_report3 = {
            "within_target_ranges": True,
            "success_rate": 0.95,
            "error_rate": 0.08
        }
        assert manager._is_report_valid(invalid_report3) == False, "Should reject report with error_rate > 0.05"
    
    def test_initial_state_includes_observation_fields(self, manager):
        """Test che stato iniziale includa campi observation."""
        # Mock filesystem per nuovo stato
        with patch.object(manager, 'save_current_state') as mock_save, \
             patch('pathlib.Path.exists', return_value=False):
            
            # Inizializza manager
            manager.__init__()
            
            # Verifica che save_current_state sia stato chiamato con stato completo
            mock_save.assert_called_once()
            saved_state = mock_save.call_args[0][0]
            
            assert "post_unlock_observation" in saved_state, "Should include post_unlock_observation"
            assert "post_unlock_remaining_reports" in saved_state, "Should include post_unlock_remaining_reports"
            assert saved_state["post_unlock_observation"] == False, "Should default to False"
            assert saved_state["post_unlock_remaining_reports"] == 0, "Should default to 0"
