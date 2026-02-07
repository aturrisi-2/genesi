#!/usr/bin/env python3
"""
Test rimozione parametri ms dal TTS - 5 scenari obbligatori
"""
import re

def sanitize_tts_text(text: str) -> str:
    """Funzione di sanitizzazione TTS copiata da main.py"""
    text = text.strip()
    # Rimuovi timestamp ISO (es: 2025-02-07T23:42:00.123Z)
    text = re.sub(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z\s*', '', text)
    # Rimuovi prefissi di log [TAG]
    text = re.sub(r'^\[[A-Z_]+\]\s*', '', text)
    # Rimuovi numeri iniziali seguiti da spazio (es: "1234567890 ")
    text = re.sub(r'^\d+\s+', '', text)
    # Rimuovi parametri temporali residui (ms) che Edge TTS non supporta
    if re.search(r'\d+ms', text):
        print(f"[TTS] WARNING: rimosso parametri temporali dal testo")
        text = re.sub(r'\d+\s?ms', '', text)
    # Rimuovi spazi multipli residui
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def test_rimozione_ms():
    print("=== TEST RIMOZIONE PARAMETRI MS - 5 SCENARI ===")
    passed = 0
    failed = 0

    # TEST 1: "ciao" → voce dice solo "ciao"
    print("\n1) Testo semplice -> nessun ms")
    try:
        text = "Ciao, come stai?"
        result = sanitize_tts_text(text)
        assert "ms" not in result
        assert result == "Ciao, come stai?"
        print(f"  PASS: '{text}' -> '{result}'")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 2: Risposta con pause → nessun numero letto
    print("\n2) Testo con pause simulate -> ms rimossi")
    try:
        text = "Ciao, 120ms come stai?"
        result = sanitize_tts_text(text)
        assert "ms" not in result
        assert result == "Ciao, come stai?"
        print(f"  PASS: '{text}' -> '{result}'")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 3: Ritmo più veloce → nessun artefatto
    print("\n3) Testo con multipli ms -> tutti rimossi")
    try:
        text = "Ciao. 85ms Come stai? 120ms Bene grazie."
        result = sanitize_tts_text(text)
        assert "ms" not in result
        assert result == "Ciao. Come stai? Bene grazie."
        print(f"  PASS: '{text}' -> '{result}'")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 4: Testo con respiri ms -> ms rimossi
    print("\n4) Testo con respiro ms -> ms rimossi")
    try:
        text = "250ms Ciao, come stai?"
        result = sanitize_tts_text(text)
        assert "ms" not in result
        assert result == "Ciao, come stai?"
        print(f"  PASS: '{text}' -> '{result}'")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 5: Testo complesso con ms e timestamp -> tutto pulito
    print("\n5) Testo complesso con ms e timestamp -> tutto pulito")
    try:
        text = "2025-02-07T23:42:00.123Z [RESPONSE_GENERATOR] Ciao, 120ms come stai? 85ms"
        result = sanitize_tts_text(text)
        assert "ms" not in result
        assert result == "Ciao, come stai?"
        print(f"  PASS: '{text}' -> '{result}'")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # RISULTATO
    print("\n" + "="*60)
    total = passed + failed
    print(f"RISULTATO: {passed}/{total} test passati")
    if failed > 0:
        print(f"FALLITI: {failed}")
    else:
        print("TUTTI I TEST PASSATI")
    print("="*60)

if __name__ == "__main__":
    test_rimozione_ms()
