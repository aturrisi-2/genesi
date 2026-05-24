import sys
import os
import asyncio
import time

# Add root project path to PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set mock env variables
os.environ["TELEGRAM_BOT_TOKEN"] = "mock_token"
os.environ["TELEGRAM_GROUP_EMAIL"] = "mock_email"
os.environ["TELEGRAM_GROUP_PASSWORD"] = "mock_password"

from core.telegram_bot import _group_should_intervene, _GROUP_CONV_STATE
from core.whatsapp_bot import _group_should_intervene as _wa_group_should_intervene, _GROUP_CONV_STATE as _WA_GROUP_CONV_STATE

async def run_tests():
    chat_id = -318483633
    sandra_id = 1329017213
    alfio_id = 494065944

    print("==================================================")
    print("[TEST] INIZIO TEST SIMULAZIONE FILTRO INTERVENTO GRUPPO")
    print("==================================================")

    # 1. Genesi ha appena risposto a Sandra (simuliamo salvando lo stato)
    print("\n--- Scenario 1: Genesi ha appena risposto a Sandra (40 secondi fa) ---")
    _GROUP_CONV_STATE[chat_id] = {
        "from_id": sandra_id,
        "ts": time.time() - 40,
        "last_reply": "Non ho informazioni dettagliate sul tempo a Bracciano, ma spero che ci sia un bel sole anche lì! [sole]"
    }
    _WA_GROUP_CONV_STATE[chat_id] = {
        "wa_id": str(sandra_id),
        "ts": time.time() - 40,
        "last_reply": "Non ho informazioni dettagliate sul tempo a Bracciano, ma spero che ci sia un bel sole anche lì! [sole]"
    }

    # Test 1.1: Alfio scrive "E da Mariella e Katia?"
    # Mittente diverso, ma entro 5 min e ha "?" ➔ Deve attivare il fast-path e ritornare True!
    msg = "E da Mariella e Katia?"
    should_tg = await _group_should_intervene(
        text=msg, caption="", chat_id=chat_id, from_id=alfio_id, first_name="Alfio",
        bot_mentioned=False, has_media=False
    )
    should_wa = await _wa_group_should_intervene(
        text=msg, caption="", chat_id=chat_id, wa_id=str(alfio_id), first_name="Alfio",
        bot_mentioned=False, has_media=False
    )

    print(f"Messaggio: '{msg}' da Alfio (mittente differente, entro 5 minuti con '?')")
    print(f"  -> Telegram fast-path: {should_tg} (Atteso: True)")
    print(f"  -> WhatsApp fast-path: {should_wa} (Atteso: True)")
    assert should_tg is True, "FAIL: Telegram fast-path non attivato per domanda di follow-up"
    assert should_wa is True, "FAIL: WhatsApp fast-path non attivato per domanda di follow-up"
    print("  -> OK!")

    # Test 1.2: Alfio scrive "e a Roma" (domanda implicita senza "?", inizia con "e ")
    # Mittente diverso, entro 5 min, inizia con "e " ➔ Deve ritornare True!
    msg = "e a Roma"
    should_tg = await _group_should_intervene(
        text=msg, caption="", chat_id=chat_id, from_id=alfio_id, first_name="Alfio",
        bot_mentioned=False, has_media=False
    )
    should_wa = await _wa_group_should_intervene(
        text=msg, caption="", chat_id=chat_id, wa_id=str(alfio_id), first_name="Alfio",
        bot_mentioned=False, has_media=False
    )
    print(f"\nMessaggio: '{msg}' da Alfio (mittente differente, entro 5 minuti, congiunzione 'e')")
    print(f"  -> Telegram fast-path: {should_tg} (Atteso: True)")
    print(f"  -> WhatsApp fast-path: {should_wa} (Atteso: True)")
    assert should_tg is True, "FAIL: Telegram fast-path non attivato per domanda implicita"
    assert should_wa is True, "FAIL: WhatsApp fast-path non attivato per domanda implicita"
    print("  -> OK!")

    # Test 1.3: Sandra (stesso utente) scrive "Qui ci sta un sole meraviglioso"
    # Stesso mittente, entro 5 min ➔ Deve ritornare True!
    msg = "Qui ci sta un sole meraviglioso"
    should_tg = await _group_should_intervene(
        text=msg, caption="", chat_id=chat_id, from_id=sandra_id, first_name="sandra",
        bot_mentioned=False, has_media=False
    )
    should_wa = await _wa_group_should_intervene(
        text=msg, caption="", chat_id=chat_id, wa_id=str(sandra_id), first_name="sandra",
        bot_mentioned=False, has_media=False
    )
    print(f"\nMessaggio: '{msg}' da Sandra (stesso mittente, entro 5 minuti)")
    print(f"  -> Telegram fast-path: {should_tg} (Atteso: True)")
    print(f"  -> WhatsApp fast-path: {should_wa} (Atteso: True)")
    assert should_tg is True, "FAIL: Telegram fast-path non attivato per lo stesso mittente"
    assert should_wa is True, "FAIL: WhatsApp fast-path non attivato per lo stesso mittente"
    print("  -> OK!")

    # 2. Genesi non ha risposto di recente (es. 10 minuti fa)
    print("\n--- Scenario 2: Genesi non risponde da 10 minuti (stato obsoleto) ---")
    _GROUP_CONV_STATE[chat_id] = {
        "from_id": sandra_id,
        "ts": time.time() - 600,
        "last_reply": "Non ho informazioni dettagliate sul tempo a Bracciano."
    }
    _WA_GROUP_CONV_STATE[chat_id] = {
        "wa_id": str(sandra_id),
        "ts": time.time() - 600,
        "last_reply": "Non ho informazioni dettagliate sul tempo a Bracciano."
    }

    # Test 2.1: Domanda breve non correlata e senza punto di domanda ➔ Deve ritornare False immediatamente
    msg = "ok"
    should_tg = await _group_should_intervene(
        text=msg, caption="", chat_id=chat_id, from_id=alfio_id, first_name="Alfio",
        bot_mentioned=False, has_media=False
    )
    print(f"Messaggio: '{msg}' da Alfio (vecchio stato, no '?')")
    print(f"  -> Telegram: {should_tg} (Atteso: False)")
    assert should_tg is False, "FAIL: Genesi non avrebbe dovuto intervenire su un semplice 'ok' fuori contesto"
    print("  -> OK!")

    print("\n==================================================")
    print("[SUCCESS] COMPLIMENTI: TUTTI I TEST DI GRUPPO SONO STATI SUPERATI CON SUCCESSO!")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_tests())
