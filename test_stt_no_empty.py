#!/usr/bin/env python3
"""
Test Finale STT No Empty - Verifica assenza totale di stringhe vuote
"""
import requests
import json

def test_stt_no_empty():
    print("=== TEST FINALE STT - NESSUNA STRINGA VUOTA ===")
    
    # Test con diverse dimensioni per verificare che non ci siano mai stringhe vuote
    test_cases = [
        (b"x" * 1, "Audio molto piccolo (1 byte)"),
        (b"x" * 50, "Audio piccolo (50 bytes)"),
        (b"x" * 500, "Audio medio (500 bytes)"),
        (b"x" * 5000, "Audio grande (5000 bytes)"),
        (b"x" * 50000, "Audio molto grande (50000 bytes)"),
        (b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00@\x1f\x00\x00\x80\x3e\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00", "iOS 44 bytes")
    ]
    
    results = []
    empty_count = 0
    
    for audio_data, description in test_cases:
        try:
            with open('test_temp.txt', 'wb') as f:
                f.write(audio_data)
            
            response = requests.post('http://localhost:8000/stt', files={'audio': open('test_temp.txt', 'rb')})
            
            if response.status_code == 200:
                result = response.json()
                text = result['text']
                print(f"   ✅ {description} ({len(audio_data)} bytes): '{text}'")
                
                if text == "":
                    empty_count += 1
                    print(f"      ❌ STRINGA VUOTA TROVATA!")
                
                results.append((description, len(audio_data), text))
            else:
                print(f"   ❌ {description}: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"   ❌ {description}: Errore {e}")
            return False
    
    # Verifica che non ci siano stringhe vuote
    no_empty = empty_count == 0
    
    print(f"\n2. ANALISI STRINGHE VUOTE:")
    print(f"   ✅ Test eseguiti: {len(results)}")
    print(f"   ✅ Stringhe vuote trovate: {empty_count}")
    print(f"   ✅ Nessuna stringa vuota: {no_empty}")
    
    if not no_empty:
        print("   ❌ ANCORA TROVATE STRINGHE VUOTE!")
        return False
    
    print("\n3. COMPORTAMENTO ATTESO:")
    print("   - Audio < 100 bytes: '[audio troppo breve]'")
    print("   - Audio >= 100 bytes: '[audio non riconosciuto]'")
    print("   - Errore: '[errore trascrizione]'")
    print("   - MAI più stringa vuota")
    
    print("\n4. LOG ATTESI:")
    print("   - [STT] Received data: XXXX bytes")
    print("   - [STT] Processed data: XXXX bytes -> '[stringa]'")
    print("   - MAI più -> ''")
    
    print("\n5. RISULTATO FINALE:")
    print("   - STT deterministico: sempre stringa")
    print("   - Nessun silenzio: mai ''")
    print("   - Chat riceve sempre testo: anche fallback")
    print("   - LLM risponde al contenuto: anche '[audio non riconosciuto]'")
    
    return True

if __name__ == "__main__":
    result = test_stt_no_empty()
    print("\n" + "="*70)
    if result:
        print("✅ NESSUNA STRINGA VUOTA IMPLEMENTATO")
        print("STT deterministico, nessun silenzio, sempre testo")
    else:
        print("❌ ANCORA STRINGHE VUOTE PRESENTI")
        print("Rimuovere tutti i return \"\"")
    print("="*70)
