"""
Tests for Reminder System - complete reminder functionality
Tests reminder engine, parsing, creation, listing, and integration.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import pytest
from unittest.mock import patch, AsyncMock
from datetime import datetime, timedelta
from pathlib import Path

from core.reminder_engine import ReminderEngine, reminder_engine
from core.proactor import Proactor, is_reminder_request, is_list_reminders_request


# ═══════════════════════════════════════════════════════════════
# Test: Reminder Engine Core Functions
# ═══════════════════════════════════════════════════════════════

class TestReminderEngine:
    
    @pytest.fixture
    def engine(self):
        """Create a fresh reminder engine for testing."""
        return ReminderEngine()
    
    @pytest.fixture
    def test_user(self):
        return "test-reminder-user"
    
    @pytest.fixture(autouse=True)
    def cleanup_reminders(self):
        """Clean up all reminders after each test."""
        import shutil
        reminders_dir = Path("data/reminders")
        
        # Cleanup before test - remove all JSON files but keep directory
        if reminders_dir.exists():
            for file_path in reminders_dir.glob("*.json"):
                file_path.unlink()
        
        yield
        
        # Cleanup after test - remove all JSON files but keep directory
        if reminders_dir.exists():
            for file_path in reminders_dir.glob("*.json"):
                file_path.unlink()
    
    def test_create_reminder(self, engine, test_user):
        """Test basic reminder creation."""
        text = "chiamare il medico"
        reminder_time = datetime.now() + timedelta(hours=1)
        
        reminder_id = engine.create_reminder(test_user, text, reminder_time)
        
        assert reminder_id is not None
        assert len(reminder_id) > 0  # Should be a UUID
        
        # Verify it was saved
        reminders = engine.list_reminders(test_user)
        assert len(reminders) == 1
        assert reminders[0]["text"] == text
        assert reminders[0]["id"] == reminder_id
        assert reminders[0]["status"] == "pending"
    
    def test_list_reminders_chronological(self, engine, test_user):
        """Test reminders are listed in chronological order."""
        now = datetime.now()
        
        # Create reminders in random order
        r1_id = engine.create_reminder(test_user, "task 1", now + timedelta(hours=3))
        r2_id = engine.create_reminder(test_user, "task 2", now + timedelta(hours=1))
        r3_id = engine.create_reminder(test_user, "task 3", now + timedelta(hours=2))
        
        reminders = engine.list_reminders(test_user)
        
        # Should be in chronological order
        assert len(reminders) == 3
        assert reminders[0]["text"] == "task 2"  # 1 hour from now
        assert reminders[1]["text"] == "task 3"  # 2 hours from now
        assert reminders[2]["text"] == "task 1"  # 3 hours from now
    
    def test_get_due_reminders(self, engine, test_user):
        """Test getting due reminders."""
        now = datetime.now()
        
        # Create reminders: one due, one future
        engine.create_reminder(test_user, "past task", now - timedelta(hours=1))
        engine.create_reminder(test_user, "future task", now + timedelta(hours=1))
        
        due_reminders = engine.get_due_reminders()
        
        # Should find only the past task
        assert len(due_reminders) == 1
        assert due_reminders[0]["text"] == "past task"
        assert due_reminders[0]["user_id"] == test_user
    
    def test_mark_reminder_done(self, engine, test_user):
        """Test marking reminder as done."""
        reminder_time = datetime.now() - timedelta(hours=1)
        reminder_id = engine.create_reminder(test_user, "test task", reminder_time)
        
        # Mark as done
        success = engine.mark_reminder_done(test_user, reminder_id)
        assert success is True
        
        # Verify status changed
        reminders = engine.list_reminders(test_user)
        assert len(reminders) == 1
        assert reminders[0]["status"] == "done"
        assert "done_at" in reminders[0]
    
    def test_cancel_reminder(self, engine, test_user):
        """Test cancelling a reminder."""
        reminder_time = datetime.now() + timedelta(hours=1)
        reminder_id = engine.create_reminder(test_user, "test task", reminder_time)
        
        # Cancel reminder
        success = engine.cancel_reminder(test_user, reminder_id)
        assert success is True
        
        # Verify status changed
        reminders = engine.list_reminders(test_user)
        assert len(reminders) == 1
        assert reminders[0]["status"] == "cancelled"
        assert "cancelled_at" in reminders[0]
    
    def test_delete_reminder(self, engine, test_user):
        """Test deleting a reminder completely."""
        reminder_time = datetime.now() + timedelta(hours=1)
        reminder_id = engine.create_reminder(test_user, "test task", reminder_time)
        
        # Delete reminder
        success = engine.delete_reminder(test_user, reminder_id)
        assert success is True
        
        # Verify it's gone
        reminders = engine.list_reminders(test_user)
        assert len(reminders) == 0
    
    def test_format_reminders_list(self, engine, test_user):
        """Test formatting reminders for display."""
        now = datetime.now()
        engine.create_reminder(test_user, "task 1", now + timedelta(hours=1))
        engine.create_reminder(test_user, "task 2", now + timedelta(hours=2))
        
        reminders = engine.list_reminders(test_user)
        formatted = engine.format_reminders_list(reminders)
        
        assert "I tuoi promemoria:" in formatted
        assert "task 1" in formatted
        assert "task 2" in formatted
        assert "⏰" in formatted  # Pending icon
    
    def test_format_empty_reminders_list(self, engine, test_user):
        """Test formatting empty reminders list."""
        formatted = engine.format_reminders_list([])
        
        assert formatted == "Non hai promemoria impostati."
    
    def test_user_isolation(self, engine):
        """Test that reminders are isolated per user."""
        user1 = "user1"
        user2 = "user2"
        
        now = datetime.now()
        engine.create_reminder(user1, "user1 task", now + timedelta(hours=1))
        engine.create_reminder(user2, "user2 task", now + timedelta(hours=1))
        
        # Each user should only see their own reminders
        user1_reminders = engine.list_reminders(user1)
        user2_reminders = engine.list_reminders(user2)
        
        assert len(user1_reminders) == 1
        assert user1_reminders[0]["text"] == "user1 task"
        
        assert len(user2_reminders) == 1
        assert user2_reminders[0]["text"] == "user2 task"


# ═══════════════════════════════════════════════════════════════
# Test: Reminder Detection in Proactor
# ═══════════════════════════════════════════════════════════════

class TestReminderDetection:
    
    def test_reminder_request_detection(self):
        """Test detection of reminder creation requests."""
        reminder_phrases = [
            "ricordami di chiamare il medico",
            "ricordamelo domani",
            "imposta un promemoria per la riunione",
            "metti un promemoria per le 18",
            "promemoria: comprare il pane"
        ]
        
        for phrase in reminder_phrases:
            assert is_reminder_request(phrase), f"Should detect: {phrase}"
    
    def test_list_reminders_detection(self):
        """Test detection of reminder list requests."""
        list_phrases = [
            "quali appuntamenti ho?",
            "cosa devo fare domani?",
            "promemoria attivi",
            "i miei promemoria",
            "elenco promemoria",
            "lista appuntamenti",
            "cosa ho da fare oggi?",
            "appuntamenti oggi"
        ]
        
        for phrase in list_phrases:
            assert is_list_reminders_request(phrase), f"Should detect: {phrase}"
    
    def test_non_reminder_phrases(self):
        """Test that non-reminder phrases are not detected."""
        non_reminder = [
            "che tempo fa",
            "ciao come stai",
            "aiutami",
            "spiegami",
            "non mi ricordo",
            "mi sono dimenticato"
        ]
        
        for phrase in non_reminder:
            assert not is_reminder_request(phrase), f"Should NOT detect as reminder: {phrase}"
            assert not is_list_reminders_request(phrase), f"Should NOT detect as list: {phrase}"


# ═══════════════════════════════════════════════════════════════
# Test: Reminder Parsing
# ═══════════════════════════════════════════════════════════════

class TestReminderParsing:
    
    @pytest.fixture
    def proactor(self):
        return Proactor()
    
    def test_parse_tomorrow_reminder(self, proactor):
        """Test parsing 'domani' reminders."""
        message = "ricordami di chiamare il medico domani alle 18"
        text, reminder_time = proactor._parse_reminder_request(message)
        
        assert text == "chiamare il medico"
        assert reminder_time is not None
        
        # Should be tomorrow at 18:00
        tomorrow = datetime.now() + timedelta(days=1)
        expected_time = tomorrow.replace(hour=18, minute=0)
        
        # Allow small time difference for processing
        time_diff = abs((reminder_time - expected_time).total_seconds())
        assert time_diff < 60  # Within 1 minute
    
    def test_parse_today_reminder(self, proactor):
        """Test parsing 'oggi' reminders."""
        message = "ricordami di comprare il pane oggi alle 15"
        text, reminder_time = proactor._parse_reminder_request(message)
        
        assert text == "comprare il pane"
        assert reminder_time is not None
        
        # Should be today at 15:00 (or tomorrow if 15:00 has passed)
        now = datetime.now()
        expected_time = now.replace(hour=15, minute=0)
        if expected_time <= now:
            expected_time += timedelta(days=1)
        
        time_diff = abs((reminder_time - expected_time).total_seconds())
        assert time_diff < 60
    
    def test_parse_weekday_reminder(self, proactor):
        """Test parsing weekday reminders."""
        message = "ricordami di andare in banca lunedì alle 9"
        text, reminder_time = proactor._parse_reminder_request(message)
        
        assert text == "andare in banca"
        assert reminder_time is not None
        
        # Should be next Monday at 9:00
        now = datetime.now()
        days_ahead = 0 - now.weekday()  # Monday is 0
        if days_ahead <= 0:
            days_ahead += 7
        expected_time = now.replace(hour=9, minute=0) + timedelta(days=days_ahead)
        
        time_diff = abs((reminder_time - expected_time).total_seconds())
        assert time_diff < 60
    
    def test_parse_default_time(self, proactor):
        """Test parsing with no time specified (defaults to 9:00)."""
        message = "ricordami di fare la spesa domani"
        text, reminder_time = proactor._parse_reminder_request(message)
        
        assert text == "fare la spesa"
        assert reminder_time is not None
        
        # Should be tomorrow at 9:00
        tomorrow = datetime.now() + timedelta(days=1)
        expected_time = tomorrow.replace(hour=9, minute=0)
        
        time_diff = abs((reminder_time - expected_time).total_seconds())
        assert time_diff < 60
    
    def test_parse_invalid_message(self, proactor):
        """Test parsing invalid reminder messages."""
        invalid_messages = [
            "ricordami",  # No task
            "vado al cinema domani",  # No reminder keyword
            "che tempo fa domani"  # Not a reminder
        ]
        
        for message in invalid_messages:
            text, reminder_time = proactor._parse_reminder_request(message)
            assert text is None
            assert reminder_time is None


# ═══════════════════════════════════════════════════════════════
# Test: Integration with Proactor
# ═══════════════════════════════════════════════════════════════

class TestProactorIntegration:
    
    @pytest.fixture
    def proactor(self):
        return Proactor()
    
    @pytest.fixture
    def test_user(self):
        return "integration-user"
    
    @pytest.fixture(autouse=True)
    def cleanup_integration_reminders(self):
        """Clean up all reminders after each integration test."""
        reminders_dir = Path("data/reminders")
        
        # Cleanup before test - remove all JSON files but keep directory
        if reminders_dir.exists():
            for file_path in reminders_dir.glob("*.json"):
                file_path.unlink()
        
        yield
        
        # Cleanup after test - remove all JSON files but keep directory
        if reminders_dir.exists():
            for file_path in reminders_dir.glob("*.json"):
                file_path.unlink()
    
    @pytest.mark.asyncio
    async def test_reminder_creation_flow(self, proactor, test_user):
        """Test complete reminder creation flow."""
        message = "ricordami di chiamare il medico domani alle 18"
        
        response = await proactor._handle_reminder_creation(test_user, message)
        
        # Should get confirmation message
        assert "Perfetto" in response
        assert "chiamare il medico" in response
        assert response.count("domani") > 0 or response.count("18") > 0
        
        # Verify reminder was created
        reminders = reminder_engine.list_reminders(test_user)
        assert len(reminders) == 1
        assert reminders[0]["text"] == "chiamare il medico"
    
    @pytest.mark.asyncio
    async def test_reminder_list_flow(self, proactor, test_user):
        """Test reminder listing flow."""
        # Create some reminders
        now = datetime.now()
        reminder_engine.create_reminder(test_user, "task 1", now + timedelta(hours=1))
        reminder_engine.create_reminder(test_user, "task 2", now + timedelta(hours=2))
        
        message = "quali appuntamenti ho?"
        response = await proactor._handle_reminder_list(test_user, message)
        
        # Should get formatted list
        assert "I tuoi promemoria:" in response
        assert "task 1" in response
        assert "task 2" in response
    
    @pytest.mark.asyncio
    async def test_empty_reminder_list(self, proactor, test_user):
        """Test listing when no reminders exist."""
        message = "cosa devo fare?"
        response = await proactor._handle_reminder_list(test_user, message)
        
        assert response == "Non hai promemoria impostati."
    
    @pytest.mark.asyncio
    async def test_invalid_reminder_request(self, proactor, test_user):
        """Test handling of invalid reminder requests."""
        message = "ricordami"  # No task specified
        
        response = await proactor._handle_reminder_creation(test_user, message)
        
        # Should get helpful error message
        assert "Non ho capito" in response
        assert "prova a dire" in response.lower()


if __name__ == "__main__":
    # Run tests
    asyncio.run(pytest.main([__file__, "-v"]))
