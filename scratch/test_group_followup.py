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

from core.telegram_bot import _group_should_intervene, _GROUP_CONV_STATE, _check_and_register_greeting
from core.whatsapp_bot import (
    _group_should_intervene as _wa_group_should_intervene, 
    _GROUP_CONV_STATE as _WA_GROUP_CONV_STATE,
    _check_and_register_greeting as _wa_check_and_register_greeting
)
from core.storage import storage

async def run_tests():
    chat_id = -318483633
    sandra_id = 1329017213
    alfio_id = 494065944

    print("==================================================")
    print("[TEST] INIZIO TEST COMPRENSIVO FILTRO INTERVENTO GRUPPO & SALUTI")
    print("==================================================")

    # Pulisci preventivamente lo stato dei saluti nel database mock/in-memory
    key = f"relational_state:group_greetings_{chat_id}"
    await storage.save(key, {})
    global_key = f"relational_state:last_group_greeting_ts_{chat_id}"
    await storage.save(global_key, 0.0)

    # --- TEST 1: SALUTI COMPORTAMENTO PER-UTENTE ---
    print("\n--- Test 1: Saluti Comportamento Per-Utente ---")
    
    # 1.1 Primo saluto di Sandra (morning) -> deve ritornare True (consentire saluto)
    s1 = await _check_and_register_greeting(chat_id, str(sandra_id), "morning")
    print(f"  Sandra saluta per prima volta (morning): {s1} (Atteso: True)")
    assert s1 is True, "FAIL: Sandra avrebbe dovuto poter salutare"

    # 1.2 Secondo saluto immediato di Sandra (morning) -> deve ritornare False (già salutato oggi per morning)
    s2 = await _check_and_register_greeting(chat_id, str(sandra_id), "morning")
    print(f"  Sandra risaluta subito (morning): {s2} (Atteso: False)")
    assert s2 is False, "FAIL: Sandra non avrebbe dovuto poter salutare di nuovo subito"

    # 1.3 Primo saluto di Alfio (morning) -> deve ritornare True (utente diverso!)
    # Nota: per via del gap globale di 1 ora di gruppo, dobbiamo simulare che sia passata più di 1 ora dal saluto di Sandra.
    global_key = f"relational_state:last_group_greeting_ts_{chat_id}"
    await storage.save(global_key, time.time() - 3700)
    a1 = await _check_and_register_greeting(chat_id, str(alfio_id), "morning")
    print(f"  Alfio saluta (morning, utente diverso): {a1} (Atteso: True)")
    assert a1 is True, "FAIL: Alfio è un utente diverso e deve poter salutare"

    # 1.4 Saluto di Sandra (morning) dopo 5 ore -> deve ritornare True (passate > 4 ore!)
    history = await storage.load(key, default={})
    history[f"{sandra_id}:morning"]["ts"] = time.time() - 18000  # 5 ore fa
    await storage.save(key, history)
    
    # Reimposta anche il gap globale a > 1 ora fa
    await storage.save(global_key, time.time() - 3700)
    s3 = await _check_and_register_greeting(chat_id, str(sandra_id), "morning")
    print(f"  Sandra saluta dopo 5 ore (morning): {s3} (Atteso: True)")
    assert s3 is True, "FAIL: Sandra avrebbe dovuto poter risalutare dopo 5 ore"


    # --- TEST 2: INTERVENTO DI GRUPPO CON SALUTO & DOMANDA (FALL-THROUGH) ---
    print("\n--- Test 2: Fall-through per Saluto con Domanda Substantiva ---")
    
    # Reimposta i saluti di oggi per Sandra in modo che `_check_and_register_greeting` ritorni False
    history = await storage.load(key, default={})
    history[f"{sandra_id}:morning"] = {
        "date": time.strftime("%Y-%m-%d"),
        "ts": time.time()
    }
    await storage.save(key, history)

    # Sandra scrive solo "Buongiorno" -> deve essere False perché ha già salutato e non c'è altro contenuto
    msg_only_greet = "Buongiorno"
    should_tg_only = await _group_should_intervene(
        text=msg_only_greet, caption="", chat_id=chat_id, from_id=sandra_id, first_name="Sandra",
        bot_mentioned=False, has_media=False
    )
    print(f"  Messaggio: '{msg_only_greet}' da Sandra (solo saluto ripetuto): {should_tg_only} (Atteso: False)")
    assert should_tg_only is False, "FAIL: Non dovrebbe intervenire su saluto ripetuto senza altro contenuto"

    # Sandra scrive "Buongiorno, che tempo fa a Bracciano?" -> deve essere True (anche se il saluto è ripetuto, c'è una domanda reale!)
    # Nota: nei test non abbiamo l'LLM attivo nel mock o se è attivo farà una chiamata mockata/reale.
    # Proviamo a simulare il fall-through fast-path di continuazione o semplicemente a verificare che non esca a False subito.
    # Per farlo fall-through verso il fast-path di continuazione (< 5 min):
    _GROUP_CONV_STATE[chat_id] = {
        "from_id": sandra_id,
        "ts": time.time() - 40,
        "last_reply": "Che bel tempo!"
    }
    _WA_GROUP_CONV_STATE[chat_id] = {
        "wa_id": str(sandra_id),
        "ts": time.time() - 40,
        "last_reply": "Che bel tempo!"
    }

    msg_with_question = "Buongiorno, come state tutti?"
    should_tg_question = await _group_should_intervene(
        text=msg_with_question, caption="", chat_id=chat_id, from_id=sandra_id, first_name="Sandra",
        bot_mentioned=False, has_media=False
    )
    should_wa_question = await _wa_group_should_intervene(
        text=msg_with_question, caption="", chat_id=chat_id, wa_id=str(sandra_id), first_name="Sandra",
        bot_mentioned=False, has_media=False
    )
    print(f"  Messaggio: '{msg_with_question}' da Sandra (saluto ripetuto + continuazione attiva):")
    print(f"    -> Telegram should_intervene: {should_tg_question} (Atteso: True)")
    print(f"    -> WhatsApp should_intervene: {should_wa_question} (Atteso: True)")
    assert should_tg_question is True, "FAIL: Dovrebbe intervenire sul fall-through di continuazione"
    assert should_wa_question is True, "FAIL: Dovrebbe intervenire sul fall-through di continuazione"
    print("  -> OK!")


    # --- TEST 3: SCENARIO FOLLOW-UP STANDARD ---
    print("\n--- Test 3: Scenario Follow-up Standard ---")
    
    # 3.1: Alfio scrive "E da Mariella e Katia?"
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

    print(f"  Messaggio: '{msg}' da Alfio (mittente differente, entro 5 minuti con '?')")
    print(f"    -> Telegram: {should_tg} (Atteso: True)")
    print(f"    -> WhatsApp: {should_wa} (Atteso: True)")
    assert should_tg is True, "FAIL: Telegram fast-path non attivato per domanda di follow-up"
    assert should_wa is True, "FAIL: WhatsApp fast-path non attivato per domanda di follow-up"
    print("  -> OK!")


    # --- TEST 4: GAP GLOBALE 1 ORA SU WHATSAPP ---
    print("\n--- Test 4: Gap Globale 1 Ora su WhatsApp ---")
    # Pulisci preventivamente lo stato
    global_key = f"relational_state:last_group_greeting_ts_{chat_id}"
    await storage.save(global_key, 0.0)
    await storage.save(f"relational_state:group_greetings_{chat_id}", {})
    
    # 4.1 Primo saluto (Sandra) -> deve ritornare True
    wg1 = await _wa_check_and_register_greeting(chat_id, str(sandra_id), "morning")
    print(f"  WA: Primo saluto di Sandra: {wg1} (Atteso: True)")
    assert wg1 is True, "FAIL: Primo saluto avrebbe dovuto poter essere registrato"

    # 4.2 Secondo saluto (Alfio) entro 1 ora -> deve ritornare False a causa del gap globale del gruppo
    wg2 = await _wa_check_and_register_greeting(chat_id, str(alfio_id), "morning")
    print(f"  WA: Secondo saluto di Alfio entro 1 ora (gap globale): {wg2} (Atteso: False)")
    assert wg2 is False, "FAIL: Secondo saluto entro 1 ora non deve essere registrato"

    # 4.3 Saluto dopo 1 ora -> deve ritornare True
    await storage.save(global_key, time.time() - 3700) # Simula saluto di 3700 secondi fa
    # Pulisci anche il gap utente per Alfio così è consentito
    wg3 = await _wa_check_and_register_greeting(chat_id, str(alfio_id), "morning")
    print(f"  WA: Saluto di Alfio dopo 1 ora: {wg3} (Atteso: True)")
    assert wg3 is True, "FAIL: Saluto dopo 1 ora dovrebbe essere consentito"


    # --- TEST 5: BYPASS FILTRO SALUTI & BREVITÀ CON HAS_MEDIA ---
    print("\n--- Test 5: Bypass Filtro Saluti & Brevità con has_media=True ---")
    # Imposta lo stato per simulare che Sandra abbia già salutato per morning e il gap globale sia attivo
    await storage.save(global_key, time.time())
    history = {
        f"{sandra_id}:morning": {
            "date": time.strftime("%Y-%m-%d"),
            "ts": time.time()
        }
    }
    await storage.save(f"relational_state:group_greetings_{chat_id}", history)
    
    # Imposta lo stato di continuazione in modo da intercettare il fall-through
    _GROUP_CONV_STATE[chat_id] = {
        "from_id": sandra_id,
        "ts": time.time() - 40,
        "last_reply": "Che bel tempo!"
    }
    _WA_GROUP_CONV_STATE[chat_id] = {
        "wa_id": str(sandra_id),
        "ts": time.time() - 40,
        "last_reply": "Che bel tempo!"
    }

    # 5.1 Telegram: Messaggio "Buongiorno" (pure greeting category, already registered) ma has_media=True
    # Dovrebbe bypassare il blocco pure greeting e ritornare True (grazie alla continuazione attiva)
    media_tg = await _group_should_intervene(
        text="Buongiorno", caption="", chat_id=chat_id, from_id=sandra_id, first_name="Sandra",
        bot_mentioned=False, has_media=True
    )
    print(f"  TG: Saluto ripetuto 'Buongiorno' con has_media=True: {media_tg} (Atteso: True)")
    assert media_tg is True, "FAIL: Telegram avrebbe dovuto bypassare il blocco dei saluti ripetuti con has_media=True"

    # 5.2 WhatsApp: Messaggio "Buongiorno" ma has_media=True
    media_wa = await _wa_group_should_intervene(
        text="Buongiorno", caption="", chat_id=chat_id, wa_id=str(sandra_id), first_name="Sandra",
        bot_mentioned=False, has_media=True
    )
    print(f"  WA: Saluto ripetuto 'Buongiorno' con has_media=True: {media_wa} (Atteso: True)")
    assert media_wa is True, "FAIL: WhatsApp avrebbe dovuto bypassare il blocco dei saluti ripetuti con has_media=True"

    # 5.3 Telegram: Messaggio cortissimo (es. "Ciao", length = 4 < 8) ma has_media=True
    # Dovrebbe bypassare il blocco della brevità e procedere
    short_media_tg = await _group_should_intervene(
        text="Ciao", caption="", chat_id=chat_id, from_id=sandra_id, first_name="Sandra",
        bot_mentioned=False, has_media=True
    )
    print(f"  TG: Messaggio cortissimo 'Ciao' con has_media=True: {short_media_tg} (Atteso: True)")
    assert short_media_tg is True, "FAIL: Telegram avrebbe dovuto bypassare il blocco dei messaggi corti con has_media=True"

    # 5.4 WhatsApp: Messaggio cortissimo ma has_media=True
    short_media_wa = await _wa_group_should_intervene(
        text="Ciao", caption="", chat_id=chat_id, wa_id=str(sandra_id), first_name="Sandra",
        bot_mentioned=False, has_media=True
    )
    print(f"  WA: Messaggio cortissimo 'Ciao' con has_media=True: {short_media_wa} (Atteso: True)")
    assert short_media_wa is True, "FAIL: WhatsApp avrebbe dovuto bypassare il blocco dei messaggi corti con has_media=True"

    print("\n==================================================")
    print("[SUCCESS] TUTTI I TEST COMPRENSIVI SONO STATI SUPERATI CON SUCCESSO!")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_tests())
