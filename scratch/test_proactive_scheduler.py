import asyncio
import sys
import os
from pathlib import Path
from datetime import date, datetime

sys.path.append(str(Path(__file__).parent.parent.absolute()))

from dotenv import load_dotenv
load_dotenv()

from core.birthday_service import (
    get_easter_date,
    get_italian_holiday,
    get_local_holiday,
    get_today_events_context,
    _generate_proactive_greeting
)

async def run_tests():
    print("==================================================")
    print("[TEST] INIZIO TEST DEL CO-SCHEDULER E DELLE FESTIVITÀ")
    print("==================================================")

    # --- TEST 1: CALCOLO PASQUA E PASQUETTA ---
    print("\n--- Test 1: Calcolo Pasqua e Pasquetta (Mobili) ---")
    
    # 2026: Pasqua è il 5 Aprile, Pasquetta il 6 Aprile
    e2026 = get_easter_date(2026)
    print(f"  Pasqua 2026: {e2026} (Atteso: 2026-04-05)")
    assert e2026 == date(2026, 4, 5), "FAIL Pasqua 2026"
    
    p2026 = get_italian_holiday(date(2026, 4, 6))
    print(f"  Pasquetta 2026 (6 Aprile): {p2026} (Atteso: Lunedì dell'Angelo (Pasquetta))")
    assert p2026 == "Lunedì dell'Angelo (Pasquetta)", "FAIL Pasquetta 2026"
    
    # 2027: Pasqua è il 28 Marzo, Pasquetta il 29 Marzo
    e2027 = get_easter_date(2027)
    print(f"  Pasqua 2027: {e2027} (Atteso: 2027-03-28)")
    assert e2027 == date(2027, 3, 28), "FAIL Pasqua 2027"

    p2027 = get_italian_holiday(date(2027, 3, 29))
    print(f"  Pasquetta 2027 (29 Marzo): {p2027} (Atteso: Lunedì dell'Angelo (Pasquetta))")
    assert p2027 == "Lunedì dell'Angelo (Pasquetta)", "FAIL Pasquetta 2027"
    print("  -> OK!")


    # --- TEST 2: FESTIVITÀ FISSE ---
    print("\n--- Test 2: Festività Nazionali Fisse ---")
    h_natale = get_italian_holiday(date(2026, 12, 25))
    print(f"  25/12/2026: {h_natale} (Atteso: Natale)")
    assert h_natale == "Natale", "FAIL Natale"

    h_repubblica = get_italian_holiday(date(2026, 6, 2))
    print(f"  02/06/2026: {h_repubblica} (Atteso: Festa della Repubblica)")
    assert h_repubblica == "Festa della Repubblica", "FAIL Festa della Repubblica"
    
    h_feriale = get_italian_holiday(date(2026, 5, 25))
    print(f"  25/05/2026: {h_feriale} (Atteso: None)")
    assert h_feriale is None, "FAIL Feriale"
    print("  -> OK!")


    # --- TEST 3: FESTIVITÀ PATRONALI LOCALI ---
    print("\n--- Test 3: Festività Patronali per Città ---")
    p_roma = get_local_holiday(date(2026, 6, 29), "roma")
    print(f"  Roma 29/06: {p_roma} (Atteso: Festa patronale di Santi Pietro e Paolo a Roma)")
    assert "Santi Pietro e Paolo" in p_roma, "FAIL Roma"

    p_milano = get_local_holiday(date(2026, 12, 7), "Milano")
    print(f"  Milano 07/12: {p_milano} (Atteso: Festa patronale di Sant'Ambrogio a Milano)")
    assert "Sant'Ambrogio" in p_milano, "FAIL Milano"
    print("  -> OK!")


    # --- TEST 4: CONTESTO CONVERSAZIONALE DEL GIORNO ---
    print("\n--- Test 4: Generazione Contesto Temporale Giornaliero ---")
    ctx = await get_today_events_context(chat_id=0)
    print("Contesto generato:\n\"\"\"")
    print(ctx)
    print("\"\"\"")
    assert "Oggi è" in ctx, "FAIL Contesto generato"
    print("  -> OK!")


    def safe_print(msg):
        try:
            print(msg)
        except Exception:
            try:
                print(msg.encode('ascii', 'ignore').decode('ascii'))
            except Exception:
                pass

    # --- TEST 5: GENERAZIONE MESSAGGIO PROATTIVO MATTUTINO (LLM) ---
    print("\n--- Test 5: Generazione Messaggio Proattivo LLM ---")
    
    # 5.1 Giorno feriale
    msg_feriale = await _generate_proactive_greeting([], "weekday_greeting", date(2026, 5, 25)) # Lunedì
    safe_print(f"  Saluto Feriale LLM:\n  -> '{msg_feriale}'\n")
    assert len(msg_feriale) > 10, "FAIL Saluto feriale"

    # 5.2 Giorno Weekend
    msg_weekend = await _generate_proactive_greeting([], "weekend_holiday_greeting", date(2026, 5, 24)) # Domenica
    safe_print(f"  Saluto Weekend LLM:\n  -> '{msg_weekend}'\n")
    assert len(msg_weekend) > 10, "FAIL Saluto weekend"

    # 5.3 Compleanno
    msg_bday = await _generate_proactive_greeting([("Rita", 57)], "birthday", date(2026, 5, 25))
    safe_print(f"  Saluto Compleanno LLM (Auguri a Rita):\n  -> '{msg_bday}'\n")
    assert "Rita" in msg_bday, "FAIL Saluto compleanno"
    print("  -> OK!")

    print("\n==================================================")
    print("[SUCCESS] TUTTI I TEST COMPRENSIVI DEL CO-SCHEDULER SONO PASSATI CON SUCCESSO!")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_tests())
