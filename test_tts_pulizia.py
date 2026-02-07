#!/usr/bin/env python3
"""
Test per verificare contaminazione testo TTS
"""
import asyncio
import sys
import os
sys.path.insert(0, '.')

from tts.coqui import synthesize_bytes

def test_tts_pulizia():
    print("=== TEST TTS PULIZIA TESTO ===")
    passed = 0
    failed = 0

    # TEST 1: Testo normale
    print("\n1) Testo normale")
    try:
        text = "Ciao, come stai?"
        audio = synthesize_bytes(text)
        assert len(audio) > 0
        print(f"  PASS: testo pulito '{text}' -> audio generato")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 2: Testo con timestamp
    print("\n2) Testo con timestamp")
    try:
        text = "2025-02-07T23:42:00.123Z Ciao, come stai?"
        audio = synthesize_bytes(text)
        assert len(audio) > 0
        print(f"  ATTENZIONE: testo con timestamp '{text}' -> audio generato (probabilmente letto)")
        failed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 3: Testo con prefisso log
    print("\n3) Testo con prefisso log")
    try:
        text = "[RESPONSE_GENERATOR] Ciao, come stai?"
        audio = synthesize_bytes(text)
        assert len(audio) > 0
        print(f"  ATTENZIONE: testo con prefisso log '{text}' -> audio generato (probabilmente letto)")
        failed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 4: Testo con numero iniziale
    print("\n4) Testo con numero iniziale")
    try:
        text = "1234567890 Ciao, come stai?"
        audio = synthesize_bytes(text)
        assert len(audio) > 0
        print(f"  ATTENZIONE: testo con numero iniziale '{text}' -> audio generato (probabilmente letto)")
        failed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # RISULTATO
    print("\n" + "="*60)
    total = passed + failed
    print(f"RISULTATO: {passed}/{total} test passati")
    if failed > 0:
        print(f"ATTENZIONE: {failed} test mostrano contaminazione possibile")
    else:
        print("TUTTI I TEST PASSATI")
    print("="*60)

if __name__ == "__main__":
    test_tts_pulizia()
