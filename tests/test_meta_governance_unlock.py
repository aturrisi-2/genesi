"""
Test Meta-Governance Unlock Logic
Verifica nuova logica unlock basata su consecutive_valid_reports invece di apply_streak
"""

import pytest
import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.evolution_state_manager import EvolutionStateManager, get_evolution_state_manager

class TestMetaGovernanceUnlock:
    
    @pytest.fixture
    def state_manager(self):
        """Fixture per ottenere state manager."""
        return EvolutionStateManager("test_meta_governance_unlock")
    
    @pytest.fixture
    def locked_state(self):
        """Stato locked per test."""
        return {
            "version": "1.0.0",
            "timestamp": "2026-02-17T12:00:00",
            "parameters": {
                "supportive_intensity": 0.5,
                "attuned_intensity": 0.5,
                "confrontational_intensity": 0.5,
                "max_questions_per_response": 1,
                "repetition_penalty_weight": 1.0
            },
            "last_snapshot": None,
            "evolution_count": 0,
            "stability_score": 0.3,
            "ema_stability": 0.35,
            "rollback_streak": 0,
            "apply_streak": 0,
            "hard_violation_streak": 2,
            "consecutive_valid_reports": 0,
            "evolution_health": "critical",
            "auto_evolution_locked": True
        }
    
    def test_no_unlock_if_only_ema_recovers(self, state_manager, locked_state):
        """Test: nessuno unlock se solo EMA recupera ma report non validi."""
        try:
            # Imposta stato locked
            state_manager.save_current_state(locked_state)
            
            # Report con EMA recuperato ma report non validi
            report_metrics = {
                "success_rate": 0.85,  # < 0.90
                "error_rate": 0.10,    # > 0.05
                "within_target_ranges": False
            }
            
            # Simula 3 report con EMA che recupera gradualmente
            for i in range(3):
                updated_state = state_manager.apply_meta_governance(
                    report_metrics, has_hard_violation=False, is_rollback_decision=False, is_apply_decision=False
                )
                time.sleep(0.001)  # Per unique timestamps
            
            # EMA dovrebbe essere > 0.6 ma sistema rimane locked
            assert updated_state["ema_stability"] > 0.6, "EMA should have recovered"
            assert updated_state["auto_evolution_locked"] == True, "Should remain locked without valid reports"
            assert updated_state["consecutive_valid_reports"] == 0, "No consecutive valid reports"
            
            print("✅ Test no unlock if only EMA recovers superato")
            
        finally:
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
    
    def test_no_unlock_if_only_reports_valid(self, state_manager, locked_state):
        """Test: nessuno unlock se solo report validi ma EMA non recupera."""
        try:
            # Imposta stato locked con EMA molto basso
            locked_state["ema_stability"] = 0.3
            state_manager.save_current_state(locked_state)
            
            # Report con success_rate basso per mantenere EMA < 0.6
            report_metrics = {
                "success_rate": 0.85,  # < 0.90 (non valido)
                "error_rate": 0.02,    # <= 0.05
                "within_target_ranges": True
            }
            
            # Simula 3 report con success_rate basso (non validi)
            for i in range(3):
                updated_state = state_manager.apply_meta_governance(
                    report_metrics, has_hard_violation=False, is_rollback_decision=False, is_apply_decision=False
                )
                time.sleep(0.001)  # Per unique timestamps
            
            # Report non validi - EMA potrebbe migliorare ma non ci sono report validi
            assert updated_state["consecutive_valid_reports"] == 0, "No valid reports with low success_rate"
            assert updated_state["auto_evolution_locked"] == True, "Should remain locked without valid reports"
            
            print("✅ Test no unlock if only reports valid superato")
            
        finally:
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
    
    def test_unlock_after_3_consecutive_valid_reports_and_ema_gt_0_6(self, state_manager, locked_state):
        """Test: unlock dopo 3 report consecutivi validi e EMA > 0.6."""
        try:
            # Imposta stato locked
            state_manager.save_current_state(locked_state)
            
            # Report validi che gradualmente migliorano EMA
            report_metrics = {
                "success_rate": 0.95,  # >= 0.90
                "error_rate": 0.02,    # <= 0.05
                "within_target_ranges": True
            }
            
            # Simula 3 report validi consecutivi
            for i in range(3):
                updated_state = state_manager.apply_meta_governance(
                    report_metrics, has_hard_violation=False, is_rollback_decision=False, is_apply_decision=False
                )
                time.sleep(0.001)  # Per unique timestamps
            
            # Dopo 3 report validi e EMA > 0.6, dovrebbe unlock
            assert updated_state["consecutive_valid_reports"] == 3, "Should have 3 consecutive valid reports"
            assert updated_state["ema_stability"] > 0.6, "EMA should be > 0.6"
            assert updated_state["auto_evolution_locked"] == False, "Should be unlocked"
            assert updated_state["hard_violation_streak"] == 0, "Hard violation streak should be reset"
            
            print("✅ Test unlock after 3 consecutive valid reports and EMA > 0.6 superato")
            
        finally:
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
    
    def test_unlock_requires_consecutive_reports(self, state_manager, locked_state):
        """Test: unlock richiede report consecutivi."""
        try:
            # Imposta stato locked
            state_manager.save_current_state(locked_state)
            
            # Alterna report validi e non validi
            valid_report = {
                "success_rate": 0.95,
                "error_rate": 0.02,
                "within_target_ranges": True
            }
            
            invalid_report = {
                "success_rate": 0.85,
                "error_rate": 0.10,
                "within_target_ranges": False
            }
            
            # Sequenza: valido, non valido, valido, non valido, valido
            reports = [valid_report, invalid_report, valid_report, invalid_report, valid_report]
            
            for i, report in enumerate(reports):
                updated_state = state_manager.apply_meta_governance(
                    report, has_hard_violation=False, is_rollback_decision=False, is_apply_decision=False
                )
                time.sleep(0.001)  # Per unique timestamps
                
                # Verifica che consecutive_valid_reports si resetti dopo report non valido
                if i % 2 == 1:  # Report non valido
                    assert updated_state["consecutive_valid_reports"] == 0, "Should reset after invalid report"
            
            # 3 report validi totali ma non consecutivi - dovrebbe rimanere locked
            assert updated_state["auto_evolution_locked"] == True, "Should remain locked without consecutive reports"
            
            print("✅ Test unlock requires consecutive reports superato")
            
        finally:
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
    
    def test_no_unlock_if_success_rate_low(self, state_manager, locked_state):
        """Test: nessuno unlock se success_rate < 0.90."""
        try:
            # Imposta stato locked
            state_manager.save_current_state(locked_state)
            
            # Report con success_rate troppo basso
            report_metrics = {
                "success_rate": 0.89,  # < 0.90
                "error_rate": 0.02,    # <= 0.05
                "within_target_ranges": True
            }
            
            # Simula 3 report con success_rate basso
            for i in range(3):
                updated_state = state_manager.apply_meta_governance(
                    report_metrics, has_hard_violation=False, is_rollback_decision=False, is_apply_decision=False
                )
                time.sleep(0.001)  # Per unique timestamps
            
            # Success rate basso - dovrebbe rimanere locked
            assert updated_state["consecutive_valid_reports"] == 0, "No valid reports with low success_rate"
            assert updated_state["auto_evolution_locked"] == True, "Should remain locked with low success_rate"
            
            print("✅ Test no unlock if success_rate low superato")
            
        finally:
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
    
    def test_no_unlock_if_error_rate_high(self, state_manager, locked_state):
        """Test: nessuno unlock se error_rate > 0.05."""
        try:
            # Imposta stato locked
            state_manager.save_current_state(locked_state)
            
            # Report con error_rate troppo alto
            report_metrics = {
                "success_rate": 0.95,  # >= 0.90
                "error_rate": 0.06,    # > 0.05
                "within_target_ranges": True
            }
            
            # Simula 3 report con error_rate alto
            for i in range(3):
                updated_state = state_manager.apply_meta_governance(
                    report_metrics, has_hard_violation=False, is_rollback_decision=False, is_apply_decision=False
                )
                time.sleep(0.001)  # Per unique timestamps
            
            # Error rate alto - dovrebbe rimanere locked
            assert updated_state["consecutive_valid_reports"] == 0, "No valid reports with high error_rate"
            assert updated_state["auto_evolution_locked"] == True, "Should remain locked with high error_rate"
            
            print("✅ Test no unlock if error_rate high superato")
            
        finally:
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
    
    def test_consecutive_valid_reports_tracking(self, state_manager):
        """Test tracciamento consecutive_valid_reports."""
        try:
            # Stato iniziale
            initial_state = {
                "version": "1.0.0",
                "timestamp": "2026-02-17T12:00:00",
                "parameters": {"supportive_intensity": 0.5},
                "last_snapshot": None,
                "evolution_count": 0,
                "stability_score": 1.0,
                "ema_stability": 1.0,
                "rollback_streak": 0,
                "apply_streak": 0,
                "hard_violation_streak": 0,
                "consecutive_valid_reports": 0,
                "evolution_health": "stable",
                "auto_evolution_locked": False
            }
            state_manager.save_current_state(initial_state)
            
            # Report valido
            valid_report = {
                "success_rate": 0.95,
                "error_rate": 0.02,
                "within_target_ranges": True
            }
            
            # Report non valido
            invalid_report = {
                "success_rate": 0.85,
                "error_rate": 0.10,
                "within_target_ranges": False
            }
            
            # 1. Report valido - incrementa
            updated_state = state_manager.apply_meta_governance(
                valid_report, has_hard_violation=False, is_rollback_decision=False, is_apply_decision=False
            )
            assert updated_state["consecutive_valid_reports"] == 1, "Should increment to 1"
            
            # 2. Report valido - incrementa
            updated_state = state_manager.apply_meta_governance(
                valid_report, has_hard_violation=False, is_rollback_decision=False, is_apply_decision=False
            )
            assert updated_state["consecutive_valid_reports"] == 2, "Should increment to 2"
            
            # 3. Report non valido - reset
            updated_state = state_manager.apply_meta_governance(
                invalid_report, has_hard_violation=False, is_rollback_decision=False, is_apply_decision=False
            )
            assert updated_state["consecutive_valid_reports"] == 0, "Should reset to 0"
            
            print("✅ Test consecutive_valid_reports tracking superato")
            
        finally:
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
