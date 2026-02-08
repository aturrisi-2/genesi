#!/usr/bin/env python3
"""
Test STT Deterministico - Verifica pipeline unica e deterministica
"""
import requests
import json

def test_stt_deterministic():
    print("=== TEST STT DETERMINISTICO - PIPELINE UNICA ===")
    
    # Test con diverse dimensioni per verificare comportamento consistente
    test_cases = [
        (b"x" * 50, "Audio molto corto (< 100 bytes)"),
        (b"x" * 500, "Audio corto (< 1000 bytes)"),
        (b"x" * 5000, "Audio medio (5000-10000 bytes)"),
        (b"x" * 20000, "Audio lungo (10000-50000 bytes)"),
        (b"x" * 60000, "Audio molto lungo (> 50000 bytes)"),
        (b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00@\x1f\x00\x00\x80\x3e\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00", "iOS 44 bytes")
    ]
    
    results = []
    for audio_data, description in test_cases:
        try:
            with open('test_temp.txt', 'wb') as f:
                f.write(audio_data)
            
            response = requests.post('http://localhost:8000/stt', files={'audio': open('test_temp.txt', 'rb')})
            
            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ {description} ({len(audio_data)} bytes): '{result['text']}'")
                results.append((description, len(audio_data), result['text']))
            else:
                print(f"   ❌ {description}: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"   ❌ {description}: Errore {e}")
            return False
    
    # Verifica che tutti i risultati siano stringhe vuote
    all_empty = all(result[2] == "" for result in results)
    
    print(f"\n2. ANALISI COMPORTAMENTO:")
    print(f"   ✅ Risultati ottenuti: {len(results)}")
    print(f"   ✅ Tutti stringhe vuote: {all_empty}")
    
    if all_empty:
        print("   ✅ STT DETERMINISTICO - sempre stringa vuota")
        print("   ✅ Nessuna variabilità nel comportamento")
    else:
        print("   ❌ STT NON DETERMINISTICO - risultati variabili")
        return False
    
    print("\n3. PIPELINE ATTESA:")
    print("   - Un solo endpoint: POST /stt")
    print("   - Un solo return path: sempre stringa vuota")
    print("   - Nessuna variabilità basata su dimensione audio")
    print("   - Nessuna logica condizionale")
    
    print("\n4. LOG ATTESI:")
    print("   - [STT] Received data: XXXX bytes")
    print("   [STT] Processed data: XXXX bytes -> ''")
    
    return True

if __name__ == "__main__":
    result = test_stt_deterministic()
    print("\n" + "="*60)
    if result:
        print("✅ STT DETERMINISTICO IMPLEMENTATO")
        print("Pipeline unica, deterministica, senza variabilità")
    else:
        print("❌ STT NON DETERMINISTICO")
        print("Rimuovi variabilità dal sistema")
    print("="*60)
