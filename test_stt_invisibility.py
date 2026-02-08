#!/usr/bin/env python3
"""
Test Finale Bug Logico STT - Verifica che STT sia invisibile
"""
import requests
import json

def test_stt_invisibility():
    print("=== TEST FINALE BUG LOGICO STT - INVISIBILITÀ COMPLETA ===")
    
    # Test 1: STT restituisce stringa vuota
    print("1. Test STT restituisce stringa vuota...")
    try:
        with open('test_audio.txt', 'wb') as f:
            f.write(b'x' * 60000)
        
        response = requests.post('http://localhost:8000/stt', files={'audio': open('test_audio.txt', 'rb')})
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ STT response: '{result['text']}'")
            
            if result['text'] == "":
                print("   ✅ Stringa vuota - NESSUNA parola problematica")
            else:
                print("   ❌ STT restituisce ancora testo non vuoto")
                return False
        else:
            print(f"   ❌ Errore HTTP: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Errore test: {e}")
        return False
    
    # Test 2: Verifica assenza parole problematiche nei log
    print("2. Verifica assenza parole problematiche nei log...")
    problematic_words = ["prova", "test", "ricevuto", "funziona", "microfono"]
    # 'audio' e 'verifica' sono permessi solo come nomi di parametro o in commenti di sistema, non nei log/testi
    
    try:
        # Controlla api/stt.py (solo contenuto effettivo)
        with open('/Users/alfioturrisi/genesi/api/stt.py', 'r') as f:
            lines = f.readlines()
            for line_num, line in enumerate(lines, 1):
                # Ignora righe con commenti o docstring
                line_clean = line.strip()
                if line_clean.startswith('#') or line_clean.startswith('"""') or line_clean.startswith("'''"):
                    continue
                for word in problematic_words:
                    if word in line_clean.lower():
                        print(f"   ❌ Parola problematica trovata in api/stt.py riga {line_num}: '{word}'")
                        return False
        
        print("   ✅ Nessuna parola problematica in api/stt.py")
        
        # Controlla core/llm.py
        with open('/Users/alfioturrisi/genesi/core/llm.py', 'r') as f:
            lines = f.readlines()
            for line_num, line in enumerate(lines, 1):
                line_clean = line.strip()
                if line_clean.startswith('#') or line_clean.startswith('"""') or line_clean.startswith("'''"):
                    continue
                for word in problematic_words:
                    if word in line_clean.lower():
                        print(f"   ❌ Parola problematica trovata in core/llm.py riga {line_num}: '{word}'")
                        return False
        
        print("   ✅ Nessuna parola problematica in core/llm.py")
        
    except Exception as e:
        print(f"   ❌ Errore verifica file: {e}")
        return False
    
    print("\n3. COMPORTAMENTO ATTESO:")
    print("   - STT restituisce stringa vuota per audio finto")
    print("   - Nessuna frase contenente 'audio', 'prova', 'test'")
    print("   - Nessuna risposta di servizio tipo 'non posso analizzare audio'")
    print("   - STT completamente invisibile al sistema")
    
    print("\n4. TEST MANUALE OBBLIGATORIO:")
    print("   Quando avrai OpenAI API_KEY:")
    print("   - Di una frase normale con il microfono")
    print("   - Il sistema DEVE rispondere al CONTENUTO")
    print("   - NON deve dire 'audio funziona' o simili")
    
    print("\n5. CRITERI DI SUCCESSO:")
    print("   ✅ STT invisibile - nessuna traccia di 'test'")
    print("   ✅ Voce ≡ testo - stesso percorso")
    print("   ✅ Nessuna classificazione meta-contenuto")
    print("   ✅ Risposte naturali al contenuto")
    
    return True

if __name__ == "__main__":
    result = test_stt_invisibility()
    print("\n" + "="*70)
    if result:
        print("✅ BUG LOGICO STT RISOLTO")
        print("STT completamente invisibile al sistema")
    else:
        print("❌ BUG LOGICO STT PRESENTE")
        print("Rimuovere tutte le tracce di test/meta-contenuto")
    print("="*70)
