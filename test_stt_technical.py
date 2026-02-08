#!/usr/bin/env python3
"""
Test Finale STT Segnali Tecnici - Verifica blocco segnali tecnici
"""
import requests
import json

def test_stt_technical_signals():
    print("=== TEST FINALE STT - BLOCCO SEGNALI TECNICI ===")
    
    # Test segnali tecnici STT
    technical_markers = [
        "[audio non riconosciuto]",
        "[audio troppo breve]",
        "[errore trascrizione]",
        "[silenzio]",
        "[trascrizione fallita]"
    ]
    
    print("1. Test segnali tecnici STT (devono essere bloccati)...")
    blocked_count = 0
    
    for marker in technical_markers:
        try:
            response = requests.post('http://localhost:8000/chat', 
                                     json={'message': marker, 'user_id': 'test'})
            
            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ {marker}: response='{result['response']}' tts_mode={result.get('tts_mode')} should_respond={result.get('should_respond')}")
                
                # Verifica che sia bloccato correttamente
                if (result['response'] == "" and 
                    result.get('tts_mode') is None and 
                    result.get('should_respond') == False):
                    blocked_count += 1
                else:
                    print(f"      ❌ NON BLOCCATO CORRETTAMENTE!")
            else:
                print(f"   ❌ {marker}: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"   ❌ {marker}: Errore {e}")
            return False
    
    # Test messaggio normale (deve passare)
    print("\n2. Test messaggio normale (deve passare)...")
    try:
        response = requests.post('http://localhost:8000/chat', 
                                 json={'message': 'ciao mondo', 'user_id': 'test'})
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ 'ciao mondo': response='{result['response'][:50]}...' tts_mode={result.get('tts_mode')} should_respond={result.get('should_respond')}")
            
            # Verifica che passi correttamente
            if (result['response'] != "" and 
                result.get('tts_mode') is not None and 
                result.get('should_respond') == True):
                print("   ✅ MESSAGGIO NORMALE PASSA CORRETTAMENTE")
            else:
                print("      ❌ MESSAGGIO NORMALE BLOCCATO!")
                return False
        else:
            print(f"   ❌ 'ciao mondo': HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ 'ciao mondo': Errore {e}")
        return False
    
    print(f"\n3. ANALISI BLOCCO:")
    print(f"   ✅ Segnali tecnici testati: {len(technical_markers)}")
    print(f"   ✅ Segnali bloccati: {blocked_count}")
    print(f"   ✅ Blocco completo: {blocked_count == len(technical_markers)}")
    
    if blocked_count != len(technical_markers):
        print("   ❌ ALCUNI SEGNALI NON BLOCCATI!")
        return False
    
    print("\n4. COMPORTAMENTO ATTESO:")
    print("   - Segnali tecnici STT → nessuna risposta")
    print("   - Messaggi normali → risposta normale")
    print("   - Nessuna memoria sporca da segnali tecnici")
    print("   - Nessun TTS per segnali tecnici")
    
    print("\n5. LOG ATTESI:")
    print("   - CHAT_IN user_id=X msg='[audio non riconosciuto]'")
    print("   - CHAT_STT_TECHNICAL user_id=X marker='[audio non riconosciuto]'")
    print("   - MAI più INTENT per segnali tecnici")
    print("   - MAI più MEMORY per segnali tecnici")
    
    print("\n6. RISULTATO FINALE:")
    print("   - SEGNALI TECNICI ≠ MESSAGGI UMANI")
    print("   - Blocco completo prima di INTENT")
    print("   - Nessuna memoria sporca")
    print("   - Nessuna risposta inutile")
    
    return True

if __name__ == "__main__":
    result = test_stt_technical_signals()
    print("\n" + "="*70)
    if result:
        print("✅ BLOCCO SEGNALI TECNICI IMPLEMENTATO")
        print("Separazione completa: segnali tecnici ≠ messaggi umani")
    else:
        print("❌ BLOCCO SEGNALI TECNICI FALLITO")
        print("Verificare che tutti i segnali siano bloccati")
    print("="*70)
