"""
Test Success Rate Calculation Bug Fix
Verifica che success_rate venga calcolato correttamente come success_count/total_messages
"""

import pytest
import json
import tempfile
import os
from core.auto_tuner import AutoTuner

class TestSuccessRateCalculation:
    
    @pytest.fixture
    def auto_tuner(self):
        """AutoTuner instance per test."""
        return AutoTuner()
    
    def test_success_rate_calculation_correct(self, auto_tuner):
        """Test calcolo success_rate corretto."""
        try:
            # Caso 1: 98/100 → 0.98
            report_data = {
                "metrics": {
                    "total_messages": 100,
                    "success_count": 98,
                    "error_count": 2,
                    "supportive_count": 18,
                    "confrontational_count": 3,
                    "repetition_detected": 1,
                    "avg_response_time": 2.2
                }
            }
            
            # Crea file temporaneo
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(report_data, f)
                temp_path = f.name
            
            # Analizza report
            analysis = auto_tuner.analyze_report(temp_path)
            
            # Verifica calcolo
            assert analysis['success_rate'] == 0.98, f"Expected 0.98, got {analysis['success_rate']}"
            
            print("✅ Test success_rate 98/100 → 0.98 superato")
            
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_success_rate_zero_success(self, auto_tuner):
        """Test success_rate con 0 success."""
        try:
            # Caso 2: 0/100 → 0.0
            report_data = {
                "metrics": {
                    "total_messages": 100,
                    "success_count": 0,
                    "error_count": 100,
                    "supportive_count": 10,
                    "confrontational_count": 2,
                    "repetition_detected": 1,
                    "avg_response_time": 2.5
                }
            }
            
            # Crea file temporaneo
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(report_data, f)
                temp_path = f.name
            
            # Analizza report
            analysis = auto_tuner.analyze_report(temp_path)
            
            # Verifica calcolo
            assert analysis['success_rate'] == 0.0, f"Expected 0.0, got {analysis['success_rate']}"
            
            print("✅ Test success_rate 0/100 → 0.0 superato")
            
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_success_rate_zero_total(self, auto_tuner):
        """Test success_rate con total_messages = 0."""
        try:
            # Caso 3: total_messages = 0 → 0.0 (division by zero protection)
            report_data = {
                "metrics": {
                    "total_messages": 0,
                    "success_count": 0,
                    "error_count": 0,
                    "supportive_count": 0,
                    "confrontational_count": 0,
                    "repetition_detected": 0,
                    "avg_response_time": 0.0
                }
            }
            
            # Crea file temporaneo
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(report_data, f)
                temp_path = f.name
            
            # Analizza report
            analysis = auto_tuner.analyze_report(temp_path)
            
            # Verifica calcolo
            assert analysis['success_rate'] == 0.0, f"Expected 0.0, got {analysis['success_rate']}"
            
            print("✅ Test success_rate total_messages=0 → 0.0 superato")
            
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_success_rate_clamping(self, auto_tuner):
        """Test clamping success_rate in range 0.0-1.0."""
        try:
            # Caso 4: Valori anomali - verifica clamping
            report_data = {
                "metrics": {
                    "total_messages": 50,
                    "success_count": 60,  # Più del totale
                    "error_count": 0,
                    "supportive_count": 10,
                    "confrontational_count": 2,
                    "repetition_detected": 1,
                    "avg_response_time": 2.0
                }
            }
            
            # Crea file temporaneo
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(report_data, f)
                temp_path = f.name
            
            # Analizza report
            analysis = auto_tuner.analyze_report(temp_path)
            
            # Verifica clamping a 1.0
            assert analysis['success_rate'] == 1.0, f"Expected 1.0 (clamped), got {analysis['success_rate']}"
            
            print("✅ Test success_rate clamping superato")
            
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_success_rate_logging(self, auto_tuner):
        """Test logging success_rate calculation."""
        try:
            # Crea report
            report_data = {
                "metrics": {
                    "total_messages": 100,
                    "success_count": 95,
                    "error_count": 5,
                    "supportive_count": 18,
                    "confrontational_count": 3,
                    "repetition_detected": 1,
                    "avg_response_time": 2.2
                }
            }
            
            # Crea file temporaneo
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(report_data, f)
                temp_path = f.name
            
            # Cattura stdout
            import sys
            from io import StringIO
            captured_output = StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured_output
            
            try:
                # Analizza report
                analysis = auto_tuner.analyze_report(temp_path)
                
                # Recupera output
                output = captured_output.getvalue()
                
                # Verifica log
                assert "SUCCESS_RATE_CALCULATED success=95 total=100 rate=0.95" in output
                
            finally:
                sys.stdout = old_stdout
        
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        
        print("✅ Test success_rate logging superato")
    
    def test_success_rate_missing_fields(self, auto_tuner):
        """Test success_rate con campi mancanti."""
        try:
            # Report senza success_count
            report_data = {
                "metrics": {
                    "total_messages": 100,
                    "error_count": 5,
                    "supportive_count": 18,
                    "confrontational_count": 3,
                    "repetition_detected": 1,
                    "avg_response_time": 2.2
                }
            }
            
            # Crea file temporaneo
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(report_data, f)
                temp_path = f.name
            
            # Analizza report
            analysis = auto_tuner.analyze_report(temp_path)
            
            # Verifica default a 0
            assert analysis['success_rate'] == 0.0, f"Expected 0.0 (default), got {analysis['success_rate']}"
            
            print("✅ Test success_rate missing fields superato")
            
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
