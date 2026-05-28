import sys
import os
import asyncio
import logging
from datetime import datetime

# Aggiunge la directory root al sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Configura il logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TestEpisodeResolution")

from dotenv import load_dotenv
load_dotenv()

from core.storage import storage
from core.episode_memory import episode_memory as _em

async def run_test():
    logger.info("=== INIZIO TEST DEL RISOLUTORE AUTOMATICO DI EPISODI ===")
    
    user_id = "test_resolution_user"
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
    
    # Salviamo direttamente in storage per impostare gli ID specifici
    await storage.save(storage_key, [ep1, ep2])
    logger.info("✓ Creati 2 episodi attivi di prova:")
    logger.info("  1. test-caviglia: Rita ha una forte distorsione alla caviglia")
    logger.info("  2. test-roma: Alfio è in viaggio di lavoro a Roma")
    
    # 3. Test Risoluzione Caviglia Rita
    msg_risoluzione_caviglia = "Rita oggi cammina benissimo, la caviglia è guarita del tutto!"
    logger.info("\nSimulo messaggio: '%s'", msg_risoluzione_caviglia)
    logger.info("Chiamo resolve_episodes...")
    await _em.resolve_episodes(user_id, msg_risoluzione_caviglia)
    
    # Verifica stato
    eps_after_1 = await _em._load(user_id)
    ep_caviglia = next(e for e in eps_after_1 if e["id"] == "test-caviglia")
    ep_roma = next(e for e in eps_after_1 if e["id"] == "test-roma")
    
    logger.info("Stato test-caviglia dopo test 1: %s (Atteso: resolved)", ep_caviglia["status"])
    logger.info("Risolto il: %s", ep_caviglia.get("resolved_at"))
    logger.info("Stato test-roma dopo test 1: %s (Atteso: active)", ep_roma["status"])
    
    assert ep_caviglia["status"] == "resolved", "FAIL: La caviglia doveva essere risolta!"
    assert ep_roma["status"] == "active", "FAIL: Roma doveva rimanere attiva!"
    logger.info("✓ Test 1 superato con successo!")
    
    # 4. Test Risoluzione Viaggio Roma
    msg_risoluzione_roma = "Sono tornato a casa stasera a Imola da Roma, viaggio stancante ma fruttuoso."
    logger.info("\nSimulo messaggio: '%s'", msg_risoluzione_roma)
    logger.info("Chiamo resolve_episodes...")
    await _em.resolve_episodes(user_id, msg_risoluzione_roma)
    
    # Verifica stato
    eps_after_2 = await _em._load(user_id)
    ep_caviglia_2 = next(e for e in eps_after_2 if e["id"] == "test-caviglia")
    ep_roma_2 = next(e for e in eps_after_2 if e["id"] == "test-roma")
    
    logger.info("Stato test-caviglia dopo test 2: %s (Atteso: resolved)", ep_caviglia_2["status"])
    logger.info("Stato test-roma dopo test 2: %s (Atteso: resolved)", ep_roma_2["status"])
    logger.info("Risolto il: %s", ep_roma_2.get("resolved_at"))
    
    assert ep_caviglia_2["status"] == "resolved", "FAIL: La caviglia doveva rimanere risolta!"
    assert ep_roma_2["status"] == "resolved", "FAIL: Il viaggio a Roma doveva essere risolto!"
    logger.info("✓ Test 2 superato con successo!")
    
    # 5. Ripulisce storage di test
    await storage.save(storage_key, [])
    logger.info("\n✓ Storage di test ripulito con successo")
    logger.info("🎉 TUTTI I TEST DEL RISOLUTORE AUTOMATICO DI EPISODI SONO STATI SUPERATI CON SUCCESSO!")

if __name__ == "__main__":
    asyncio.run(run_test())
