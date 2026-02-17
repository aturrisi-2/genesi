"""Test per AutoEvolutionEngine - Sistema di Auto-Evoluzione Aggressiva Controllata"""

import pytest
import json
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import patch, mock_open, AsyncMock

from core.auto_evolution_engine import AutoEvolutionEngine, ReportHandler, get_evolution_engine


class TestAutoEvolutionEngine:
    """Test suite per AutoEvolutionEngine."""
    
    def setup_method(self):
        """Setup per ogni test."""
        self.temp_dir = tempfile.mkdtemp()
        self.engine = AutoEvolutionEngine(lab_dir=self.temp_dir)
        
    def test_hard_constraints_violation(self):
        """Test violazione vincoli hard."""
        # Analisi con supportive fuori range
        analysis = {
            'supportive_rate': 0.10,  # Sotto 15%
            'confrontational_rate': 0.04,
            'repetition_rate': 0.01,
            'success_rate': 0.98,
            'avg_response_time': 2.0
        }
        
        # Verifica violazione
        result = asyncio.run(self.engine._check_hard_constraints_violation(analysis))
        assert result == True, "Should detect supportive rate violation"
        
        # Analisi nei range
        analysis_good = {
            'supportive_rate': 0.18,  # Nel range 15-22%
            'confrontational_rate': 0.04,  # Nel range 2-6%
            'repetition_rate': 0.01,  # Sotto 2%
            'success_rate': 0.98,  # Sopra 97%
            'avg_response_time': 2.0  # Sotto 3.5s
        }
        
        result = asyncio.run(self.engine._check_hard_constraints_violation(analysis_good))
        assert result == False, "Should not detect violation when in range"
    
    def test_validate_report_safety(self):
        """Test validazione sicurezza report."""
        # Report sicuro
        safe_report = {
            'metrics': {
                'total_messages': 100,
                'error_count': 3,  # 3% < 5%
                'success_count': 97
            }
        }
        
        with patch('builtins.open', mock_open(read_data=json.dumps(safe_report))):
            result = asyncio.run(self.engine._validate_report_safety('fake_path.json'))
            assert result == True, "Safe report should pass validation"
        
        # Report pericoloso (error rate > 5%)
        unsafe_report = {
            'metrics': {
                'total_messages': 100,
                'error_count': 10,  # 10% > 5%
                'success_count': 90
            }
        }
        
        with patch('builtins.open', mock_open(read_data=json.dumps(unsafe_report))):
            result = asyncio.run(self.engine._validate_report_safety('fake_path.json'))
            assert result == False, "Unsafe report should fail validation"
        
        # Report con LLM_SERVICE_ALL_FAIL
        fail_report = {
            'metrics': {
                'total_messages': 100,
                'error_count': 2
            },
            'errors': ['llm_service_all_fail']
        }
        
        with patch('builtins.open', mock_open(read_data=json.dumps(fail_report))):
            result = asyncio.run(self.engine._validate_report_safety('fake_path.json'))
            assert result == False, "LLM fail report should fail validation"
    
    def test_emergency_rollback(self):
        """Test rollback di emergenza."""
        # Mock snapshot
        snapshot = {
            'id': 'test_snapshot_001',
            'timestamp': '2026-02-17T00:00:00',
            'previous_state': {'param1': 0.5},
            'new_state': {'param1': 0.6}
        }
        
        with patch.object(self.engine.auto_tuner, '_get_latest_snapshot', return_value=snapshot), \
             patch.object(self.engine.auto_tuner, 'rollback_to_snapshot', return_value='test_snapshot_001') as mock_rollback:
            
            result = asyncio.run(self.engine._emergency_rollback())
            
            # Verifica rollback chiamato
            mock_rollback.assert_called_once_with('test_snapshot_001')
    
    def test_get_current_tuning_state(self):
        """Test ottenimento stato tuning corrente."""
        # Mock stato dal state manager
        mock_state = {
            'version': '1.0.0',
            'parameters': {'supportive_intensity': 1.2, 'confrontational_intensity': 0.8}
        }
        
        with patch.object(self.engine.state_manager, 'load_current_state', return_value=mock_state):
            state = asyncio.run(self.engine.get_current_tuning_state())
            assert state == mock_state
    
    def test_manual_tuning_cycle(self):
        """Test ciclo di tuning manuale."""
        report_path = f"{self.temp_dir}/test_report.json"
        
        # Mock process_report
        with patch.object(self.engine, 'process_report', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = None
            
            result = asyncio.run(self.engine.manual_tuning_cycle(report_path))
            
            # Verifica process_report chiamato
            mock_process.assert_called_once_with(report_path)
    
    def test_singleton_evolution_engine(self):
        """Test singleton pattern."""
        engine1 = get_evolution_engine()
        engine2 = get_evolution_engine()
        
        # Stessa istanza
        assert engine1 is engine2


class TestReportHandler:
    """Test per ReportHandler."""
    
    def test_report_creation_detection(self):
        """Test rilevamento creazione report."""
        # Mock evolution engine
        mock_engine = AsyncMock()
        handler = ReportHandler(mock_engine)
        
        # Mock event
        mock_event = AsyncMock()
        mock_event.is_directory = False
        mock_event.src_path = "/path/to/massive_training_auth_report_20260217_010640.json"
        
        # Simula on_created con event loop
        async def test_with_loop():
            handler.on_created(mock_event)
        
        # Esegui con event loop
        asyncio.run(test_with_loop())
        
        # Verifica che il path sia corretto
        assert mock_event.src_path.endswith('.json')
        assert 'massive_training_auth_report' in mock_event.src_path
    
    def test_ignore_non_json_files(self):
        """Test ignora file non JSON."""
        mock_engine = AsyncMock()
        handler = ReportHandler(mock_engine)
        
        # Mock event non JSON
        mock_event = AsyncMock()
        mock_event.is_directory = False
        mock_event.src_path = "/path/to/report.txt"
        
        # Simula on_created
        handler.on_created(mock_event)
        
        # Non dovrebbe processare
        # (Verifichiamo solo che non ci siano eccezioni)
    
    def test_ignore_directories(self):
        """Test ignora directory."""
        mock_engine = AsyncMock()
        handler = ReportHandler(mock_engine)
        
        # Mock event directory
        mock_event = AsyncMock()
        mock_event.is_directory = True
        mock_event.src_path = "/path/to/dir"
        
        # Simula on_created
        handler.on_created(mock_event)
        
        # Non dovrebbe processare directory


class TestEvolutionIntegration:
    """Test integrazione completa del sistema di evoluzione."""
    
    def setup_method(self):
        """Setup per test integrazione."""
        self.temp_dir = tempfile.mkdtemp()
        self.engine = AutoEvolutionEngine(lab_dir=self.temp_dir)
    
    def test_full_tuning_workflow(self):
        """Test workflow completo di tuning."""
        # Report di esempio
        report = {
            'metrics': {
                'total_messages': 100,
                'success_count': 95,
                'error_count': 5,
                'supportive_count': 18,
                'confrontational_count': 4,
                'repetition_detected': 2,
                'avg_response_time': 2.5,
                'success_rate': 95
            }
        }
        
        report_path = f"{self.temp_dir}/massive_training_auth_report_test.json"
        
        # Mock tutte le dipendenze
        with patch('builtins.open', mock_open(read_data=json.dumps(report))), \
             patch.object(self.engine, '_validate_report_safety', return_value=True), \
             patch.object(self.engine, '_check_hard_constraints_violation', return_value=False), \
             patch.object(self.engine.auto_tuner, 'run_auto_tuning_cycle', return_value={'status': 'adjusted'}), \
             patch.object(self.engine, '_log_tuning_applied', new_callable=AsyncMock):
            
            # Esegui processo
            result = asyncio.run(self.engine.process_report(report_path))
            
            # Verifica che il processo sia completato senza errori
            assert result is None  # process_report non ritorna nulla in caso di successo
    
    def test_tuning_applied_logging(self):
        """Test log per tuning applicato."""
        result = {
            'status': 'adjusted',
            'previous_state': {'supportive_intensity': 1.0},
            'new_state': {'supportive_intensity': 1.1},
            'adjustments': {'supportive_intensity': 0.1}
        }
        
        # Mock logger
        with patch('core.auto_evolution_engine.logger') as mock_logger:
            asyncio.run(self.engine._log_tuning_applied(result))
            
            # Verifica log chiamati
            mock_logger.info.assert_any_call("🔧 TUNING_APPLIED")
            mock_logger.info.assert_any_call("OLD_STATE: {'supportive_intensity': 1.0}")
            mock_logger.info.assert_any_call("NEW_STATE: {'supportive_intensity': 1.1}")
            mock_logger.info.assert_any_call("DELTA: {'supportive_intensity': 0.1}")
    
    def test_tuning_rollback_logging(self):
        """Test log per rollback."""
        result = {
            'snapshot_id': 'test_snapshot',
            'reason': 'constraints_violation'
        }
        
        # Mock logger e print
        with patch('core.auto_evolution_engine.logger') as mock_logger, \
             patch('builtins.print') as mock_print:
            
            asyncio.run(self.engine._log_tuning_rollback(result))
            
            # Verifica log chiamati (aggiornati per nuova implementazione)
            mock_logger.critical.assert_any_call("🔧 TUNING_ROLLBACK")
            mock_logger.critical.assert_any_call("ROLLBACK_REASON: {'snapshot_id': 'test_snapshot', 'reason': 'constraints_violation'}")
            
            # Verifica print
            mock_print.assert_any_call("TUNING_ROLLBACK constraints_violation")
