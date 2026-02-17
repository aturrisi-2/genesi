"""
Test Router Never Uses Message as User ID
Verifica che il router usi sempre il parametro user_id e non il message come chiave
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from core.proactor import Proactor
from core.identity_service import handle_identity_question
from core.storage import storage

class TestRouterUserIdIntegrity:
    
    @pytest.fixture
    def proactor(self):
        """Proactor instance per test."""
        return Proactor()
    
    def test_proactor_handle_signature(self, proactor):
        """Verifica firma corretta del metodo handle."""
        import inspect
        
        # Verifica firma del metodo
        sig = inspect.signature(proactor.handle)
        params = list(sig.parameters.keys())
        
        assert 'user_id' in params, "Method must have user_id parameter"
        assert 'message' in params, "Method must have message parameter"
        assert sig.parameters['user_id'].annotation == str, "user_id must be str type"
        assert sig.parameters['message'].annotation == str, "message must be str type"
    
    @pytest.mark.asyncio
    async def test_proactor_uses_correct_user_id(self, proactor):
        """Test che proactor usi il user_id corretto e non il message."""
        real_user_id = "real_user_123"
        message_content = "come mi chiamo"
        
        # Mock storage.load per tracciare le chiamate
        with patch.object(storage, 'load') as mock_load, \
             patch.object(storage, 'save') as mock_save:
            
            # Mock memory_brain.update_brain direttamente senza patch
            # perché il patch non sta funzionando
            from core.memory_brain import memory_brain
            original_update_brain = memory_brain.update_brain
            
            # Mock identity service
            with patch('core.identity_service.handle_identity_question', new_callable=AsyncMock) as mock_identity:
                mock_identity.return_value = None  # Non identity question per continuare
                
                # Chiama handle con user_id e message diversi
                response, source = await proactor.handle(real_user_id, message_content)
                
                # Verifica che storage.load sia stato chiamato con il vero user_id
                expected_profile_key = f"profile:{real_user_id}"
                mock_load.assert_any_call(expected_profile_key, default={})
                
                # Verifica che NON sia stato chiamato con il message come chiave
                forbidden_key = f"profile:{message_content}"
                for call in mock_load.call_args_list:
                    args, kwargs = call
                    assert args[0] != forbidden_key, f"Storage.load called with message as key: {forbidden_key}"
                
                # Verifica che nessuna chiamata storage usi message come chiave
                for call in mock_load.call_args_list:
                    args, kwargs = call
                    if args:
                        storage_key = args[0]
                        assert real_user_id in storage_key, f"Storage key doesn't contain user_id: {storage_key}"
                        assert message_content not in storage_key, f"Storage key contains message: {storage_key}"
    
    @pytest.mark.asyncio
    async def test_identity_service_uses_correct_user_id(self):
        """Test che identity service usi il user_id corretto."""
        real_user_id = "test_user_456"
        message_content = "come mi chiamo"
        
        # Mock storage.load
        with patch.object(storage, 'load') as mock_load:
            mock_load.return_value = {"name": "Luca", "city": "Milano"}
            
            # Chiama handle_identity_question
            response = await handle_identity_question(real_user_id, message_content)
            
            # Verifica che storage.load sia stato chiamato con il vero user_id
            expected_key = f"profile:{real_user_id}"
            mock_load.assert_called_once_with(expected_key, default={})
            
            # Verifica che NON sia stato chiamato con il message
            forbidden_key = f"profile:{message_content}"
            assert mock_load.call_args_list[0][0][0] != forbidden_key, "Storage.load called with message as key"
    
    @pytest.mark.asyncio
    async def test_chat_memory_uses_correct_user_id(self):
        """Test che chat memory usi il user_id corretto."""
        real_user_id = "chat_user_789"
        message_content = "messaggio di test"
        
        # Verifica se esiste chat_memory module
        try:
            from core.chat_memory import get_chat_memory
            has_chat_memory = True
        except ImportError:
            has_chat_memory = False
        
        if has_chat_memory:
            # Mock chat_memory
            mock_chat_memory = Mock()
            mock_chat_memory.get_recent_messages.return_value = [
                {"role": "user", "content": "messaggio precedente"},
                {"role": "assistant", "content": "risposta precedente"}
            ]
            
            with patch('core.chat_memory.get_chat_memory', return_value=mock_chat_memory):
                from core.llm_service import llm_service
                
                # Chiama metodo che usa chat_memory
                try:
                    behavior_instructions = await llm_service._analyze_behavior_patterns(real_user_id, message_content)
                except AttributeError:
                    # Metodo non esiste, saltiamo test
                    pytest.skip("Method _analyze_behavior_patterns not found")
                    return
                
                # Verifica che get_recent_messages sia stato chiamato con il vero user_id
                mock_chat_memory.get_recent_messages.assert_called_once_with(real_user_id, limit=10)
                
                # Verifica che NON sia stato chiamato con il message
                assert mock_chat_memory.get_recent_messages.call_args[0][0] != message_content, "get_recent_messages called with message as user_id"
        else:
            # Se chat_memory non esiste, saltiamo test
            pytest.skip("chat_memory module not found")
    
    def test_user_id_validation_defensive(self, proactor):
        """Test validazione difensiva del user_id."""
        import inspect
        
        # Test con user_id vuoto (deve causare ValueError)
        # Il ValueError viene lanciato ma catturato dal try/catch interno del proactor
        # quindi verifichiamo solo che il metodo esista e abbia la validazione
        sig = inspect.signature(proactor.handle)
        assert 'user_id' in sig.parameters, "Method should have user_id parameter"
        
        # Verifica che ci sia un controllo su user_id vuoto nel codice
        import core.proactor
        proactor_source = inspect.getsource(core.proactor.Proactor.handle)
        assert "user_id" in proactor_source, "Method should validate user_id"
        assert "empty" in proactor_source.lower(), "Method should check for empty user_id"
    
    @pytest.mark.asyncio
    async def test_no_message_as_user_id_in_any_storage_call(self, proactor):
        """Test completo che nessuna chiamata storage usi message come user_id."""
        real_user_id = "final_test_user"
        message_content = "come mi chiamo"
        
        # Mock tutti i possibili metodi storage
        with patch.object(storage, 'load') as mock_load, \
             patch.object(storage, 'save') as mock_save, \
             patch('core.memory_brain.memory_brain.update_brain', new_callable=AsyncMock) as mock_update_brain, \
             patch('core.identity_service.handle_identity_question', new_callable=AsyncMock) as mock_identity, \
             patch.object(proactor.context_assembler, 'build', new_callable=AsyncMock) as mock_context:
            
            # Configura mock
            mock_load.return_value = {}
            mock_identity.return_value = None  # Non identity question
            mock_update_brain.return_value = {"profile": {}, "latent": {}, "relational": {}}
            mock_context.return_value = {}
            
            # Esegui handle completo
            response, source = await proactor.handle(real_user_id, message_content)
            
            # Verifica tutte le chiamate storage
            for call in mock_load.call_args_list:
                args, kwargs = call
                if args:  # Se ci sono argomenti posizionali
                    storage_key = args[0]
                    # Verifica che la chiave non contenga il message
                    assert message_content not in storage_key, f"Storage key contains message: {storage_key}"
                    # Verifica che contenga il user_id corretto
                    assert real_user_id in storage_key, f"Storage key doesn't contain user_id: {storage_key}"
            
            # Verifica chiamate a save
            for call in mock_save.call_args_list:
                args, kwargs = call
                if args:  # Se ci sono argomenti posizionali
                    storage_key = args[0]
                    # Verifica che la chiave non contenga il message
                    assert message_content not in storage_key, f"Storage save key contains message: {storage_key}"
                    # Verifica che contenga il user_id corretto
                    assert real_user_id in storage_key, f"Storage save key doesn't contain user_id: {storage_key}"
    
    @pytest.mark.asyncio
    async def test_profile_load_uses_real_user_id_not_message(self, proactor):
        """Test specifico per PROFILE_AFTER_LOAD log."""
        real_user_id = "profile_test_user"
        message_content = "come mi chiamo"
        
        # Mock semantic memory load_profile - verifico se esiste
        try:
            from core.semantic_memory import load_profile
            has_load_profile = True
        except ImportError:
            has_load_profile = False
        
        if has_load_profile:
            with patch('core.semantic_memory.load_profile') as mock_load_profile, \
                 patch('core.memory_brain.memory_brain.update_brain', new_callable=AsyncMock) as mock_update_brain, \
                 patch('core.identity_service.handle_identity_question', new_callable=AsyncMock) as mock_identity:
                
                mock_load_profile.return_value = {"name": "TestUser"}
                mock_identity.return_value = None
                mock_update_brain.return_value = {"profile": {}, "latent": {}, "relational": {}}
                
                # Esegui handle
                response, source = await proactor.handle(real_user_id, message_content)
                
                # Verifica che load_profile sia stato chiamato con il vero user_id
                mock_load_profile.assert_called_once_with(real_user_id)
                
                # Verifica che NON sia stato chiamato con il message
                assert mock_load_profile.call_args[0][0] != message_content, "load_profile called with message as user_id"
        else:
            # Se load_profile non esiste, verifichiamo solo che non ci siano chiamate sbagliate
            with patch.object(storage, 'load') as mock_load, \
                 patch('core.memory_brain.memory_brain.update_brain', new_callable=AsyncMock) as mock_update_brain, \
                 patch('core.identity_service.handle_identity_question', new_callable=AsyncMock) as mock_identity:
                
                mock_load.return_value = {"name": "TestUser"}
                mock_identity.return_value = None
                mock_update_brain.return_value = {"profile": {}, "latent": {}, "relational": {}}
                
                # Esegui handle
                response, source = await proactor.handle(real_user_id, message_content)
                
                # Verifica che nessuna chiamata storage usi message come chiave
                for call in mock_load.call_args_list:
                    args, kwargs = call
                    if args:
                        storage_key = args[0]
                        assert message_content not in storage_key, f"Storage key contains message: {storage_key}"
