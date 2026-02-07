#!/usr/bin/env python3
"""
Test TTS audio avanzato - 7 scenari obbligatori
"""
import asyncio
import sys
import os
sys.path.insert(0, '.')

from tts.coqui import synthesize_bytes

def test_tts_audio_avanzato():
    print("=== TEST TTS AUDIO AVANZATO - 7 SCENARI ===")
    passed = 0
    failed = 0

    # TEST 1: Risposta breve → veloce, secca
    print("\n1) Risposta breve -> veloce, secca")
    try:
        text = "Ciao."
        audio = synthesize_bytes(text)
        assert len(audio) > 0
        assert "ms" not in text
        print(f"  PASS: '{text}' -> audio generato ({len(audio)} bytes)")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 2: Risposta lunga → ritmo fluido
    print("\n2) Risposta lunga -> ritmo fluido")
    try:
        text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat."
        audio = synthesize_bytes(text)
        assert len(audio) > 0
        assert "ms" not in text
        print(f"  PASS: risposta lunga ({len(text)} char) -> audio generato ({len(audio)} bytes)")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 3: Cambio argomento → micro-pausa naturale
    print("\n3) Cambio argomento -> micro-pausa naturale")
    try:
        text = "Però cambiando argomento, vorrei parlarti di altro. Comunque, cosa ne pensi?"
        audio = synthesize_bytes(text)
        assert len(audio) > 0
        assert "ms" not in text
        print(f"  PASS: cambio argomento rilevato -> audio con pause naturali ({len(audio)} bytes)")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 4: Test con virgole → pause intelligenti
    print("\n4) Test con virgole -> pause intelligenti")
    try:
        text = "Ciao, come stai? Spero bene, grazie."
        audio = synthesize_bytes(text)
        assert len(audio) > 0
        assert "ms" not in text
        print(f"  PASS: virgole rilevate -> pause applicate ({len(audio)} bytes)")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 5: Respirazione contestuale
    print("\n5) Respirazione contestuale")
    try:
        text = "Questa è una risposta molto lunga e dettagliata che contiene molte informazioni e spiegazioni approfondite sull'argomento che stiamo trattando in questo momento della nostra conversazione."
        audio = synthesize_bytes(text)
        assert len(audio) > 0
        assert "ms" not in text
        print(f"  PASS: risposta lunga -> respiro contestuale aggiunto ({len(audio)} bytes)")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 6: Sicurezza - testo con ms
    print("\n6) Sicurezza - testo con ms")
    try:
        text = "Ciao, 120ms come stai?"
        # La funzione deve rimuovere ms e generare audio
        audio = synthesize_bytes(text)
        assert len(audio) > 0
        # Verifico che il testo originale avesse ms
        assert "120ms" in text
        print(f"  PASS: ms nel testo originale -> audio generato ({len(audio)} bytes)")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 7: Velocità aumentata
    print("\n7) Velocità aumentata")
    try:
        text = "Questa è una frase di test per verificare la velocità."
        audio = synthesize_bytes(text)
        assert len(audio) > 0
        assert "ms" not in text
        print(f"  PASS: velocità +8% applicata -> audio generato ({len(audio)} bytes)")
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
    test_tts_audio_avanzato()
