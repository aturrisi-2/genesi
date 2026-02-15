"""
Tests for Memory Routing - conversational memory references
Tests the memory routing override and memory_context responses.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from core.proactor import Proactor, is_memory_reference
from core.chat_memory import chat_memory
from core.memory_storage import memory_storage
from core.storage import storage


# ═══════════════════════════════════════════════════════════════
# Test: Memory Reference Detection
# ═══════════════════════════════════════════════════════════════

class TestMemoryReferenceDetection:

    def test_memory_reference_patterns(self):
        """Test various memory reference patterns."""
        memory_phrases = [
            "prima",
            "abbiamo parlato",
            "ricordi",
            "ricordarmi",
            "l'altra volta",
            "ieri",
            "di cosa",
            "come mi chiamo",
            "ti ricordi",
            "cosa abbiamo detto",
            "cosa dicevamo",
            "sai cosa",
            "ricordi cosa",
            "mi ricordi",
            "ci siamo detti",
            "avevamo parlato",
            "discusso",
            "avevamo detto"
        ]
        
        for phrase in memory_phrases:
            assert is_memory_reference(f"{phrase} di noi?"), f"Should detect: {phrase}"
            assert is_memory_reference(f"Tu {phrase}?"), f"Should detect: {phrase}"
            assert is_memory_reference(f"Ricordi {phrase}?"), f"Should detect: {phrase}"

    def test_memory_reference_case_insensitive(self):
        """Test case insensitive detection."""
        assert is_memory_reference("PRIMA di noi?")
        assert is_memory_reference("Ricordi AVEVAMO PARLATO?")
        assert is_memory_reference("DI COSA abbiamo detto?")

    def test_non_memory_phrases(self):
        """Test that non-memory phrases are not detected."""
        non_memory = [
            "che tempo fa",
            "notizie di oggi",
            "come stai",
            "ciao",
            "aiutami",
            "spiegami",
            "cos'è",
            "dove si trova"
        ]
        
        for phrase in non_memory:
            assert not is_memory_reference(phrase), f"Should NOT detect: {phrase}"

    def test_partial_matches(self):
        """Test partial matches work correctly."""
        assert is_memory_reference("di cosa abbiamo parlato prima?")
        assert is_memory_reference("ti ricordi il mio nome?")
        assert is_memory_reference("ieri abbiamo detto che...")
        assert is_memory_reference("ricordi cosa ci siamo detti?")


# ═══════════════════════════════════════════════════════════════
# Test: Memory Routing Integration
# ═══════════════════════════════════════════════════════════════

class TestMemoryRoutingIntegration:

    @pytest.fixture
    def proactor(self):
        return Proactor()

    @pytest.fixture
    def setup_user_history(self):
        """Setup a user with conversation history."""
        user_id = "test-memory-user"
        
        # Clear any existing data
        memory_storage.delete(f"chat:{user_id}")
        
        # Add 3 conversation messages
        messages = [
            ("ciao", "Ciao! Come posso aiutarti oggi?", "greeting"),
            ("mi chiamo Mario e vivo a Roma", "Ciao Mario! Piacere di conoscerti. Roma è una bella città.", "identity"),
            ("che tempo fa a Roma?", "Oggi a Roma c'è bel tempo, con temperature piacevoli.", "weather")
        ]
        
        for user_msg, sys_msg, intent in messages:
            chat_memory.add_message(user_id, user_msg, sys_msg, intent)
        
        return user_id

    @pytest.mark.asyncio
    async def test_memory_routing_override(self, proactor, setup_user_history):
        """Test that memory references trigger memory_context intent."""
        user_id = setup_user_history
        
        # Mock the LLM service to avoid actual API calls
        with patch('core.llm_service.llm_service._call_with_protection') as mock_llm:
            mock_llm.return_value = "Ricordo che ti chiami Mario e vivi a Roma. Abbiamo parlato anche del tempo oggi."
            
            # Test memory reference triggers routing
            response, source = await proactor.handle(user_id, "di cosa abbiamo parlato prima?")
            
            # Should have called LLM with memory context
            assert mock_llm.called
            call_args = mock_llm.call_args
            assert call_args[1]['route'] == "memory"
            assert call_args[1]['user_id'] == user_id
            
            # Response should be memory-aware
            assert "Mario" in response or "Roma" in response or "tempo" in response
            assert source == "knowledge"

    @pytest.mark.asyncio
    async def test_memory_routing_with_no_history(self, proactor):
        """Test memory routing with no conversation history."""
        user_id = "new-user-no-history"
        
        # Clear any existing data
        memory_storage.delete(f"chat:{user_id}")
        
        # With no history, memory routing should NOT be triggered
        # It should go through normal routing (relational in this case)
        response, source = await proactor.handle(user_id, "di cosa abbiamo parlato?")
        
        # Should get normal response (not memory-specific)
        assert response is not None and len(response) > 0
        # Should NOT contain memory-specific fallback text
        assert "abbastanza" not in response.lower() and "conversare" not in response.lower()

    @pytest.mark.asyncio
    async def test_memory_routing_bypasses_classifier(self, proactor, setup_user_history):
        """Test that memory routing bypasses intent classifier."""
        user_id = setup_user_history
        
        with patch('core.intent_classifier.intent_classifier.classify') as mock_classify:
            with patch('core.llm_service.llm_service._call_with_protection') as mock_llm:
                mock_llm.return_value = "Ricordo la nostra conversazione..."
                
                # Memory reference should bypass classifier
                response, source = await proactor.handle(user_id, "ricordi cosa ci siamo detti?")
                
                # Classifier should NOT be called
                assert not mock_classify.called
                
                # LLM should be called with memory route
                assert mock_llm.called
                assert mock_llm.call_args[1]['route'] == "memory"

    @pytest.mark.asyncio
    async def test_non_memory_uses_normal_routing(self, proactor, setup_user_history):
        """Test that non-memory messages use normal routing."""
        user_id = setup_user_history
        
        with patch('core.intent_classifier.intent_classifier.classify') as mock_classify:
            mock_classify.return_value = "greeting"
            
            # Non-memory message should use normal routing
            response, source = await proactor.handle(user_id, "come stai?")
            
            # Classifier should be called
            assert mock_classify.called

    @pytest.mark.asyncio
    async def test_memory_context_with_llm_failure(self, proactor, setup_user_history):
        """Test memory context response when LLM fails."""
        user_id = setup_user_history
        
        with patch('core.llm_service.llm_service._call_with_protection') as mock_llm:
            mock_llm.return_value = None  # LLM failure
            
            response, source = await proactor.handle(user_id, "ti ricordi di me?")
            
            # Should get fallback response
            assert "ricordo" in response.lower() or "scambi" in response.lower()

    @pytest.mark.asyncio
    async def test_memory_context_error_handling(self, proactor, setup_user_history):
        """Test error handling in memory context."""
        user_id = setup_user_history
        
        with patch('core.chat_memory.chat_memory.get_messages') as mock_get:
            mock_get.side_effect = Exception("Memory error")
            
            response, source = await proactor.handle(user_id, "di cosa abbiamo detto?")
            
            # Should get error fallback
            assert "dispiace" in response.lower() or "problema" in response.lower()

    @pytest.mark.asyncio
    async def test_complete_memory_flow(self, proactor):
        """Test complete flow: new user -> conversation -> memory reference."""
        user_id = "complete-flow-user"
        
        # Clear any existing data
        memory_storage.delete(f"chat:{user_id}")
        
        # Mock LLM for consistent responses
        with patch('core.llm_service.llm_service._call_with_protection') as mock_llm:
            mock_llm.return_value = "Ciao! Piacere di conoscerti."
            
            # 1. First message - greeting
            response1, source1 = await proactor.handle(user_id, "ciao")
            assert response1
            
            # Manually add to chat memory since proactor doesn't automatically save responses
            chat_memory.add_message(user_id, "ciao", response1, "greeting")
            
            # 2. Second message - identity
            mock_llm.return_value = "Ho capito, grazie per avermelo detto."
            response2, source2 = await proactor.handle(user_id, "mi chiamo Laura")
            assert response2
            chat_memory.add_message(user_id, "mi chiamo Laura", response2, "identity")
            
            # 3. Third message - weather
            mock_llm.return_value = "Oggi c'è bel tempo."
            response3, source3 = await proactor.handle(user_id, "che tempo fa?")
            assert response3
            chat_memory.add_message(user_id, "che tempo fa?", response3, "weather")
            
            # 4. Memory reference - should trigger memory routing
            mock_llm.return_value = "Ricordo che ti chiami Laura e abbiamo parlato del tempo."
            response4, source4 = await proactor.handle(user_id, "di cosa abbiamo parlato prima?")
            
            # Should be memory-aware
            assert "Laura" in response4 or "tempo" in response4
            assert mock_llm.call_args[1]['route'] == "memory"


# ═══════════════════════════════════════════════════════════════
# Test: Regression - Other Routes Still Work
# ═══════════════════════════════════════════════════════════════

class TestRegressionOtherRoutes:

    @pytest.fixture
    def proactor(self):
        return Proactor()

    @pytest.mark.asyncio
    async def test_greeting_still_works(self, proactor):
        """Test that greeting messages still work normally."""
        user_id = "greeting-user"
        
        with patch('core.llm_service.llm_service._call_with_protection') as mock_llm:
            mock_llm.return_value = "Ciao! Come posso aiutarti?"
            
            response, source = await proactor.handle(user_id, "ciao")
            
            # Should use normal routing (not memory)
            assert mock_llm.called
            assert mock_llm.call_args[1]['route'] != "memory"

    @pytest.mark.asyncio
    async def test_weather_still_works(self, proactor):
        """Test that weather requests still work."""
        user_id = "weather-user"
        
        with patch('core.tool_services.tool_service.get_weather') as mock_weather:
            mock_weather.return_value = "Oggi c'è sole."
            
            response, source = await proactor.handle(user_id, "che tempo fa a Roma?")
            
            assert "sole" in response
            assert mock_weather.called

    @pytest.mark.asyncio
    async def test_news_still_works(self, proactor):
        """Test that news requests still work."""
        user_id = "news-user"
        
        with patch('core.tool_services.tool_service.get_news') as mock_news:
            mock_news.return_value = "Ultime notizie:..."
            
            response, source = await proactor.handle(user_id, "notizie di oggi")
            
            assert "notizie" in response.lower()
            assert mock_news.called

    @pytest.mark.asyncio
    async def test_profile_still_works(self, proactor):
        """Test that identity questions still work."""
        user_id = "profile-user"
        
        # Setup a profile for the user
        profile_data = {
            "name": "Mario",
            "city": "Roma",
            "age": 30
        }
        await storage.save(f"profile:{user_id}", profile_data)
        
        # Test actual identity question handling
        response, source = await proactor.handle(user_id, "come mi chiamo?")
        
        # Should get a response containing the name from the profile
        assert "Mario" in response


if __name__ == "__main__":
    # Run tests
    asyncio.run(pytest.main([__file__, "-v"]))
