import sys
import os
import asyncio
import logging
from datetime import datetime
from unittest.mock import patch, AsyncMock

# Aggiunge la directory root al sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Configura il logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Test1to1EpisodeResolution")

from dotenv import load_dotenv
load_dotenv()

from core.storage import storage
from core.episode_memory import episode_memory as _em
from api.chat import chat_endpoint, chat_stream_endpoint, ChatRequest

class MockUser:
    def __init__(self, id, email):
        self.id = id
        self.email = email

async def run_test():
    logger.info("=== INIZIO TEST DEL RISOLUTORE EMISODI 1:1 ===")
    
    # Mocking llm_service._call_model per rendere il test deterministico ed indipendente da OpenRouter
    from core.llm_service import llm_service
    original_call_model = llm_service._call_model
    
    async def mock_call_model(model, prompt, message, user_id, route, messages=None):
        if route == "memory":
            logger.info(f"[MOCK LLM] Intercettata chiamata per la route 'memory' con messaggio: {repr(message)}")
            if "caviglia" in message or "cammina" in message:
                res = '{"resolved_ids": ["test-caviglia"]}'
            elif "Roma" in message or "tornato" in message:
                res = '{"resolved_ids": ["test-roma"]}'
            else:
                res = '{"resolved_ids": []}'
            logger.info(f"[MOCK LLM] Ritorno risposta mockata: {res}")
            return res
        return await original_call_model(model, prompt, message, user_id, route, messages)
        
    llm_service._call_model = mock_call_model

    user_id = "test_1to1_user"
    storage_key = f"episodes:{user_id}"
    
    # 1. Pulisce storage preesistente
    await storage.save(storage_key, [])
    logger.info("✓ Storage di test pulito")
    
    # 2. Crea ed aggiunge episodi di prova 'active'
    ep1 = {
        "id": "test-caviglia",
        "text": "Rita ha una forte distorsione alla caviglia e deve stare a riposo.",
        "event_date": None,
        "is_future": False,
        "tags": ["rita", "caviglia", "distorsione", "salute"],
        "saved_at": datetime.utcnow().isoformat(),
        "last_used_at": None,
        "use_count": 0,
        "status": "active",
        "resolved_at": None
    }
    
    ep2 = {
        "id": "test-roma",
        "text": "Alfio è in viaggio di lavoro a Roma e rientrerà a breve.",
        "event_date": None,
        "is_future": True,
        "tags": ["alfio", "roma", "viaggio", "lavoro"],
        "saved_at": datetime.utcnow().isoformat(),
        "last_used_at": None,
        "use_count": 0,
        "status": "active",
        "resolved_at": None
    }
    
    await storage.save(storage_key, [ep1, ep2])
    logger.info("✓ Creati 2 episodi attivi di prova per l'utente 1:1:")
    logger.info("  1. test-caviglia: Rita ha una forte distorsione alla caviglia")
    logger.info("  2. test-roma: Alfio è in viaggio di lavoro a Roma")
    
    # Mock user object
    user = MockUser(id=user_id, email="test@example.com")
    
    # 3. Test 1:1 Sincrono (chat_endpoint)
    # Patchiamo simple_chat_handler per evitare chiamate esterne all'LLM durante la chat
    # e simuliamo la risposta relazionale.
    logger.info("\n=== TEST 1: CHAT 1:1 SINCRONA ===")
    msg_caviglia = "Rita oggi cammina benissimo, la caviglia è guarita del tutto!"
    logger.info("Inviato messaggio 1:1: '%s'", msg_caviglia)
    
    mock_handler = AsyncMock(return_value=("Ti auguro una buona giornata!", "chat_free"))
    
    with patch("api.chat.simple_chat_handler", mock_handler):
        req = ChatRequest(message=msg_caviglia, conversation_id="test-conv-1", platform="web")
        response = await chat_endpoint(req, user)
        logger.info("Risposta chat_endpoint sincrona ricevuta: %s", response.response)
        
        # Aspettiamo il task in background
        logger.info("Attendo l'esecuzione del Resolution Engine in background...")
        await asyncio.sleep(2.5)
        
        # Carica gli episodi e verifica
        eps = await _em._load(user_id)
        ep_caviglia = next(e for e in eps if e["id"] == "test-caviglia")
        ep_roma = next(e for e in eps if e["id"] == "test-roma")
        
        logger.info("Stato test-caviglia: %s (Atteso: resolved)", ep_caviglia["status"])
        logger.info("Stato test-roma: %s (Atteso: active)", ep_roma["status"])
        
        assert ep_caviglia["status"] == "resolved", "FAIL: L'episodio caviglia doveva essere resolved!"
        assert ep_roma["status"] == "active", "FAIL: L'episodio Roma doveva rimanere active!"
        logger.info("✓ Test 1: Sincrono 1:1 SUPERATO!")

    # 4. Test 1:1 Streaming (chat_stream_endpoint)
    logger.info("\n=== TEST 2: CHAT 1:1 STREAMING ===")
    msg_roma = "Sono tornato a casa stasera a Imola da Roma, viaggio stancante ma fruttuoso."
    logger.info("Inviato messaggio streaming: '%s'", msg_roma)
    
    mock_sch = AsyncMock(return_value="Bene! Bentornato a casa!")
    
    with patch("api.chat.simple_chat_handler", mock_sch):
        req = ChatRequest(message=msg_roma, conversation_id="test-conv-2", platform="web")
        stream_response = await chat_stream_endpoint(req, user)
        
        # Consuma il generatore dello streaming response per far avanzare il pipeline_task
        # (FastAPI StreamingResponse contiene body_iterator)
        logger.info("Consumo l'iteratore dello streaming...")
        async for chunk in stream_response.body_iterator:
            pass
            
        # Aspettiamo il task in background
        logger.info("Attendo l'esecuzione del Resolution Engine in background per lo stream...")
        await asyncio.sleep(2.5)
        
        # Carica gli episodi e verifica
        eps = await _em._load(user_id)
        ep_caviglia_2 = next(e for e in eps if e["id"] == "test-caviglia")
        ep_roma_2 = next(e for e in eps if e["id"] == "test-roma")
        
        logger.info("Stato test-caviglia: %s (Atteso: resolved)", ep_caviglia_2["status"])
        logger.info("Stato test-roma: %s (Atteso: resolved)", ep_roma_2["status"])
        
        assert ep_caviglia_2["status"] == "resolved", "FAIL: L'episodio caviglia doveva rimanere resolved!"
        assert ep_roma_2["status"] == "resolved", "FAIL: L'episodio Roma doveva essere resolved!"
        logger.info("✓ Test 2: Streaming 1:1 SUPERATO!")

    # 5. Pulizia
    await storage.save(storage_key, [])
    logger.info("\n✓ Storage di test ripulito con successo")
    logger.info("🎉 TUTTI I TEST DEL RISOLUTORE AUTOMATICO 1:1 SUPERATI CON SUCCESSO!")

if __name__ == "__main__":
    asyncio.run(run_test())
