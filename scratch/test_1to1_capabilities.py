import sys
import os
import asyncio
import logging
from unittest.mock import patch, AsyncMock

# Aggiunge la directory root al sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Configura il logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Test1to1Capabilities")

from dotenv import load_dotenv
load_dotenv()

from api.chat import chat_endpoint, chat_stream_endpoint, ChatRequest

class MockUser:
    def __init__(self, id, email):
        self.id = id
        self.email = email

async def run_test():
    logger.info("=== INIZIO TEST DEL LINK EXPLORER IN 1:1 ===")
    
    user = MockUser(id="test_cap_user", email="test_cap@example.com")
    
    # 1. Test 1:1 Sincrono (chat_endpoint)
    logger.info("\n=== TEST 1: CHAT 1:1 SINCRONA ===")
    msg = "Guarda questo link interessante: https://httpbin.org/html"
    logger.info("Inviato messaggio 1:1: '%s'", msg)
    
    captured_messages = []
    
    async def mock_handler(user_id, chat_message, conversation_id=None, platform=None):
        captured_messages.append(chat_message)
        return "Risposta simulata", "chat_free"
    
    with patch("api.chat.simple_chat_handler", mock_handler):
        req = ChatRequest(message=msg, conversation_id="test-conv-cap", platform="web")
        response = await chat_endpoint(req, user)
        logger.info("Risposta chat_endpoint sincrona ricevuta: %s", response.response)
        
        # Verifica che il messaggio passato al simple_chat_handler sia stato arricchito con il contenuto del link
        assert len(captured_messages) == 1, "FAIL: Il messaggio non è stato catturato!"
        enriched_msg = captured_messages[0]
        logger.info("Messaggio arricchito catturato in chat_endpoint:\n%s", enriched_msg)
        
        assert "[Contenuto dei Link esplorati nel messaggio:" in enriched_msg, "FAIL: Il contenuto del link non è presente nel messaggio arricchito!"
        assert "Herman Melville" in enriched_msg, "FAIL: Il testo di Moby Dick dal link non è stato estratto!"
        logger.info("✓ Test 1: Link Explorer Sincrono 1:1 SUPERATO!")

    # 2. Test 1:1 Streaming (chat_stream_endpoint)
    logger.info("\n=== TEST 2: CHAT 1:1 STREAMING ===")
    logger.info("Inviato messaggio streaming: '%s'", msg)
    
    captured_stream_messages = []
    
    async def mock_sch(user_id, stream_chat_message, conversation_id=None, platform=None):
        captured_stream_messages.append(stream_chat_message)
        return "Risposta streaming simulata"
    
    with patch("core.simple_chat.simple_chat_handler", mock_sch):
        req = ChatRequest(message=msg, conversation_id="test-conv-cap-stream", platform="web")
        stream_response = await chat_stream_endpoint(req, user)
        
        # Consuma lo stream
        async for chunk in stream_response.body_iterator:
            pass
            
        assert len(captured_stream_messages) == 1, "FAIL: Il messaggio streaming non è stato catturato!"
        enriched_stream_msg = captured_stream_messages[0]
        logger.info("Messaggio arricchito catturato in chat_stream_endpoint:\n%s", enriched_stream_msg)
        
        assert "[Contenuto dei Link esplorati nel messaggio:" in enriched_stream_msg, "FAIL: Il contenuto del link non è presente nel messaggio streaming arricchito!"
        assert "Herman Melville" in enriched_stream_msg, "FAIL: Il testo di Moby Dick dal link streaming non è stato estratto!"
        logger.info("✓ Test 2: Link Explorer Streaming 1:1 SUPERATO!")

    logger.info("\n🎉 TUTTI I TEST DEL LINK EXPLORER IN 1:1 SUPERATI CON SUCCESSO!")

if __name__ == "__main__":
    asyncio.run(run_test())
