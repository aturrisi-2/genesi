"""
Test Evolution Transactions - Sistema Transazionale Robusto
Verifica snapshot versionati, apply atomico e rollback reale
"""

import pytest
import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.evolution_state_manager import EvolutionStateManager, get_evolution_state_manager
from core.auto_evolution_engine import get_evolution_engine
from core.llm_service import load_tuning_state, reload_tuning_state

class TestEvolutionTransactions:
    
    @pytest.fixture
    def state_manager(self):
        """Fixture per ottenere state manager."""
        return EvolutionStateManager("test_evolution")
    
    @pytest.fixture
    def test_state(self):
        """Stato di test per transazioni."""
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
            "evolution_count": 0
        }
    
    def test_snapshot_created_on_apply(self, state_manager, test_state):
        """Test che snapshot viene creato durante apply."""
        new_parameters = {
            "supportive_intensity": 0.7,
            "attuned_intensity": 0.6
        }
        
        # Cattura stdout
        import sys
        from io import StringIO
        captured_output = StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured_output
        
        try:
            # Applica transazione
            success = state_manager.apply_evolution_transaction(test_state, new_parameters)
            
            # Recupera output
            output = captured_output.getvalue()
            
            # Verifica successo
            assert success, "Transazione apply fallita"
            
            # Verifica snapshot creato
            assert "SNAPSHOT_CREATED" in output, "Snapshot non creato"
            assert "STATE_APPLIED" in output, "Stato non applicato"
            assert "EVOLUTION_LOG_WRITTEN" in output, "Log non scritto"
            
            # Verifica file snapshot
            snapshots = state_manager.list_snapshots()
            assert len(snapshots) > 0, "Nessun snapshot creato"
            
            print("✅ Test snapshot creato su apply superato")
            
        finally:
            sys.stdout = old_stdout
            # Pulizia
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
    
    def test_restore_on_rollback(self, state_manager, test_state):
        """Test che restore avviene su rollback."""
        # Prima crea uno snapshot
        snapshot_version = state_manager.create_snapshot(test_state)
        assert snapshot_version, "Snapshot non creato"
        
        # Modifica stato corrente
        modified_state = test_state.copy()
        modified_state["parameters"]["supportive_intensity"] = 0.9
        state_manager.save_current_state(modified_state)
        
        # Cattura stdout
        import sys
        from io import StringIO
        captured_output = StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured_output
        
        try:
            # Esegui rollback
            success = state_manager.rollback_evolution_transaction()
            
            # Recupera output
            output = captured_output.getvalue()
            
            # Verifica successo
            assert success, "Transazione rollback fallita"
            
            # Verifica log
            assert "STATE_ROLLED_BACK" in output, "Rollback non loggato"
            assert "EVOLUTION_LOG_WRITTEN" in output, "Log non scritto"
            
            # Verifica stato ripristinato
            current_state = state_manager.load_current_state()
            assert current_state["parameters"]["supportive_intensity"] == 0.5, "Stato non ripristinato"
            
            print("✅ Test restore su rollback superato")
            
        finally:
            sys.stdout = old_stdout
            # Pulizia
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
    
    def test_crash_mid_apply_simulation(self, state_manager, test_state):
        """Test simulazione crash durante apply con rollback automatico."""
        
        try:
            # Simula scenario: snapshot creato ma apply fallisce
            # 1. Crea snapshot manualmente
            snapshot_version = state_manager.create_snapshot(test_state)
            assert snapshot_version, "Snapshot non creato"
            
            # 2. Modifica stato corrente per simulare stato intermedio
            modified_state = test_state.copy()
            modified_state["parameters"]["supportive_intensity"] = 0.8
            state_manager.save_current_state(modified_state)
            
            # 3. Simula rollback manuale (come farebbe apply_evolution_transaction in caso di crash)
            restored_state = state_manager.restore_last_snapshot()
            
            # 4. Verifica che rollback sia avvenuto
            assert restored_state is not None, "Rollback fallito"
            
            current_state = state_manager.load_current_state()
            assert current_state["parameters"]["supportive_intensity"] == 0.5, "Stato non ripristinato dopo rollback"
            
            # 5. Verifica log di rollback
            log_entry = {
                "action": "rollback_simulated",
                "restored_to": snapshot_version,
                "parameters": current_state["parameters"]
            }
            state_manager.append_evolution_log(log_entry)
            
            print("✅ Test crash mid-apply con rollback superato")
            
        finally:
            # Pulizia
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
    
    def test_no_apply_without_snapshot(self, state_manager, test_state):
        """Test che apply non avvenga senza snapshot."""
        
        # Mock create_snapshot per fallire
        def failing_create(*args, **kwargs):
            return None
        
        state_manager.create_snapshot = failing_create
        
        try:
            new_parameters = {"supportive_intensity": 0.8}
            
            # Applica transazione (dovrebbe fallire)
            success = state_manager.apply_evolution_transaction(test_state, new_parameters)
            
            # Verifica fallimento
            assert not success, "Apply dovrebbe fallire senza snapshot"
            
            # Verifica che stato non sia cambiato
            current_state = state_manager.load_current_state()
            assert current_state["parameters"]["supportive_intensity"] == 0.5, "Stato non dovrebbe cambiare"
            
            print("✅ Test no apply senza snapshot superato")
            
        finally:
            # Pulizia
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
    
    def test_multiple_versioning(self, state_manager, test_state):
        """Test versioning multiplo degli snapshot."""
        try:
            # Crea più versioni
            versions = []
            for i in range(3):
                # Aggiungi piccolo delay per unicità timestamp
                time.sleep(0.001)
                
                new_parameters = {
                    "supportive_intensity": 0.5 + (i * 0.1)
                }
                
                # Aggiorna stato corrente
                current_state = state_manager.load_current_state()
                success = state_manager.apply_evolution_transaction(current_state, new_parameters)
                assert success, f"Transazione {i} fallita"
                
                # Salva versione
                versions.append(current_state["parameters"]["supportive_intensity"])
            
            # Verifica snapshot multipli
            snapshots = state_manager.list_snapshots()
            assert len(snapshots) >= 3, f"Snapshot multipli non creati: {len(snapshots)} trovati"
            
            # Verifica versioni diverse
            snapshot_versions = [s["version"] for s in snapshots]
            assert len(set(snapshot_versions)) == len(snapshot_versions), "Versioni non univoche"
            
            print("✅ Test multiple versioning superato")
            
        finally:
            # Pulizia
            if state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(state_manager.base_dir)
    
    @pytest.mark.asyncio
    async def test_integration_with_evolution_engine(self):
        """Test integrazione con auto evolution engine."""
        try:
            # Ottieni engine e state manager
            engine = get_evolution_engine()
            test_state_manager = EvolutionStateManager("test_integration")
            
            # Mock state manager nell'engine
            engine.state_manager = test_state_manager
            
            # Crea report finto
            fake_report = {
                "metrics": {
                    "total_messages": 100,
                    "success_count": 95,
                    "error_count": 0,
                    "supportive_count": 10,  # 10% (sotto 15-22%)
                    "confrontational_count": 2,  # 2% (dentro 2-6%)
                    "repetition_detected": 1,  # 1% (sotto 2%)
                    "avg_response_time": 2.5  # sotto 3.5s
                }
            }
            
            # Scrivi report temporaneo
            report_path = Path("test_report.json")
            with open(report_path, 'w') as f:
                json.dump(fake_report, f)
            
            # Cattura stdout
            import sys
            from io import StringIO
            captured_output = StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured_output
            
            try:
                # Processa report
                await engine.process_report(str(report_path))
                
                # Recupera output
                output = captured_output.getvalue()
                
                # Verifica transazione
                assert "SNAPSHOT_CREATED" in output or "EVOLUTION_DECISION" in output, "Transazione non eseguita"
                
                print("✅ Test integrazione evolution engine superato")
                
            finally:
                sys.stdout = old_stdout
                if report_path.exists():
                    report_path.unlink()
                
        finally:
            # Pulizia
            if test_state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(test_state_manager.base_dir)
    
    def test_llm_service_integration(self):
        """Test integrazione llm service con evolution state manager."""
        try:
            # Crea state manager di test
            test_state_manager = EvolutionStateManager("test_llm_integration")
            
            # Mock get_evolution_state_manager
            import core.evolution_state_manager
            original_get = core.evolution_state_manager.get_evolution_state_manager
            core.evolution_state_manager.get_evolution_state_manager = lambda: test_state_manager
            
            try:
                # Test caricamento stato
                state = load_tuning_state()
                assert "supportive_intensity" in state, "Stato non caricato correttamente"
                
                # Test reload
                reloaded = reload_tuning_state()
                assert reloaded == state, "Reload non funzionante"
                
                print("✅ Test integrazione llm service superato")
                
            finally:
                # Ripristina originale
                core.evolution_state_manager.get_evolution_state_manager = original_get
                
        finally:
            # Pulizia
            if test_state_manager.base_dir.exists():
                import shutil
                shutil.rmtree(test_state_manager.base_dir)
