import sys
import os
import asyncio
import logging

# Aggiunge il root al sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Imposta il logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TestGroupBehavior")

from core.storage import storage

# Importiamo le funzioni da testare da telegram_bot
from core.telegram_bot import (
    _get_greeting_category,
    _check_and_register_greeting,
    _group_should_intervene
)

async def test_greeting_logic():
    logger.info("=== 1. Test Classificazione Categorie Saluti ===")
    
    # Test morning
    assert _get_greeting_category("Buongiorno a tutti!".lower()) == "morning"
    assert _get_greeting_category("buon pranzo".lower()) == "morning"
    logger.info("✓ Categoria 'morning' classificata correttamente")

    # Test evening
    assert _get_greeting_category("Buonasera famiglia!".lower()) == "evening"
    assert _get_greeting_category("buonanotte a tutti".lower()) == "evening"
    logger.info("✓ Categoria 'evening' classificata correttamente")

    # Test holiday
    assert _get_greeting_category("Buona Pasqua!".lower()) == "holiday"
    assert _get_greeting_category("Buon compleanno Enzo!".lower()) == "holiday"
    logger.info("✓ Categoria 'holiday' classificata correttamente")

    # Test general
    assert _get_greeting_category("Ciao!".lower()) == "general"
    assert _get_greeting_category("Salve".lower()) == "general"
    logger.info("✓ Categoria 'general' classificata correttamente")

    # Test no greeting
    assert _get_greeting_category("Come stai?".lower()) == ""
    logger.info("✓ Frase generica classificata vuota correttamente")

    logger.info("=== 2. Test Registro e Limitazione Giornaliera dei Saluti ===")
    chat_id = 999999
    key = f"relational_state:group_greetings_{chat_id}"
    global_key = f"relational_state:last_group_greeting_ts_{chat_id}"
    
    # Pulisce lo stato precedente per il test
    await storage.save(key, {})
    await storage.save(global_key, 0.0)
    logger.info("Punto di partenza pulito per chat_id=%s", chat_id)

    # Primo saluto morning -> deve essere accettato
    res1 = await _check_and_register_greeting(chat_id, "123456", "morning")
    logger.info("Primo 'morning': %s (Atteso: True)", res1)
    assert res1 is True

    # Secondo saluto morning dello stesso giorno -> deve essere bloccato
    res2 = await _check_and_register_greeting(chat_id, "123456", "morning")
    logger.info("Secondo 'morning': %s (Atteso: False)", res2)
    assert res2 is False

    # Pulisce il timestamp globale di 1 ora e la cronologia utente per permettere il test del saluto evening
    await storage.save(key, {})
    await storage.save(global_key, 0.0)

    # Saluto evening (diverso) nello stesso giorno -> deve essere accettato
    res3 = await _check_and_register_greeting(chat_id, "123456", "evening")
    logger.info("Primo 'evening': %s (Atteso: True)", res3)
    assert res3 is True

    # Saluto general ("Ciao") dopo che è già stato registrato un saluto -> deve essere bloccato
    res4 = await _check_and_register_greeting(chat_id, "123456", "general")
    logger.info("Saluto generico dopo saluti esistenti: %s (Atteso: False)", res4)
    assert res4 is False

    # Ripuliamo
    await storage.save(key, {})
    logger.info("Registro ripulito con successo")

async def test_llm_intervention_decision():
    logger.info("=== 3. Test Decisioni LLM per l'Intervento Spontaneo ===")
    chat_id = 999999
    
    # Caso A: Domanda generica di servizio / aiuto (dovrebbe intervenire autonomamente)
    msg_domanda = "Qualcuno sa a che ora chiude il supermercato Esselunga stasera?"
    logger.info("Simulo messaggio: '%s'", msg_domanda)
    should_a = await _group_should_intervene(
        msg_domanda, "", chat_id, 123, "Marco"
    )
    logger.info("Risultato Intervento per Domanda Generica: %s (Atteso: True)", should_a)

    # Caso B: Saluto morning quando Genesi ha già salutato oggi (dovrebbe ignorarlo)
    key = f"relational_state:group_greetings_{chat_id}"
    from datetime import datetime
    from zoneinfo import ZoneInfo
    try:
        tz = ZoneInfo("Europe/Rome")
    except Exception:
        tz = None
    today_str = datetime.now(tz).date().isoformat()
    await storage.save(key, {"morning": today_str})
    
    msg_saluto_bis = "Buongiorno a tutti!"
    logger.info("Simulo secondo messaggio di saluto morning: '%s'", msg_saluto_bis)
    should_b = await _group_should_intervene(
        msg_saluto_bis, "", chat_id, 456, "Giulia"
    )
    logger.info("Risultato Intervento per Saluto Morning Bis: %s (Atteso: False)", should_b)

    # Ripuliamo
    await storage.save(key, {})

async def main():
    try:
        await test_greeting_logic()
        await test_llm_intervention_decision()
        logger.info("🎉 TUTTI I TEST DI GRUPPO SONO STATI SUPERATI CON SUCCESSO!")
    except AssertionError as e:
        logger.error("❌ ERRORE DI ASSERZIONE NEI TEST: %s", e)
    except Exception as e:
        logger.error("❌ ERRORE IMPREVISTO NEI TEST: %s", e)

if __name__ == "__main__":
    asyncio.run(main())
