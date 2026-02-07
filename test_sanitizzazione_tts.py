#!/usr/bin/env python3
"""
Test sanitizzazione TTS - 5 scenari obbligatori (senza dipendenze esterne)
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
    return text

def test_sanitizzazione_tts():
    print("=== TEST SANITIZZAZIONE TTS - 5 SCENARI ===")
    passed = 0
    failed = 0

    # TEST 1: Risposta breve ("ciao") → voce pulita
    print("\n1) Risposta breve -> voce pulita")
    try:
        text = "Ciao, come stai?"
        result = sanitize_tts_text(text)
        assert result == "Ciao, come stai?"
        print(f"  PASS: '{text}' -> '{result}'")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 2: Risposta lunga → nessun numero letto
    print("\n2) Risposta lunga -> nessun numero letto")
    try:
        text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua."
        result = sanitize_tts_text(text)
        assert result == text  # Dovrebbe rimanere uguale
        print(f"  PASS: testo lungo non modificato")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 3: Log verbosi attivi → voce pulita
    print("\n3) Log verbosi attivi -> voce pulita")
    try:
        text = "[RESPONSE_GENERATOR] Ciao, come stai?"
        result = sanitize_tts_text(text)
        assert result == "Ciao, come stai?"
        print(f"  PASS: '{text}' -> '{result}'")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 4: Timestamp contaminante → voce pulita
    print("\n4) Timestamp contaminante -> voce pulita")
    try:
        text = "2025-02-07T23:42:00.123Z Ciao, come stai?"
        result = sanitize_tts_text(text)
        assert result == "Ciao, come stai?"
        print(f"  PASS: '{text}' -> '{result}'")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 5: Numero iniziale → voce pulita
    print("\n5) Numero iniziale -> voce pulita")
    try:
        text = "1234567890 Ciao, come stai?"
        result = sanitize_tts_text(text)
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
    test_sanitizzazione_tts()
