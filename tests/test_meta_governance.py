"""
Test Meta-Governance EMA Stability
Verifica calcolo EMA, lock/unlock, streak logic e governance rules
"""

import pytest
import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.evolution_state_manager import EvolutionStateManager, get_evolution_state_manager
from core.auto_evolution_engine import get_evolution_engine

class TestMetaGovernanceEMA:
    
    @pytest.fixture
    def state_manager(self):
        """Fixture per ottenere state manager."""
        return EvolutionStateManager("test_meta_governance")
    
    @pytest.fixture
    def base_state(self):
        """Stato base per test."""
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
            "stability_score": 1.0,
            "ema_stability": 1.0,
            "rollback_streak": 0,
            "apply_streak": 0,
            "hard_violation_streak": 0,
            "evolution_health": "stable",
            "auto_evolution_locked": False
        }
    
    def test_ema_calculation_correct(self, state_manager, base_state):
        """Test calcolo EMA corretto con alpha=0.4."""
        try:
            # Salva stato base
            state_manager.save_current_state(base_state)
            
            # Primo report: stability_score = 0.8
            report_metrics = {"success_rate": 0.8}
            updated_state = state_manager.apply_meta_governance(
                report_metrics, has_hard_violation=False, is_rollback_decision=False, is_apply_decision=True
            )
            
            # EMA: 0.4 * 0.8 + 0.6 * 1.0 = 0.32 + 0.6 = 0.92
            expected_ema = 0.4 * 0.8 + 0.6 * 1.0
            actual_ema = updated_state["ema_stability"]
            
            assert abs(actual_ema - expected_ema) < 0.001, f"EMA {actual_ema} != expected {expected_ema}"
            assert updated_state["evolution_health"] == "stable", f"Health should be stable, got {updated_state['evolution_health']}"
            assert updated_state["apply_streak"] == 1, "Apply streak should be 1"
            
            print("✅ Test EMA calculation correct superato")
            
        finally:
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
    
    def test_lock_when_critical(self, state_manager, base_state):
        """Test lock automatico quando EMA < 0.4."""
        try:
            # Simula stato critico
            base_state["ema_stability"] = 0.3
            base_state["hard_violation_streak"] = 1
            state_manager.save_current_state(base_state)
            
            # Report con hard violation
            report_metrics = {"success_rate": 0.7}
            updated_state = state_manager.apply_meta_governance(
                report_metrics, has_hard_violation=True, is_rollback_decision=True, is_apply_decision=False
            )
            
            # Dovrebbe fare lock
            assert updated_state["auto_evolution_locked"] == True, "Should be locked when critical"
            assert updated_state["hard_violation_streak"] == 2, "Hard violation streak should be 2"
            assert updated_state["evolution_health"] == "critical", f"Health should be critical, got {updated_state['evolution_health']}"
            
            print("✅ Test lock when critical superato")
            
        finally:
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
    
    def test_unlock_after_recovery(self, state_manager, base_state):
        """Test unlock automatico dopo recovery."""
        try:
            # Simula stato locked con recovery
            base_state["auto_evolution_locked"] = True
            base_state["ema_stability"] = 0.5
            base_state["hard_violation_streak"] = 0
            base_state["apply_streak"] = 0
            state_manager.save_current_state(base_state)
            
            # 3 report successivi senza violazioni - report validi per nuova logica
            for i in range(3):
                report_metrics = {
                    "success_rate": 0.95,  # >= 0.90
                    "error_rate": 0.02,    # <= 0.05
                    "within_target_ranges": True
                }
                updated_state = state_manager.apply_meta_governance(
                    report_metrics, has_hard_violation=False, is_rollback_decision=False, is_apply_decision=False
                )
                time.sleep(0.001)  # Per unique timestamps
            
            # Dopo unlock, solo hard_violation_streak viene resettato
            assert updated_state["auto_evolution_locked"] == False, "Should be unlocked after recovery"
            assert updated_state["hard_violation_streak"] == 0, "Hard violation streak should be reset"
            # NOTA: apply_streak e rollback_streak NON vengono più resettati nella nuova logica
            
            print("✅ Test unlock after recovery superato")
            
        finally:
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
    
    def test_no_apply_when_locked(self, state_manager, base_state):
        """Test che non viene applicato tuning quando locked."""
        try:
            # Imposta stato locked
            base_state["auto_evolution_locked"] = True
            state_manager.save_current_state(base_state)
            
            # Mock auto_tuner per verificare che non venga chiamato
            with patch.object(state_manager, 'apply_evolution_transaction') as mock_apply:
                # Report che normalmente triggererebbe apply
                report_metrics = {"success_rate": 0.7}
                updated_state = state_manager.apply_meta_governance(
                    report_metrics, has_hard_violation=False, is_rollback_decision=False, is_apply_decision=True
                )
                
                # Verifica che apply_evolution_transaction non sia stato chiamato
                mock_apply.assert_not_called()
                assert updated_state["auto_evolution_locked"] == True, "Should remain locked"
            
            print("✅ Test no apply when locked superato")
            
        finally:
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
    
    def test_streak_increment_logic(self, state_manager, base_state):
        """Test logica increment streak counters."""
        try:
            state_manager.save_current_state(base_state)
            
            # 1. Apply decision
            report_metrics = {"success_rate": 0.8}
            updated_state = state_manager.apply_meta_governance(
                report_metrics, has_hard_violation=False, is_rollback_decision=False, is_apply_decision=True
            )
            assert updated_state["apply_streak"] == 1, "Apply streak should be 1"
            assert updated_state["rollback_streak"] == 0, "Rollback streak should be reset"
            
            # 2. Rollback decision
            updated_state = state_manager.apply_meta_governance(
                report_metrics, has_hard_violation=True, is_rollback_decision=True, is_apply_decision=False
            )
            assert updated_state["rollback_streak"] == 1, "Rollback streak should be 1"
            assert updated_state["apply_streak"] == 0, "Apply streak should be reset"
            assert updated_state["hard_violation_streak"] == 1, "Hard violation streak should be 1"
            
            # 3. Report senza violazioni (reset hard violation streak)
            updated_state = state_manager.apply_meta_governance(
                report_metrics, has_hard_violation=False, is_rollback_decision=False, is_apply_decision=True
            )
            assert updated_state["hard_violation_streak"] == 0, "Hard violation streak should be reset"
            
            print("✅ Test streak increment logic superato")
            
        finally:
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
    
    def test_health_classification(self, state_manager):
        """Test classificazione health basato su EMA."""
        try:
            # Test stable (> 0.8)
            health = state_manager.classify_evolution_health(0.9)
            assert health == "stable", f"0.9 should be stable, got {health}"
            
            # Test adaptive (> 0.6)
            health = state_manager.classify_evolution_health(0.7)
            assert health == "adaptive", f"0.7 should be adaptive, got {health}"
            
            # Test unstable (> 0.4)
            health = state_manager.classify_evolution_health(0.5)
            assert health == "unstable", f"0.5 should be unstable, got {health}"
            
            # Test critical (<= 0.4)
            health = state_manager.classify_evolution_health(0.3)
            assert health == "critical", f"0.3 should be critical, got {health}"
            
            print("✅ Test health classification superato")
            
        finally:
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
    
    def test_stability_score_calculation(self, state_manager):
        """Test calcolo stability score."""
        try:
            # Caso 1: Success rate alto, no violations
            metrics = {"success_rate": 0.95}
            score = state_manager.calculate_stability_score(metrics, has_hard_violation=False, is_rollback_decision=False)
            assert abs(score - 0.95) < 0.001, f"Score should be ~0.95, got {score}"
            
            # Caso 2: Hard violation
            score = state_manager.calculate_stability_score(metrics, has_hard_violation=True, is_rollback_decision=False)
            assert abs(score - 0.45) < 0.001, f"Score should be ~0.45 (0.95 - 0.5), got {score}"
            
            # Caso 3: Rollback decision
            score = state_manager.calculate_stability_score(metrics, has_hard_violation=False, is_rollback_decision=True)
            assert abs(score - 0.65) < 0.001, f"Score should be ~0.65 (0.95 - 0.3), got {score}"
            
            # Caso 4: Entrambe le violazioni (clamp 0)
            score = state_manager.calculate_stability_score(metrics, has_hard_violation=True, is_rollback_decision=True)
            assert abs(score - 0.15) < 0.001, f"Score should be ~0.15 (0.95 - 0.5 - 0.3), got {score}"
            
            # Caso 5: Clamp 0
            metrics = {"success_rate": 0.1}
            score = state_manager.calculate_stability_score(metrics, has_hard_violation=True, is_rollback_decision=True)
            assert score == 0.0, f"Score should be clamped to 0, got {score}"
            
            print("✅ Test stability score calculation superato")
            
        finally:
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
    
    @pytest.mark.asyncio
    async def test_integration_with_evolution_engine(self):
        """Test integrazione completa con auto evolution engine."""
        try:
            # Crea state manager di test
            test_state_manager = EvolutionStateManager("test_integration_meta")
            
            # Mock state manager nell'engine
            engine = get_evolution_engine()
            original_state_manager = engine.state_manager
            engine.state_manager = test_state_manager
            
            # Crea report finto
            fake_report = {
                "metrics": {
                    "total_messages": 100,
                    "success_count": 85,  # 85%
                    "error_count": 0,
                    "supportive_count": 10,  # 10% (sotto 15-22%)
                    "confrontational_count": 2,  # 2% (dentro 2-6%)
                    "repetition_detected": 1,  # 1% (sotto 2%)
                    "avg_response_time": 2.5  # sotto 3.5s
                }
            }
            
            # Scrivi report temporaneo
            report_path = Path("test_meta_report.json")
            with open(report_path, 'w') as f:
                json.dump(fake_report, f)
            
            try:
                # Processa report
                await engine.process_report(str(report_path))
                
                # Verifica meta-governance applicata
                current_state = test_state_manager.load_current_state()
                assert "ema_stability" in current_state, "EMA stability should be present"
                assert "evolution_health" in current_state, "Evolution health should be present"
                assert "stability_score" in current_state, "Stability score should be present"
                
                print("✅ Test integrazione evolution engine superato")
                
            finally:
                if report_path.exists():
                    report_path.unlink()
                engine.state_manager = original_state_manager
                
        finally:
            if test_state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(test_state_manager.base_dir)
