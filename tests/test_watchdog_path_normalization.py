"""
Test Watchdog Path Normalization
Verifica che i path watchdog vengano normalizzati correttamente senza duplicazioni
"""

import pytest
import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from watchdog.events import FileSystemEvent
from core.auto_evolution_engine import ReportHandler, AutoEvolutionEngine

class TestWatchdogPathNormalization:
    
    @pytest.fixture
    def evolution_engine(self):
        """Mock evolution engine per test."""
        engine = Mock(spec=AutoEvolutionEngine)
        engine.main_loop = Mock()
        return engine
    
    @pytest.fixture
    def report_handler(self, evolution_engine):
        """Report handler per test."""
        return ReportHandler(evolution_engine)
    
    def test_absolute_path_normalization(self, report_handler, evolution_engine):
        """Test normalizzazione path assoluto."""
        try:
            # Crea file temporaneo nella directory corrente
            current_dir = os.getcwd()
            temp_filename = "test_massive_training_auth_report.json"
            temp_path = os.path.join(current_dir, temp_filename)
            
            with open(temp_path, 'w') as f:
                json.dump({"test": "data"}, f)
            
            # Mock evento watchdog con path relativo
            event = Mock(spec=FileSystemEvent)
            event.is_directory = False
            event.src_path = temp_filename  # Solo filename
            
            # Mock process_report per catturare la chiamata
            received_path = None
            
            async def mock_process_report(path):
                nonlocal received_path
                received_path = path
            
            evolution_engine.process_report = mock_process_report
            
            # Cattura la chiamata a run_coroutine_threadsafe
            called_coroutine = None
            
            def capture_run_coroutine(coro, loop):
                nonlocal called_coroutine
                called_coroutine = coro
                mock_future = Mock()
                return mock_future
            
            with patch('asyncio.run_coroutine_threadsafe', side_effect=capture_run_coroutine):
                # Simula evento
                report_handler.on_created(event)
                
                # Esegui la coroutine catturata per ottenere il path
                if called_coroutine:
                    asyncio.run(called_coroutine)
                
                # Verifica che il path sia stato normalizzato correttamente
                expected_path = os.path.abspath(temp_path)
                assert received_path == expected_path, f"Expected {expected_path}, got {received_path}"
                assert os.path.isabs(received_path), "Path should be absolute"
            
            print("✅ Test absolute path normalization superato")
            
        finally:
            # Pulizia
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_path_deduplication_with_normalized_paths(self, report_handler, evolution_engine):
        """Test deduplicazione con path normalizzati."""
        try:
            # Crea file temporaneo nella directory corrente
            current_dir = os.getcwd()
            temp_filename = "test_massive_training_auth_report_dup.json"
            temp_path = os.path.join(current_dir, temp_filename)
            
            with open(temp_path, 'w') as f:
                json.dump({"test": "data"}, f)
            
            # Mock evento watchdog
            event = Mock(spec=FileSystemEvent)
            event.is_directory = False
            event.src_path = temp_path  # Path assoluto
            
            # Mock process_report
            with patch('asyncio.run_coroutine_threadsafe') as mock_run_coroutine:
                mock_future = Mock()
                mock_run_coroutine.return_value = mock_future
                
                # Primo evento - dovrebbe processare
                report_handler.on_created(event)
                assert mock_run_coroutine.call_count == 1, "First event should be processed"
                
                # Secondo evento stesso file - dovrebbe ignorare
                report_handler.on_created(event)
                assert mock_run_coroutine.call_count == 1, "Duplicate event should be ignored"
            
            print("✅ Test path deduplication superato")
            
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_guard_clause_invalid_path(self, report_handler, evolution_engine):
        """Test guard clause per path invalidi."""
        # Mock evento con path inesistente
        event = Mock(spec=FileSystemEvent)
        event.is_directory = False
        event.src_path = "/path/that/does/not/exist.json"
        
        # Mock process_report
        with patch.object(evolution_engine, 'process_report') as mock_process:
            with patch('asyncio.run_coroutine_threadsafe') as mock_run_coroutine:
                # Simula evento
                report_handler.on_created(event)
                
                # Verifica che process_report NON sia stato chiamato
                mock_run_coroutine.assert_not_called()
                mock_process.assert_not_called()
        
        print("✅ Test guard clause invalid path superato")
    
    def test_path_logging(self, report_handler, evolution_engine, caplog):
        """Test logging path normalization."""
        import logging
        import sys
        from io import StringIO

        try:
            # Crea file temporaneo nella directory corrente
            current_dir = os.getcwd()
            temp_filename = "test_massive_training_auth_report_log.json"
            temp_path = os.path.join(current_dir, temp_filename)

            with open(temp_path, 'w') as f:
                json.dump({"test": "data"}, f)

            # Mock evento watchdog
            event = Mock(spec=FileSystemEvent)
            event.is_directory = False
            event.src_path = temp_filename  # Path relativo

            # Cattura stdout (log() custom) + caplog (logger.debug/info)
            captured_output = StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured_output

            try:
                with caplog.at_level(logging.DEBUG), patch('asyncio.run_coroutine_threadsafe') as mock_run_coroutine:
                    mock_future = Mock()
                    mock_run_coroutine.return_value = mock_future

                    # Simula evento
                    report_handler.on_created(event)

                    # Combina stdout + caplog
                    output = captured_output.getvalue() + caplog.text

                    # Verifica log path
                    assert f"WATCHDOG_EVENT_RECEIVED path={temp_filename}" in output
                    assert f"NORMALIZED_PATH path={os.path.abspath(temp_path)}" in output
                    assert f"REPORT_DETECTED" in output and os.path.abspath(temp_path) in output

            finally:
                sys.stdout = old_stdout
        
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        
        print("✅ Test path logging superato")
    
    def test_no_double_concatenation(self, report_handler, evolution_engine):
        """Test che non avvenga doppia concatenazione del path."""
        try:
            # Crea file temporaneo nella directory corrente
            current_dir = os.getcwd()
            temp_filename = "test_massive_training_auth_report_concat.json"
            temp_path = os.path.join(current_dir, temp_filename)
            
            with open(temp_path, 'w') as f:
                json.dump({"test": "data"}, f)
            
            # Mock evento watchdog con path assoluto
            event = Mock(spec=FileSystemEvent)
            event.is_directory = False
            event.src_path = temp_path  # Già assoluto
            
            # Mock process_report per catturare path passato
            received_path = None
            
            def mock_process_report(path):
                nonlocal received_path
                received_path = path
                return asyncio.sleep(0)
            
            evolution_engine.process_report = mock_process_report
            
            with patch('asyncio.run_coroutine_threadsafe') as mock_run_coroutine:
                mock_future = Mock()
                mock_run_coroutine.return_value = mock_future
                
                # Simula evento
                report_handler.on_created(event)
                
                # Verifica che il path ricevuto sia esatto e non duplicato
                assert received_path == temp_path, f"Path should be exactly {temp_path}, got {received_path}"
                # Verifica che non ci siano duplicazioni del filename nel path
                filename = os.path.basename(temp_path)
                path_parts = received_path.replace("\\", "/").split("/")
                filename_count = sum(1 for part in path_parts if filename in part)
                assert filename_count == 1, f"Filename {filename} appears {filename_count} times in path"
            
            print("✅ Test no double concatenation superato")
            
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_relative_to_absolute_conversion(self, report_handler, evolution_engine):
        """Test conversione da relativo a assoluto."""
        try:
            # Crea file temporaneo nella directory corrente
            current_dir = os.getcwd()
            temp_filename = "test_massive_training_auth_report_rel.json"
            temp_path = os.path.join(current_dir, temp_filename)
            
            with open(temp_path, 'w') as f:
                json.dump({"test": "data"}, f)
            
            # Mock evento watchdog con path relativo
            event = Mock(spec=FileSystemEvent)
            event.is_directory = False
            event.src_path = temp_filename  # Solo filename
            
            # Mock process_report per catturare path
            received_path = None
            
            def mock_process_report(path):
                nonlocal received_path
                received_path = path
                return asyncio.sleep(0)
            
            evolution_engine.process_report = mock_process_report
            
            with patch('asyncio.run_coroutine_threadsafe') as mock_run_coroutine:
                mock_future = Mock()
                mock_run_coroutine.return_value = mock_future
                
                # Simula evento
                report_handler.on_created(event)
                
                # Verifica conversione a assoluto
                expected_absolute = os.path.abspath(temp_filename)
                assert received_path == expected_absolute, f"Expected absolute {expected_absolute}, got {received_path}"
                assert os.path.isabs(received_path), "Received path should be absolute"
            
            print("✅ Test relative to absolute conversion superato")
            
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
