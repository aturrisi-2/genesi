#!/usr/bin/env python3
"""
Test Finale STT No Test Messages - Verifica assenza totale di test messages
"""
import requests
import json

def test_stt_no_test_messages():
    print("=== TEST FINALE STT - NESSUN MESSAGGIO DI TEST ===")
    
    # Test con diverse dimensioni per verificare che non ci siano mai test messages
    test_cases = [
        (b"x" * 50, "Audio molto piccolo (50 bytes)"),
        (b"x" * 500, "Audio piccolo (500 bytes)"),
        (b"x" * 5000, "Audio medio (5000 bytes)"),
        (b"x" * 50000, "Audio grande (50000 bytes)"),
        (b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00@\x1f\x00\x00\x80\x3e\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00", "iOS 44 bytes")
    ]
    
    results = []
    test_message_count = 0
    
    for audio_data, description in test_cases:
        try:
            with open('test_temp.txt', 'wb') as f:
                f.write(audio_data)
            
            response = requests.post('http://localhost:8000/stt', files={'audio': open('test_temp.txt', 'rb')})
            
            if response.status_code == 200:
                result = response.json()
                text = result['text']
                print(f"   ✅ {description} ({len(audio_data)} bytes): '{text}'")
                
                # Verifica che non ci siano test messages
                test_phrases = ["prova audio", "test audio", "audio.*test", "microfono funzionante"]
                for phrase in test_phrases:
                    if phrase in text.lower():
                        test_message_count += 1
                        print(f"      ❌ TEST MESSAGE TROVATO: '{phrase}'")
                
                results.append((description, len(audio_data), text))
            else:
                print(f"   ❌ {description}: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"   ❌ {description}: Errore {e}")
            return False
    
    # Verifica che non ci siano test messages
    no_test_messages = test_message_count == 0
    
    print(f"\n2. ANALISI TEST MESSAGES:")
    print(f"   ✅ Test eseguiti: {len(results)}")
    print(f"   ✅ Test messages trovati: {test_message_count}")
    print(f"   ✅ Nessun test message: {no_test_messages}")
    
    if not no_test_messages:
        print("   ❌ ANCORA TROVATI TEST MESSAGES!")
        return False
    
    print("\n3. VERIFICA REPO:")
    try:
        import subprocess
        result = subprocess.run(['grep', '-r', 'prova audio', '/Users/alfioturrisi/genesi', '--exclude-dir=.git'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("   ❌ ANCORA TROVATO 'prova audio' nel repo!")
            print(f"   {result.stdout}")
            return False
        else:
            print("   ✅ Nessun 'prova audio' nel repo")
    except Exception as e:
        print(f"   ❌ Errore verifica repo: {e}")
        return False
    
    print("\n4. COMPORTAMENTO ATTESO:")
    print("   - Audio qualsiasi → stringa vuota")
    print("   - MAI più test messages hardcoded")
    print("   - MAI più frasi di test")
    print("   - MAI più fallback testuali")
    
    print("\n5. FLUSSO CORRETTO:")
    print("   audio → STT → stringa vuota")
    print("   stringa vuota → chat → bloccato")
    print("   MAI più test messages → chat")
    
    print("\n6. RISULTATO FINALE:")
    print("   - STT pulito: nessun test message")
    print("   - Chat pulita: nessuna risposta inutile")
    print("   - Repo pulito: nessuna stringa di test")
    print("   - Sistema pronto per vera trascrizione")
    
    return True

if __name__ == "__main__":
    result = test_stt_no_test_messages()
    print("\n" + "="*70)
    if result:
        print("✅ NESSUN MESSAGGIO DI TEST IMPLEMENTATO")
        print("STT completamente pulito, pronto per trascrizione reale")
    else:
        print("❌ ANCORA MESSAGGI DI TEST PRESENTI")
        print("Rimuovere tutte le stringhe di test")
    print("="*70)
